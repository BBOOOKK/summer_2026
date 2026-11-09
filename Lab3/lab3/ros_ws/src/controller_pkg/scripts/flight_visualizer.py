#!/usr/bin/env python3
import rospy,math
from visualization_msgs.msg import Marker,MarkerArray
from geometry_msgs.msg import Point
from nav_msgs.msg import Odometry
from trajectory_msgs.msg import MultiDOFJointTrajectoryPoint
rospy.init_node('flight_visualizer');pub=rospy.Publisher('/flight_visuals',MarkerArray,queue_size=1,latch=True)
trail=[];latest=None;desired=None;start=None
rospy.Subscriber('/desired_state',MultiDOFJointTrajectoryPoint,lambda m:globals().update(desired=m))
def base(i,kind,col):
 m=Marker();m.header.frame_id='world';m.header.stamp=rospy.Time(0);m.ns='LAB3';m.id=i;m.type=kind;m.action=Marker.ADD;m.pose.orientation.w=1;m.color.r,m.color.g,m.color.b,m.color.a=col;return m
def update(state):
 global start
 if start is None:start=state.header.stamp.to_sec()
 p=state.pose.pose.position;trail.append(Point(p.x,p.y,p.z))
 if len(trail)>12000:del trail[0]
 arr=MarkerArray();ring=base(0,Marker.LINE_STRIP,(.28,.78,.64,1));ring.scale.x=.035
 ring.points=[Point(5*math.sin(i*math.pi/180),5*math.cos(i*math.pi/180),2) for i in range(361)];arr.markers.append(ring)
 path=base(1,Marker.LINE_STRIP,(.25,.65,1,1));path.scale.x=.045;path.points=trail;arr.markers.append(path)
 body=base(2,Marker.CUBE,(1,.55,.16,1));body.pose=state.pose.pose;body.scale.x=.42;body.scale.y=.3;body.scale.z=.12;arr.markers.append(body)
 arms=base(3,Marker.LINE_LIST,(.9,.92,.96,1));arms.pose=state.pose.pose;arms.scale.x=.055
 arms.points=[Point(-.32,-.32,0),Point(.32,.32,0),Point(-.32,.32,0),Point(.32,-.32,0)];arr.markers.append(arms)
 ref=base(4,Marker.SPHERE,(.28,.78,.64,.85));ref.scale.x=ref.scale.y=ref.scale.z=.18
 err=float('nan')
 if desired and desired.transforms:
  d=desired.transforms[0].translation;ref.pose.position=Point(d.x,d.y,d.z);err=math.sqrt((p.x-d.x)**2+(p.y-d.y)**2+(p.z-d.z)**2)
 arr.markers.append(ref)
 title=base(5,Marker.TEXT_VIEW_FACING,(.95,.96,1,1));title.pose.position=Point(0,0,5.2);title.scale.z=.38;title.text='LAB3  |  GEOMETRIC TRAJECTORY TRACKING';arr.markers.append(title)
 status=base(6,Marker.TEXT_VIEW_FACING,(.72,.83,.93,1));status.pose.position=Point(0,0,4.5);status.scale.z=.27;status.text='Official TESSE / Unity  |  ROS Noetic\nTime: %.1f s   Position error: %.3f m\nBlue: vehicle   Green: reference'%(state.header.stamp.to_sec()-start,err);arr.markers.append(status)
 pub.publish(arr)
rospy.Subscriber('/current_state',Odometry,update,queue_size=1);rospy.spin()
