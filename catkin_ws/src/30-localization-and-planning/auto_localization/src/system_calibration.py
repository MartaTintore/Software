#!/usr/bin/env python

## AIDO localization Sysem Calibration
# Author: Chen-Lung (Eric) Lu , ETHZ NCTU, eric565648.eed03@g2.nctu.edu.tw

## This script records the positions of all reference Apriltags
# and save them into map file
# The scenerio is that the system will calibrate itself from time to time.

import rospkg
import rospy
import sys
import yaml
import numpy as np
from datetime import datetime
import tf
import tf.transformations as tr
import numpy as np

from duckietown_msgs.msg import RemapPoseArray, RemapPose, GlobalPoseArray, GlobalPose

class system_calibration(object):

    def __init__(self):

        self.node_name = 'system_calibration'

        # load the map file, notice that it will overwrite the file
        self.map_filename = rospy.get_param("~map") + ".yaml"
        self.output_map_filename = rospy.get_param("~output_file") + ".yaml"
        self.map_data = self.load_map_info(self.map_filename)

        # Subscribe all tfs from subfserver node
        self.sub_tfs = rospy.Subscriber("local_poses", RemapPoseArray, self.callback, queue_size=1)

        # Start Calibration

        #Parameters
        self.start_calibrate = False
        self.wait_for_message = 15 # At least wait 3 secs (15/5hz from subfserver_easy node) for tags collection after all watchtower have publish things.

        #Watchtowers, to make sure they all send datas
        self.watchtowers = {}
        for wt in self.map_watchtowers:
            self.watchtowers[wt] = False

    # callback make sure that all watchtowers have sent messages.
    def callback(self, msg_tfs):

        # Return callback if calibration has already started
        if self.start_calibrate == True:
            return

        # Make sure that we get meesage from all watchtowers
        if self.wait_for_message == 15:
            for tf in msg_tfs.poses:
                self.watchtowers[tf.host] = True
            not_ready = ""
            for wt in self.watchtowers:
                if self.watchtowers[wt] == False:
                    not_ready += wt + ", "
            if not_ready == "":
                rospy.loginfo("Get all tags. Start Counting Down")
            else:
                rospy.loginfo("Still waiting for: " + not_ready)
                return

        self.wait_for_message -= 1
        rospy.loginfo("Start Calibration in %d secs", self.wait_for_message/5)

        if self.wait_for_message == 0:
            self.start_calibrate = True
            self.sys_calib(msg_tfs.poses)


    def sys_calib(self, msg_tfs):

        self.tag_relationship = self.find_tag_relationship(msg_tfs)

        fixed_tags_data = []
        for tag in self.tag_relationship:
            # Every matrix is the transformation matrix between the tag and origin tag
            # We here decompose the matrix and save only translation and rotation
            tag_data = {}
            tag_data['id'] = tag
            tag_data['transformation'] = list(self.tag_relationship[tag])
            fixed_tags_data.append(tag_data)


        # Write the transformation relationship to map file
        data = {'tiles':self.map_tiles, 'watchtowers':self.map_watchtowers, 'origin':self.map_origins, 'fixed_tags':fixed_tags_data}
        with open(rospkg.RosPack().get_path('auto_localization')+"/config/"+self.output_map_filename, 'w') as outfile:
            yaml.dump(data, outfile, default_flow_style=False)

        rospy.loginfo("Calibration Finished!")
        rospy.signal_shutdown("Finished Calibration")

    # find relationship of each tags with origin
    # return a dictionary with tag id as key and translation, rotation as content of each key
    def find_tag_relationship(self, tfs):

        # https://www.python.org/doc/essays/graphs/
        # make all pose to pose relationship into a graph
        # so that we could compute shortest path
        # and get the tag to origin transformation later
        tag_graph = dict() # Save tag node connection graph with a 1D dictionary
        tag_transformation = dict() # Save tag transformation with a 2D dictionary
        for tf_node in tfs:
            if not tag_graph.has_key(tf_node.frame_id):
                tag_graph[tf_node.frame_id] = []
                tag_transformation[tf_node.frame_id] = dict()
            # Here we create transformation link with python dictionary between tag and tag
            # For convenient, we reuse RemapPose message data type here
            # frame_id = child frame, bot_id = parent frame
            # tag_transformation[child_frame][parent_frame]
            tag_graph[tf_node.frame_id].append(tf_node.bot_id)
            tag_transformation[tf_node.frame_id][tf_node.bot_id] = [  [tf_node.posestamped.pose.position.x, tf_node.posestamped.pose.position.y, tf_node.posestamped.pose.position.z],
                                                            [tf_node.posestamped.pose.orientation.x, tf_node.posestamped.pose.orientation.y, tf_node.posestamped.pose.orientation.z, tf_node.posestamped.pose.orientation.w]]

        # Define a find shortest path function here
        def find_shortest_path(graph, start, end, path=[]):
            path = path + [start]
            if start == end:
                return path
            if not graph.has_key(start):
                return None
            shortest = None
            for node in graph[start]:
                if node not in path:
                    newpath = find_shortest_path(graph, node, end, path)
                    if newpath:
                        if not shortest or len(newpath) < len(shortest):
                            shortest = newpath
            return shortest

        # A little recursive function to find the transformation from origin to end_tag
        def from_origin_to_end(path):
            # tag_transformation[child_frame][parent_frame]
            trans = tag_transformation[path[0]][path[1]][0]
            rot = tag_transformation[path[0]][path[1]][1]
            # Compse transformation matrix with translation and angle (in euler)
            transformation_mat = tr.compose_matrix(angles=tr.euler_from_quaternion(rot), translate=trans)
            if len(path) == 2:
                return transformation_mat
            else:
                next_transformation = from_origin_to_end(path[1:])
                print next_transformation
                print np.dot(transformation_mat, next_transformation)
                return np.dot(transformation_mat, next_transformation)

        tag_relationship = dict()
        origin = self.map_origins[0]['id'] # a.t.m. we only consider one origin
        for tag_node in tag_graph:
            print "tag_node: ", tag_node
            if tag_node == origin:
                tag_relationship[tag_node] = np.identity(4)
            else:
                path_node = find_shortest_path(tag_graph, origin, tag_node)
                print "path_node: ", path_node
                tag_relationship[tag_node] = from_origin_to_end(path_node)

        print tag_relationship
        return tag_relationship

    ## Load Map Data
    def load_map_info(self, filename):

        map_data = yaml.load(file(rospkg.RosPack().get_path('auto_localization')+"/config/"+filename,'r')) # Need RosPack get_path to find the file path
        print "Loaded map from file: ", self.map_filename

        self.map_tiles = map_data['tiles']
        print "\nThis is your map: \n", self.map_tiles

        self.map_watchtowers = map_data['watchtowers']
        print "\nThese watchtowers suppose to work: \n", self.map_watchtowers

        self.map_origins = map_data['origin']
        print "The origins: \n", self.map_origins

        return map_data


### ------------------- ------- MAIN -------------------------------#####
if __name__ == '__main__':
    rospy.init_node('system_calibration',anonymous=False, disable_signals=True)
    node = system_calibration()
    rospy.spin()