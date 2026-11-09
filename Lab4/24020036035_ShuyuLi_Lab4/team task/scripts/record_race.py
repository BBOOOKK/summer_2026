#!/usr/bin/env python3
"""Record real simulator messages with reference trajectory time."""
import argparse,csv,json,time
from pathlib import Path
import rospy
from nav_msgs.msg import Odometry
from trajectory_msgs.msg import MultiDOFJointTrajectoryPoint
from std_msgs.msg import Float64MultiArray
from tf.transformations import euler_from_quaternion
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--duration',type=float,default=120)
args=p.parse_args();rospy.init_node('lab4_recorder')
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
f=out.open('w');w=csv.writer(f)
w.writerow(['t','stamp','plan_t','desired_stamp','x','y','z','xd','yd','zd','vx','vy','vz','vxd','vyd','vzd','roll','pitch','yaw','yawd','thrust','saturated'])
desired=None;origin=None;ds=0;diag=[0]*17;done=False;count=0;last=time.monotonic()
plan_offset=0;have_plan_offset=False
def target(m):
    global desired,origin,ds,plan_offset,have_plan_offset
    desired=m;ds=rospy.Time.now().to_sec()
    if origin is not None and not have_plan_offset and m.time_from_start.to_sec()>0:
        plan_offset=max(0,ds-origin-m.time_from_start.to_sec());have_plan_offset=True
def diagnostic(m):
    global diag
    diag=list(m.data)
def state(m):
    global done,count,last,origin
    last=time.monotonic()
    if desired is None or done:return
    if origin is None:origin=m.header.stamp.to_sec()
    t=m.header.stamp.to_sec()-origin
    if t<0:return
    pos=m.pose.pose.position;q=m.pose.pose.orientation;v=m.twist.twist.linear
    d=desired.transforms[0];vd=desired.velocities[0].linear
    rpy=euler_from_quaternion([q.x,q.y,q.z,q.w]);qd=d.rotation
    yd=euler_from_quaternion([qd.x,qd.y,qd.z,qd.w])[2]
    w.writerow([t,m.header.stamp.to_sec(),desired.time_from_start.to_sec(),ds,
                pos.x,pos.y,pos.z,d.translation.x,d.translation.y,d.translation.z,
                v.x,v.y,v.z,vd.x,vd.y,vd.z,*rpy,yd,diag[12],diag[16]])
    count+=1
    if count%100==0:f.flush()
    plan=out.parent/'plan.csv.times'
    duration=float(plan.read_text().splitlines()[-1])+4 if plan.exists() else args.duration
    if t>=duration+plan_offset or abs(pos.x)>150 or abs(pos.y)>150 or pos.z < -10 or pos.z>100:done=True
rospy.Subscriber('/desired_state',MultiDOFJointTrajectoryPoint,target,queue_size=1)
rospy.Subscriber('/current_state',Odometry,state,queue_size=100)
rospy.Subscriber('/controller_diagnostics',Float64MultiArray,diagnostic,queue_size=1)
begin=time.monotonic()
while not done and not rospy.is_shutdown():
    if time.monotonic()-begin>600 or time.monotonic()-last>45:break
    time.sleep(.05)
f.close()
(out.parent/'record_status.json').write_text(json.dumps({'samples':count,'wall_seconds':time.monotonic()-begin,'completed':done}))
if count<10:raise RuntimeError('No valid simulator telemetry')
