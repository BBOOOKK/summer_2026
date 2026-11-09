#!/usr/bin/env python3
"""Track a solved rigid-body trajectory using rotor commands and state feedback.

No pose writes, time scaling, collision switches, or simulator modifications.
"""
import argparse,json,math,time
from pathlib import Path
import numpy as np
import rospy
from scipy.spatial.transform import Rotation
from nav_msgs.msg import Odometry
from mav_msgs.msg import Actuators
from std_msgs.msg import Float64MultiArray
from trajectory_msgs.msg import MultiDOFJointTrajectoryPoint
from geometry_msgs.msg import Transform,Twist

ap=argparse.ArgumentParser();ap.add_argument('--reference',required=True)
ap.add_argument('--plan-output',required=True);ap.add_argument('--params-json',default='{}')
ap.add_argument('--ready-file',default='')
args=ap.parse_args();cfg=json.loads(args.params_json)
a=np.genfromtxt(args.reference,delimiter=',',names=True)
P=np.column_stack([a[k] for k in ['x','y','z']]);V=np.column_stack([a[k] for k in ['vx','vy','vz']]);A=np.column_stack([a[k] for k in ['ax','ay','az']]);Q=np.column_stack([a[k] for k in ['qx','qy','qz','qw']]);W=np.column_stack([a[k] for k in ['wx','wy','wz']]);U=np.column_stack([a[k] for k in ['u0','u1','u2','u3']])
rotations=Rotation.from_quat(Q).as_dcm()
arm=.3/math.sqrt(2);allocation=np.array([[1,1,1,1],[arm,arm,-arm,-arm],[-arm,arm,arm,-arm],[.01,-.01,.01,-.01]])
inverse=np.linalg.inv(allocation);J=np.diag([.1,.2,.1]);dt=.02
kp=cfg.get('pilot_position_gain',80.);kv=cfg.get('pilot_velocity_gain',18.)
kr=cfg.get('pilot_attitude_gain',12.);rate=cfg.get('pilot_rate_gain',50.)
preview=cfg.get('pilot_preview_steps',0);axis_feedback=cfg.get('pilot_axis_feedback',True)
delay_steps=cfg.get('pilot_delay_steps',0)
gain=cfg.get('pilot_feedback_scale',1.)
motor_compensation=cfg.get('pilot_motor_compensation',.9)
rotor_limit=cfg.get('pilot_max_rotor_speed',1000.)
force_limit=.001*rotor_limit**2
synchronous=cfg.get('pilot_synchronous',False)
direct_env=None
out=Path(args.plan_output);out.parent.mkdir(exist_ok=True,parents=True)
np.savetxt(str(out),np.column_stack([a['t'],P,V,A,Rotation.from_quat(Q).as_euler('xyz')[:,2]]),delimiter=',',header='t,x,y,z,vx,vy,vz,ax,ay,az,yaw',comments='')
status=json.loads((Path(args.reference).parent/'model_status.json').read_text())
np.savetxt(str(out)+'.times',np.r_[np.array(status['gate_indices'])*dt,a['t'][-1]])
rospy.init_node('rigid_reference_controller')
rotor=rospy.Publisher('/rotor_speed_cmds',Actuators,queue_size=1)
desired=rospy.Publisher('/desired_state',MultiDOFJointTrajectoryPoint,queue_size=1)
diagpub=rospy.Publisher('/controller_diagnostics',Float64MultiArray,queue_size=1)
origin=None;last_stamp=None;preparation_begin=None;last_forces=None;probe_stage=0

