"""Reset and independently record the Gazebo target object.

The node deliberately never writes the object pose during transport.  A single
``SetEntityState`` call is allowed at the beginning of each run to restore the
repeatable A-point initial condition; physical carrying is owned by the
contact-gated detachable-joint plugin.
"""

import csv
import json
import math
from pathlib import Path
import time

from gazebo_msgs.msg import EntityState
from gazebo_msgs.srv import GetEntityState, SetEntityState
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ObjectManager(Node):
    """Reset the cube once per run and log its measured world trajectory."""

    def __init__(self):
        super().__init__('object_manager')
        self.declare_parameter('entity_name', 'target_object')
        self.declare_parameter('world_frame', 'world')
        # The 35 mm cube rests exactly on the 0.75 m table in world space.
        self.declare_parameter('initial_pose', [0.22, 0.12, 0.7675])
        self.declare_parameter('initial_yaw_rad', 0.499)
        self.declare_parameter('sample_rate_hz', 50.0)
        self.declare_parameter('log_directory', 'logs')
        self._entity = self.get_parameter('entity_name').value
        self._world = self.get_parameter('world_frame').value
        self._initial = self.get_parameter('initial_pose').value
        self._initial_yaw = float(
            self.get_parameter('initial_yaw_rad').value)
        self._log_dir = Path(
            str(self.get_parameter('log_directory').value)).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._set_state = self.create_client(
            SetEntityState, '/gazebo/set_entity_state')
        self._get_state = self.create_client(
            GetEntityState, '/gazebo/get_entity_state')
        self._status_pub = self.create_publisher(
            String, '/object_manager/state', 10)
        self.create_subscription(
            String, '/pick_place/state', self._task_state, 20)
        self._stage = 'IDLE'
        self._run_id = ''
        self._trajectory_path = None
        self._query_pending = False
        self._reset_writes = 0
        self._transport_writes = 0
        rate = max(1.0, float(self.get_parameter('sample_rate_hz').value))
        self.create_timer(1.0 / rate, self._sample)

    def _task_state(self, message):
        try:
            payload = json.loads(message.data)
        except (json.JSONDecodeError, AttributeError):
            return
        self._stage = str(payload.get('state', 'UNKNOWN'))
        run_id = str(payload.get('run_id', ''))
        if self._stage == 'VALIDATING' and run_id and run_id != self._run_id:
            self._run_id = run_id
            self._trajectory_path = (
                self._log_dir / f'object_trajectory_{run_id}.csv')
            with self._trajectory_path.open(
                    'w', newline='', encoding='utf-8') as stream:
                csv.writer(stream).writerow([
                    'wall_time', 'ros_time', 'run_id', 'stage',
                    'x', 'y', 'z', 'qx', 'qy', 'qz', 'qw',
                    'vx', 'vy', 'vz',
                ])
            self._reset_once()

    def _reset_once(self):
        if not self._set_state.service_is_ready():
            self.get_logger().error('Gazebo SetEntityState is unavailable')
            return
        request = SetEntityState.Request()
        request.state = EntityState()
        request.state.name = self._entity
        request.state.reference_frame = self._world
        request.state.pose.position.x = float(self._initial[0])
        request.state.pose.position.y = float(self._initial[1])
        request.state.pose.position.z = float(self._initial[2])
        request.state.pose.orientation.z = math.sin(self._initial_yaw / 2.0)
        request.state.pose.orientation.w = math.cos(self._initial_yaw / 2.0)
        self._reset_writes += 1
        future = self._set_state.call_async(request)
        future.add_done_callback(self._reset_complete)

    def _reset_complete(self, future):
        response = future.result()
        ok = response is not None and response.success
        payload = {
            'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'run_id': self._run_id,
            'event': 'RESET_AT_A',
            'success': ok,
            'reset_writes': self._reset_writes,
            'transport_set_state_writes': self._transport_writes,
        }
        self._status_pub.publish(String(data=json.dumps(payload)))
        if not ok:
            self.get_logger().error('failed to reset target object at A')

    def _sample(self):
        if not self._run_id or self._trajectory_path is None:
            return
        if self._query_pending or not self._get_state.service_is_ready():
            return
        request = GetEntityState.Request()
        request.name = self._entity
        request.reference_frame = self._world
        self._query_pending = True
        future = self._get_state.call_async(request)
        future.add_done_callback(self._sample_complete)

    def _sample_complete(self, future):
        self._query_pending = False
        response = future.result()
        if response is None or not response.success or self._trajectory_path is None:
            return
        pose = response.state.pose
        twist = response.state.twist
        with self._trajectory_path.open(
                'a', newline='', encoding='utf-8') as stream:
            csv.writer(stream).writerow([
                f'{time.time():.6f}',
                f'{self.get_clock().now().nanoseconds / 1e9:.6f}',
                self._run_id, self._stage,
                pose.position.x, pose.position.y, pose.position.z,
                pose.orientation.x, pose.orientation.y,
                pose.orientation.z, pose.orientation.w,
                twist.linear.x, twist.linear.y, twist.linear.z,
            ])


def main(args=None):
    rclpy.init(args=args)
    node = ObjectManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
