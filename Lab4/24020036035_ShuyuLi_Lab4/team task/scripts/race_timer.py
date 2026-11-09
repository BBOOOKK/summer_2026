#!/usr/bin/env python3
"""Ordered, aperture-checked race timing from actual simulator state.

Pure Python timing core; ROS imports are limited to run_ros(). Timestamps use
integer simulation nanoseconds. Position/velocity Hermite interpolation finds
sub-frame crossings: millisecond display does NOT imply 1 ms accuracy.
"""
import argparse
import csv
import json
import threading
from decimal import Decimal
from pathlib import Path


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


class RaceTimer:
    def __init__(self, gates, spawn=(.4, 8., .215), half_aperture=.5):
        self.gates = []
        previous = spawn
        for gate in gates:
            gate = dict(gate)
            n = gate['normal']
            if dot(n, [x-y for x, y in zip(gate['position'], previous)]) < 0:
                n = [-x for x in n]
            gate['normal'] = n
            self.gates.append(gate)
            previous = gate['position']
        self.half_aperture = half_aperture
        self.armed = False
        self.previous = None
        self.now_ns = None
        self.crossings = []
        self.collisions = []
        self.max_sample_gap_ns = 0
        self.ignored_timestamps = 0

    def arm(self):
        self.armed = True

    @property
    def finished(self):
        return bool(self.gates) and len(self.crossings) == len(self.gates)

    def update(self, stamp_ns, position, velocity=None):
        stamp_ns = int(stamp_ns)
        if self.now_ns is not None and stamp_ns <= self.now_ns:
            self.ignored_timestamps += 1
            return
        self.now_ns = stamp_ns
        old = self.previous
        self.previous = (stamp_ns, tuple(position), tuple(velocity) if velocity is not None else None)
        if not self.armed or self.finished or old is None:
            return
        t0, p0, v0 = old
        self.max_sample_gap_ns = max(self.max_sample_gap_ns, stamp_ns-t0)
        previous_fraction = -1.
        while not self.finished:
            gate = self.gates[len(self.crossings)]
            q0 = [x-y for x, y in zip(p0, gate['position'])]
            q1 = [x-y for x, y in zip(position, gate['position'])]
            d0, d1 = dot(q0, gate['normal']), dot(q1, gate['normal'])
            # Forward crossing only; exact-on-plane endpoint counts once.
            if not (d0 < 0 <= d1):
                break
            fraction = d0/(d0-d1)
            linear_fraction = fraction
            method = 'linear position interpolation'
            offset = [a+(b-a)*fraction for a, b in zip(q0, q1)]
            if v0 is not None and velocity is not None:
                dt = (stamp_ns-t0)/1e9

                def curve(u):
                    h00, h10 = 2*u**3-3*u**2+1, u**3-2*u**2+u
                    h01, h11 = -2*u**3+3*u**2, u**3-u**2
                    return [h00*a+h10*dt*va+h01*b+h11*dt*vb
                            for a,va,b,vb in zip(q0,v0,q1,velocity)]

                lo, hi = 0., 1.
                for _ in range(40):
                    mid = (lo+hi)/2
                    if dot(curve(mid),gate['normal']) < 0:
                        lo = mid
                    else:
                        hi = mid
                fraction = (lo+hi)/2
                offset = curve(fraction)
                method = 'cubic Hermite actual position + velocity'
            if fraction < previous_fraction:
                break
            h, v = dot(offset, gate['horizontal']), offset[2]
            if abs(h) >= self.half_aperture or abs(v) >= self.half_aperture:
                break
            ns = t0 + round(fraction*(stamp_ns-t0))
            start = self.crossings[0]['stamp_ns'] if self.crossings else ns
            self.crossings.append(dict(gate=len(self.crossings)+1, stamp_ns=ns,
                                       elapsed_ms=(ns-start)/1e6,
                                       horizontal_m=h, vertical_m=v,
                                       bracket_ms=(stamp_ns-t0)/1e6,
                                       interpolation=method,
                                       hermite_minus_linear_ms=(fraction-linear_fraction)*(stamp_ns-t0)/1e6))
            previous_fraction = fraction

    def collision(self, stamp_ns, name):
        if not self.armed:
            return
        # Ground contact at spawn is normal. Any obstacle contact or ground
        # contact after gate 1 invalidates the complete recorded trial.
        if name.startswith('Floor') and (not self.crossings or stamp_ns < self.crossings[0]['stamp_ns']):
            return
        self.collisions.append(dict(stamp_ns=int(stamp_ns), object=name))

    def snapshot(self):
        start = self.crossings[0]['stamp_ns'] if self.crossings else None
        end = self.crossings[-1]['stamp_ns'] if self.finished else None
        elapsed_ns = (end if end is not None else self.now_ns)-start if start is not None else 0
        ms = (elapsed_ns+500000)//1000000
        phase = 'FINISHED' if self.finished else ('RUNNING' if start is not None else 'WAITING FOR GATE 1')
        return dict(phase=phase, gates_passed=len(self.crossings), gates_total=len(self.gates),
                    sample_stamp_ns=self.now_ns,
                    elapsed_ns=elapsed_ns, elapsed_ms=elapsed_ns/1e6,
                    display='%d.%03d s' % (ms//1000, ms % 1000),
                    start_stamp_ns=start, finish_stamp_ns=end, crossings=list(self.crossings),
                    valid=self.finished and not self.collisions,
                    collisions=list(self.collisions), max_sample_gap_ms=self.max_sample_gap_ns/1e6,
                    ignored_timestamps=self.ignored_timestamps,
                    clock='Odometry.header.stamp: simulator time',
                    precision_note='1 ms display; sub-frame interpolation of sampled actual positions/velocities; not native 1 ms measurement accuracy')


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def replay(directory, gates):
    timer = RaceTimer(gates)
    timer.arm()
    with (directory/'telemetry.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            ns = int(Decimal(row['stamp'])*1000000000)
            timer.update(ns, [float(row[k]) for k in ('x', 'y', 'z')], [float(row[k]) for k in ('vx','vy','vz')])
    data_path = directory/'flight_data.json'
    if data_path.exists():
        flight = json.loads(data_path.read_text())
        for event in flight['collision_events']:
            if not event['is_collision'] or event['stamp'] < flight['first_desired_stamp']:
                continue
            ns = round(event['stamp']*1e9)
            if event['object'].startswith('Floor') and (not timer.crossings or ns < timer.crossings[0]['stamp_ns']):
                continue
            timer.collision(ns, event['object'])
    result = timer.snapshot()
    result['collision_data_present'] = data_path.exists()
    result['valid'] = result['valid'] and result['collision_data_present']
    atomic_json(directory/'race_timer_replay.json', result)
    print(json.dumps(dict(case=str(directory), **{k:result[k] for k in ('phase','gates_passed','elapsed_ms','valid','max_sample_gap_ms')})))
    return result


def run_ros(args, gates):
    import rospy
    from nav_msgs.msg import Odometry
    from trajectory_msgs.msg import MultiDOFJointTrajectoryPoint
    from std_msgs.msg import String
    from tesse_ros_bridge.msg import CollisionStats
    timer, lock = RaceTimer(gates), threading.Lock()
    rospy.init_node('race_timer')
    publisher = rospy.Publisher('/race_timer', String, queue_size=1, latch=True)

    def save():
        value = timer.snapshot()
        atomic_json(args.output, value)
        if args.live_output:
            atomic_json(args.live_output, value)
        publisher.publish(String(data=json.dumps(value)))

    def desired(_):
        with lock:
            timer.arm()

    def state(msg):
        with lock:
            p = msg.pose.pose.position
            v = msg.twist.twist.linear
            timer.update(msg.header.stamp.to_nsec(), (p.x, p.y, p.z), (v.x,v.y,v.z))
            save()

    def collision(msg):
        with lock:
            if msg.is_collision:
                timer.collision(msg.header.stamp.to_nsec(), msg.object_name)
                save()

    save()
    rospy.Subscriber('/desired_state', MultiDOFJointTrajectoryPoint, desired, queue_size=1)
    rospy.Subscriber('/current_state', Odometry, state, queue_size=100)
    rospy.Subscriber('/tesse/collision', CollisionStats, collision, queue_size=100)
    rospy.spin()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gates', required=True)
    p.add_argument('--replay', type=Path)
    p.add_argument('--output')
    p.add_argument('--live-output')
    args = p.parse_args()
    gates = json.loads(Path(args.gates).read_text())
    if args.replay:
        replay(args.replay, gates)
    else:
        if not args.output:
            p.error('--output is required for ROS mode')
        run_ros(args, gates)