def state(m):
    global origin,last_stamp,preparation_begin,last_forces,probe_stage
    stamp=m.header.stamp.to_sec()
    if last_stamp is not None and stamp<=last_stamp:return
    last_stamp=stamp
    if preparation_begin is None:preparation_begin=stamp
    preparing=origin is None
    raw_t=stamp-origin if origin is not None else 0.
    t=max(0,raw_t)
    frame_index=int(round(raw_t/dt))
    i=min(frame_index+preview+(delay_steps if not preparing else 0),len(a)-2)
    i=max(0,i);ended=frame_index>=len(a)-1
    if ended:i=len(a)-1
    pos=m.pose.pose.position;vel=m.twist.twist.linear;q=m.pose.pose.orientation;omega=m.twist.twist.angular
    x=np.array([pos.x,pos.y,pos.z]);v=np.array([vel.x,vel.y,vel.z])
    R=Rotation.from_quat([q.x,q.y,q.z,q.w]).as_dcm();ww=np.array([omega.x,omega.y,omega.z])
    if preparing:
        angle0=np.linalg.norm(Rotation.from_dcm(rotations[0]@R.T).as_rotvec())
        settled=np.linalg.norm(x-P[0])<.012 and np.linalg.norm(v)<.035 and np.linalg.norm(ww)<.035 and angle0<.012
        if stamp-preparation_begin>=.6 and settled:
            origin=stamp+delay_steps*dt;preparing=False
            (out.parent/'pilot_start.json').write_text(json.dumps(dict(stamp=stamp,position=x.tolist(),velocity=v.tolist(),angular_velocity_world=ww.tolist(),quaternion=[q.x,q.y,q.z,q.w]),indent=2))
        elif stamp-preparation_begin>6:
            rospy.logerr('Initial state did not settle; abandoning this trial')
            rospy.signal_shutdown('Initial state did not settle')
            return
    if not preparing and last_forces is not None:
        for _ in range(delay_steps):
            hold=allocation@last_forces
            vn=v+dt*(hold[0]*R[:,2]+np.array([0,0,-9.81]))
            wn=ww+dt*(R@np.diag([10.,5.,10.])@hold[1:])
            if np.linalg.norm(wn)>7:wn*=7/np.linalg.norm(wn)
            x=x+dt*vn;v=vn;R=Rotation.from_rotvec(wn*dt).as_dcm()@R;ww=wn
    pref=P[i];vref=V[i] if not ended else np.zeros(3)
    aref=A[i] if not ended and not preparing else np.zeros(3)
    active_gain=1 if ended else gain
    force=aref+np.array([0,0,9.81])+active_gain*(kp*(pref-x)+kv*(vref-v))
    if preparing:force=np.array([0,0,9.81])+4*(P[0]-x)-3*v
    Rd=rotations[i].copy()
    if axis_feedback or ended or preparing:
        b=force/max(np.linalg.norm(force),1e-9)
        if b@Rd[:,2]<0:b=-b
        heading=Rd[:,0];b2=np.cross(b,heading)
        if np.linalg.norm(b2)<1e-8:b2=np.cross(b,[0,1,0])
        b2/=np.linalg.norm(b2);Rd=np.column_stack([np.cross(b2,b),b2,b])
    error=Rotation.from_dcm(Rd@R.T).as_rotvec()
    next_w=W[min(i+1,len(a)-1)] if not ended and not preparing else np.zeros(3)
    ff_alpha=(next_w-W[i])/dt if not ended else np.zeros(3)
    alpha=ff_alpha+rate*(active_gain*kr*error+next_w-ww)
    if not ended and not preparing:
        # The target for the following velocity sample already contains
        # feedforward acceleration; do not add it a second time.
        alpha=rate*(next_w+gain*kr*error-ww)
    if preparing:alpha=20*(8*error-ww)
    moment=J@(R.T@alpha)
    thrust=force@R[:,2]
    if cfg.get('pilot_rate_probe',False) and not preparing:
        if probe_stage==1:
            (out.parent/'rate_probe.json').write_text(json.dumps(dict(stamp=stamp,angular_velocity_world=ww.tolist(),angular_speed_rad_s=float(np.linalg.norm(ww)),test_roll_torque_nm=100,rotor_limit_rad_s=rotor_limit,physics_step_s=dt),indent=2));probe_stage=2
        hover_force=np.array([0,0,9.81])+4*(P[0]-x)-3*v
        hover_error=Rotation.from_dcm(rotations[0]@R.T).as_rotvec()
        moment=J@(R.T@(20*(8*hover_error-ww)));thrust=hover_force@R[:,2]
        if probe_stage==0:moment=np.array([100.,0.,0.]);probe_stage=1
    forces=inverse@np.r_[thrust,moment]
    saturated=np.sum(abs(forces)>force_limit)
    forces=np.clip(forces,-force_limit,force_limit)
    if cfg.get('pilot_open_loop',False) and not preparing and not ended:
        forces=U[i].copy()
    last_forces=forces.copy()
    speeds=np.sign(forces)*np.sqrt(abs(forces)/.001)
    # The original simulator's Update() moves every propeller toward zero
    # at 50 rad/s^2 even while external commands are used. At 50 Hz the
    # held command loses roughly 1 rad/s before the next physics update.
    speeds=np.clip(speeds+np.sign(speeds)*motor_compensation,-rotor_limit,rotor_limit)
    cmd=Actuators();cmd.header.stamp=m.header.stamp;cmd.angular_velocities=speeds.tolist();rotor.publish(cmd)
    if direct_env is not None:
        from tesse.msgs import PropSpeeds
        direct_env.send(PropSpeeds(*speeds.tolist()))
    live=out.parent/'pilot_live.json';temporary=live.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(native_stamp_s=stamp,flight_elapsed_s=max(0,t),preparing=preparing,rotor_limit_rad_s=rotor_limit)))
    temporary.replace(live)
    d=MultiDOFJointTrajectoryPoint();d.time_from_start=rospy.Duration(min(t,a['t'][-1]));tr=Transform();tv=Twist();ta=Twist()
    tr.translation.x,tr.translation.y,tr.translation.z=pref
    tr.rotation.x,tr.rotation.y,tr.rotation.z,tr.rotation.w=Q[i]
    tv.linear.x,tv.linear.y,tv.linear.z=vref;tv.angular.x,tv.angular.y,tv.angular.z=W[i]
    ta.linear.x,ta.linear.y,ta.linear.z=aref
    d.transforms=[tr];d.velocities=[tv];d.accelerations=[ta];desired.publish(d)
    applied=allocation@forces
    diagnostic=Float64MultiArray();diagnostic.data=np.r_[x-pref,v-vref,error,R.T@(ww-next_w),applied,saturated].tolist();diagpub.publish(diagnostic)

