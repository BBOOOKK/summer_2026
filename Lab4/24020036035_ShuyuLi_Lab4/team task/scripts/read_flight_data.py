#!/usr/bin/env python3
"""Read flight timing, collisions, and trajectory measurements from a rosbag."""
from pathlib import Path
import json,collections,argparse
import rosbag
import numpy as np
from tesse_ros_bridge.utils import parse_metadata
base=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args()
gates=json.loads((base/'results/gates.json').read_text())
for folder in ([base/'results'/args.case] if args.case else sorted((base/'results').iterdir())):
    bag=folder/'race.bag'
    if not bag.exists():continue
    counts=collections.Counter();collisions=[];native_collisions=[];first_desired=None;last_desired=None
    with rosbag.Bag(str(bag)) as b:
        duration=b.get_end_time()-b.get_start_time()
        for topic,msg,stamp in b.read_messages():
            counts[topic]+=1
            if topic=='/desired_state':
                if first_desired is None:first_desired=stamp.to_sec()
                last_desired=stamp.to_sec()
            if topic.endswith('/collision'):
                collisions.append({'stamp':msg.header.stamp.to_sec(),'object':msg.object_name,'is_collision':msg.is_collision})
            if topic=='/tesse/native_metadata':
                native=parse_metadata(msg.data)
                if native['collision_status']:
                    native_collisions.append({'stamp':native['time'],'object':native['collision_object'],'is_collision':True})
    if counts['/tesse/native_metadata']:
        collisions=native_collisions
    result={'duration_s':duration,'topic_message_counts':dict(counts),'first_desired_stamp':first_desired,
            'last_desired_stamp':last_desired,'collision_events':collisions}
    plan=folder/'plan.csv'
    if plan.exists():
        a=np.genfromtxt(plan,delimiter=',',names=True);times=np.loadtxt(str(plan)+'.times')[:len(gates)]
        xyz=np.array([[np.interp(t,a['t'],a[c]) for c in ['x','y','z']] for t in times])
        error=np.linalg.norm(xyz-np.array([g['position'] for g in gates]),axis=1)
        result.update(plan_sampled_waypoint_error_m=error.tolist(),max_sampled_waypoint_error_m=float(error.max()),
                      start_velocity_norm=float(np.linalg.norm([a[c][0] for c in ['vx','vy','vz']])),
                      end_velocity_norm=float(np.linalg.norm([a[c][-1] for c in ['vx','vy','vz']])),
                      max_reference_speed=float(np.max(np.sqrt(a['vx']**2+a['vy']**2+a['vz']**2))),
                      max_reference_acceleration=float(np.max(np.sqrt(a['ax']**2+a['ay']**2+a['az']**2))))
    (folder/'flight_data.json').write_text(json.dumps(result,indent=2))
    print(folder.name,dict(counts),'collisions',len(collisions))
