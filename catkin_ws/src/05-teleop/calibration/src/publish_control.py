#!/usr/bin/env python
import rospy
import rosnode
from std_msgs.msg import String #Imports msg
from duckietown_msgs.msg import WheelsCmdStamped, Twist2DStamped
from math import sin, pi, cos
import os 

class calibration:
	def __init__(self):
		
		# Initialize the node with rospy
                rospy.init_node('command', anonymous=True)

                # Create publisher
                publisher=rospy.get_param("~veh")+"/wheels_driver_node/wheels_cmd"
                self.pub_wheels_cmd = rospy.Publisher(publisher,WheelsCmdStamped,queue_size=1)

		self.vFin = rospy.get_param("~vFin")
		self.Nstep = rospy.get_param("~Nstep")
		#self.stepTime = rospy.get_param("~stepTime")

		self.k1 = rospy.get_param("~k1")
                self.k2 = rospy.get_param("~k2")
                self.omega = rospy.get_param("~omega")
		self.duration = rospy.get_param("~duration")		
		self.frequency = 30.0

	def sendCommand(self, vel_right, vel_left):
		# Put the wheel commands in a message and publish
		msg_wheels_cmd = WheelsCmdStamped()
		msg_wheels_cmd.header.stamp = rospy.Time.now()
		msg_wheels_cmd.vel_right =vel_right
		msg_wheels_cmd.vel_left =vel_left
		self.pub_wheels_cmd.publish(msg_wheels_cmd)

	def StraightCalib(self):
		rospy.loginfo("Straight calibration starts")

		for n in range(1,self.Nstep+1):
			v=self.vFin/self.Nstep*n
			self.sendCommand(v, v)
			rospy.sleep(1/self.frequency)
		self.sendCommand(0, 0)


	def SinCalib(self):
		rospy.loginfo("Sin calibration starts") 

		for t in range(0,self.duration,10):
			self.sendCommand(self.k1+self.k2*cos(self.omega*t),self.k1-self.k2*cos(self.omega*t))
			rospy.sleep(1/self.frequency)
		
		self.sendCommand(0,0)


if __name__ == '__main__':
	rospy.sleep(5) #wait for the bag to start recording
	calib=calibration()

	calib.StraightCalib()
	rospy.loginfo("Replace your Duckietown at the beginning of the track, the calibration will restart in 10 seconds")
	rospy.sleep(10)
	calib.SinCalib()
	rospy.loginfo("Calibration finished")
	#os.system("rosnode kill /record")
