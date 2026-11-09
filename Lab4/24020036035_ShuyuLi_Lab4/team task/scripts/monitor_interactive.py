#!/usr/bin/env python3
"""Small live ROS status file for the native control panel; no replay data."""
import json,time,os,math,collections
from pathlib import Path
import rospy
from nav_msgs.msg import Odometry
from trajectory_msgs.msg import MultiDOFJointTrajectoryPoint
out=Path('/work/lab4/interactive_status.json')
rospy.init_node('lab4_interactive_status',anonymous=True)
state={};samples=collections.deque(maxlen=100);lastwrite=0
def current(m):
 global lastwrite
 p=m.pose.pose.position;stamp=m.header.stamp.to_sec();wall=time.monotonic()
 samples.append((wall,stamp));state.update(x=p.x,y=p.y,z=p.z,sim_time=stamp)
 if len(samples)>2:
  state['state_hz']=(len(samples)-1)/max(.001,wall-samples[0][0])
  state['sim_per_wall']=(stamp-samples[0][1])/max(.001,wall-samples[0][0])
 if wall-lastwrite>.2:
  state['updated_wall']=time.time();tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(state));os.replace(str(tmp),str(out));lastwrite=wall
def desired(m):
 if m.transforms:
  p=m.transforms[0].translation;state.update(xd=p.x,yd=p.y,zd=p.z)
rospy.Subscriber('/current_state',Odometry,current,queue_size=10)
rospy.Subscriber('/desired_state',MultiDOFJointTrajectoryPoint,desired,queue_size=10)
rospy.spin()