if args.ready_file:
    ready=Path(args.ready_file);ready.write_text('ready')
    while not Path(str(ready)+'.go').exists() and not rospy.is_shutdown():time.sleep(.005)
if synchronous:
    from tesse.env import Env
    from tesse.msgs import SetFrameRate,MetadataRequest,StepWithForce
    from tesse_ros_bridge.utils import parse_metadata
    from tesse_ros_bridge.msg import CollisionStats
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import String
    direct_env=Env(simulation_ip='127.0.0.1',own_ip='127.0.0.1')
    odom_pub=rospy.Publisher('/current_state',Odometry,queue_size=100)
    clock_pub=rospy.Publisher('/clock',Clock,queue_size=100,latch=True)
    collision_pub=rospy.Publisher('/tesse/collision',CollisionStats,queue_size=100)
    metadata_pub=rospy.Publisher('/tesse/native_metadata',String,queue_size=100)
    direct_env.send(SetFrameRate(50));time.sleep(.2)
    last_native_stamp=None;last_native_position=None;last_native_rotation=None
    capture_index=0
    (out.parent/'state_method.json').write_text(json.dumps(dict(position='Unmodified native Unity metadata pose',velocity='Backward difference of successive native post-step poses; raw metadata velocity is one FixedUpdate older',angular_velocity='SO(3) difference of successive native poses',dt=.02,physics_parameters_modified=False,collisions_enabled=True,rotor_limit_rad_s=rotor_limit),indent=2))
    try:
        while not rospy.is_shutdown():
            tick=time.monotonic()
            response=direct_env.request(MetadataRequest(),timeout=3)
            if response is None:raise RuntimeError('Native metadata request timed out')
            raw_metadata=response.metadata if isinstance(response.metadata,str) else bytes(response.metadata).decode('utf-8')
            metadata_pub.publish(String(data=raw_metadata))
            native=parse_metadata(response.metadata)
            stamp=native['time']
            if last_native_stamp is None or stamp>last_native_stamp+1e-8:
                m=Odometry();m.header.stamp=rospy.Time.from_sec(stamp);m.header.frame_id='world';m.child_frame_id='base_link_gt'
                p0=native['position'];v0=native['velocity'];q0=native['quaternion'];w0=native['ang_vel']
                m.pose.pose.position.x,m.pose.pose.position.y,m.pose.pose.position.z=p0[0],p0[2],p0[1]
                m.pose.pose.orientation.x,m.pose.pose.orientation.y,m.pose.pose.orientation.z,m.pose.pose.orientation.w=-q0[0],-q0[2],-q0[1],q0[3]
                m.twist.twist.linear.x,m.twist.twist.linear.y,m.twist.twist.linear.z=v0[0],v0[2],v0[1]
                m.twist.twist.angular.x,m.twist.twist.angular.y,m.twist.twist.angular.z=-w0[0],-w0[2],-w0[1]
                position=np.array([p0[0],p0[2],p0[1]])
                rotation=Rotation.from_quat([-q0[0],-q0[2],-q0[1],q0[3]]).as_dcm()
                if last_native_stamp is not None:
                    native_dt=stamp-last_native_stamp
                    velocity=(position-last_native_position)/native_dt
                    angular=Rotation.from_dcm(rotation@last_native_rotation.T).as_rotvec()/native_dt
                    m.twist.twist.linear.x,m.twist.twist.linear.y,m.twist.twist.linear.z=velocity
                    m.twist.twist.angular.x,m.twist.twist.angular.y,m.twist.twist.angular.z=angular
                last_native_stamp=stamp;last_native_position=position;last_native_rotation=rotation
                clock_pub.publish(Clock(clock=m.header.stamp));odom_pub.publish(m)
                if native['collision_status']:
                    c=CollisionStats();c.header=m.header;c.is_collision=True;c.object_name=native['collision_object'];collision_pub.publish(c)
                state(m)
                if cfg.get('pilot_capture_frames',False) and not (out.parent/'capture.done').exists():
                    request=out.parent/'capture_request.json';temp=request.with_suffix('.tmp')
                    temp.write_text(json.dumps(dict(index=capture_index,native_stamp_ns=m.header.stamp.to_nsec())))
                    temp.replace(request);begin=time.monotonic()
                    while not (out.parent/'capture.done').exists() and time.monotonic()-begin<3:
                        try:
                            ack=json.loads((out.parent/'capture_ack.json').read_text())
                            if ack['index']==capture_index:break
                        except (OSError,ValueError,KeyError):pass
                        time.sleep(.005)
                    capture_index+=1
            # Native step API: advance the unchanged 20 ms physics step
            # only after the rotor command has reached the simulator.
            time.sleep(.003)
            direct_env.send(StepWithForce())
            time.sleep(max(0,dt-(time.monotonic()-tick)))
    finally:direct_env.send(SetFrameRate(0))
else:
    rospy.Subscriber('/current_state',Odometry,state,queue_size=1,tcp_nodelay=True)
    rospy.spin()
