#!/usr/bin/env python3
"""Publish official Unity states in VNAV's ROS frames and relay rotor commands."""
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile
import rospy,socket,json,xml.etree.ElementTree as ET,csv,math,time
import numpy as np
from nav_msgs.msg import Odometry
from mav_msgs.msg import Actuators
from rosgraph_msgs.msg import Clock
from trajectory_msgs.msg import MultiDOFJointTrajectoryPoint
import tf
rospy.init_node('official_unity_bridge')
rotors=[49.5227]*4; desired=[float('nan')]*3; desired_yaw=float('nan')
ready=threading.Event();desired_ready=threading.Event()
def command(m):
 rotors[:]=list(m.angular_velocities);ready.set()
rospy.Subscriber('/rotor_speed_cmds',Actuators,command,tcp_nodelay=True)
def reference(m):
 global desired_yaw
 if m.transforms:
  desired[:]=[m.transforms[0].translation.x,m.transforms[0].translation.y,m.transforms[0].translation.z]
  r=m.transforms[0].rotation
  desired_yaw=tf.transformations.euler_from_quaternion([r.x,r.y,r.z,r.w])[2]
  desired_ready.set()
rospy.Subscriber('/desired_state',MultiDOFJointTrajectoryPoint,reference)
pub=rospy.Publisher('/current_state',Odometry,queue_size=1);clock=rospy.Publisher('/clock',Clock,queue_size=1);br=tf.TransformBroadcaster()
s=socket.create_connection((rospy.get_param('~host','host.docker.internal'),9010),timeout=30);stream=s.makefile('rwb',buffering=0)
record_dir=Path(rospy.get_param('~record_dir', 'flight')).expanduser()
record_dir.mkdir(parents=True,exist_ok=True)
out=NamedTemporaryFile(mode='w',dir=record_dir,prefix='ros_unity_',suffix='.csv',delete=False,buffering=1,newline='')
rospy.loginfo('Recording flight to %s',out.name)
rospy.on_shutdown(out.close)
writer=csv.writer(out);writer.writerow(['time','x','y','z','vx','vy','vz','xd','yd','zd','desired_yaw','actual_yaw','yaw_error','error','rotor1','rotor2','rotor3','rotor4','qx','qy','qz','qw','wx','wy','wz'])
first=True;count=0
while not rospy.is_shutdown():
 applied=rotors.copy()
 stream.write((json.dumps({'rotors':applied,'initialize':first})+'\n').encode());first=False
 response=json.loads(stream.readline())
 if 'error' in response:rospy.logwarn(response['error']);time.sleep(.1);continue
 root=ET.fromstring(response['xml'])
 def vec(tag,keys):return [float(root.find(tag).attrib[k]) for k in keys]
 p=vec('position',['x','z','y']);q=vec('quaternion',['x','z','y','w']);q=[-q[0],-q[1],-q[2],q[3]]
 v=vec('velocity',['x_dot','z_dot','y_dot']);w=vec('angular_velocity',['x_ang_dot','z_ang_dot','y_ang_dot']);w=[-a for a in w]
 stamp=rospy.Time.from_sec(float(root.find('time').text));msg=Odometry();msg.header.stamp=stamp;msg.header.frame_id='world';msg.child_frame_id='base_link_gt'
 msg.pose.pose.position.x,msg.pose.pose.position.y,msg.pose.pose.position.z=p
 msg.pose.pose.orientation.x,msg.pose.pose.orientation.y,msg.pose.pose.orientation.z,msg.pose.pose.orientation.w=q
 msg.twist.twist.linear.x,msg.twist.twist.linear.y,msg.twist.twist.linear.z=v
 msg.twist.twist.angular.x,msg.twist.twist.angular.y,msg.twist.twist.angular.z=w
 ready.clear();desired_ready.clear();pub.publish(msg);time.sleep(.002);clock.publish(Clock(stamp));br.sendTransform(p,q,stamp,'base_link_gt','world')
 ready.wait(.03);desired_ready.wait(.03)
 actual_yaw=tf.transformations.euler_from_quaternion(q)[2]
 yaw_error=math.atan2(math.sin(actual_yaw-desired_yaw),math.cos(actual_yaw-desired_yaw))
 writer.writerow([stamp.to_sec(),*p,*v,*desired,desired_yaw,actual_yaw,yaw_error,float(np.linalg.norm(np.array(p)-desired)),*applied,*q,*w]);count+=1
 if count%100==0:rospy.loginfo('Official Unity: t=%.2f, xyz=(%.2f,%.2f,%.2f)',stamp.to_sec(),*p)
