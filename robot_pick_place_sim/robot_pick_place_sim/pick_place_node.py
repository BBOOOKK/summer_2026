"""ROS 2 fixed-point pick-and-place task controller."""

import csv
import json
from pathlib import Path
import threading
import time
from uuid import uuid4

from action_msgs.msg import GoalStatus
from control_msgs.action import FollowJointTrajectory
import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectoryPoint

from .safety import SafetyError, validate_task


ARM_JOINTS = [f'joint{i}' for i in range(1, 7)]


class PickPlaceNode(Node):
    """Execute a guarded, reusable pick-and-place sequence."""

    def __init__(self):
        super().__init__('pick_place')
        defaults = {
            'simulation': True, 'auto_start': True,
            'auto_start_delay_sec': 5.0, 'action_timeout_sec': 25.0,
            'motion_duration_sec': 2.0, 'gripper_duration_sec': 2.0,
            'safe_height_m': 0.12, 'reach_min_m': 0.08,
            'reach_max_m': 0.38, 'table_z_m': 0.0,
            'object_height_m': 0.04, 'gripper_open_rad': -0.35,
            'gripper_closed_rad': 0.15, 'log_directory': 'logs',
            'attachment_mode': 'service',
            'attach_service': '/grasp/attach',
            'detach_service': '/grasp/detach',
            'grasp_service_timeout_sec': 6.0,
            'require_collision_monitor': True,
            'collision_readiness_service': '/collision_monitor/readiness',
            'collision_reset_service': '/collision_monitor/reset',
            'collision_readiness_timeout_sec': 10.0,
            'pick_point_xyz': [0.22, 0.12, 0.02],
            'place_point_xyz': [0.20, -0.16, 0.02],
            'home_joints': [0.0] * 6,
            'pick_above_joints': [
                0.494819, 0.444935, -0.142174,
                -0.030279, -0.294663, 0.028902],
            'pick_joints': [
                0.464516, 1.201020, -0.114062,
                -0.096231, -1.080543, 0.044709],
            'place_above_joints': [
                -0.671786, 0.551014, -0.295827,
                0.031529, -0.247085, -0.030507],
            'place_joints': [
                -0.640737, 1.260058, -0.265817,
                0.106509, -0.988509, -0.057984],
            'joint_lower_limits': [
                -2.792527, -1.3089, -3.0543,
                -2.7052, -2.0071, -3.14],
            'joint_upper_limits': [
                2.792527, 2.0943, 1.1344,
                2.7052, 2.0071, 3.14],
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self._config = {name: self.get_parameter(name).value for name in defaults}
        self._arm = ActionClient(
            self, FollowJointTrajectory,
            '/arm_controller/follow_joint_trajectory')
        self._gripper = ActionClient(
            self, FollowJointTrajectory,
            '/gripper_controller/follow_joint_trajectory')
        self._attach = self.create_client(
            Trigger, str(self._config['attach_service']))
        self._detach = self.create_client(
            Trigger, str(self._config['detach_service']))
        self._collision_readiness = self.create_client(
            Trigger, str(self._config['collision_readiness_service']))
        self._safety_callbacks = ReentrantCallbackGroup()
        self._collision_reset = self.create_client(
            Trigger, str(self._config['collision_reset_service']),
            callback_group=self._safety_callbacks)
        self._state_pub = self.create_publisher(String, '/pick_place/state', 10)
        self._grasp_pub = self.create_publisher(Bool, '/pick_place/grasped', 10)
        self.create_subscription(JointState, '/joint_states', self._joint_state, 20)
        self.create_service(Trigger, '/pick_place/start', self._start_service)
        self.create_service(Trigger, '/pick_place/stop', self._stop_service)
        self.create_service(
            Trigger, '/pick_place/collision_stop',
            self._collision_stop_service)
        self.create_service(
            Trigger, '/pick_place/reset_safety', self._reset_safety_service,
            callback_group=self._safety_callbacks)
        self._lock = threading.Lock()
        self._running = False
        self._safety_latched = False
        self._safety_reason = ''
        self._stop_requested = threading.Event()
        self._active_goal = None
        self._run_id = ''
        self._trajectory_path = None
        self._log_dir = Path(str(self._config['log_directory'])).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._publish_state('IDLE', 'ready; call /pick_place/start')
        if self._config['auto_start']:
            self._auto_timer = self.create_timer(
                float(self._config['auto_start_delay_sec']), self._auto_start)

    def _auto_start(self):
        self.destroy_timer(self._auto_timer)
        self._begin_run()

    def _start_service(self, _request, response):
        accepted, message = self._begin_run()
        response.success = accepted
        response.message = message
        return response

    def _stop_service(self, _request, response):
        self._request_safety_stop('operator safe stop requested')
        response.success = True
        response.message = 'safety stop latched; explicit reset is required'
        return response

    def _collision_stop_service(self, _request, response):
        self._request_safety_stop('collision monitor requested safe stop')
        response.success = True
        response.message = 'collision safety stop latched'
        return response

    def _reset_safety_service(self, _request, response):
        with self._lock:
            if self._running:
                response.success = False
                response.message = 'cannot reset safety while task is running'
                return response
        timeout = float(self._config['collision_readiness_timeout_sec'])
        if not self._collision_reset.wait_for_service(timeout_sec=timeout):
            response.success = False
            response.message = 'collision monitor reset service unavailable'
            return response
        try:
            monitor_response = self._await(
                self._collision_reset.call_async(Trigger.Request()), timeout,
                'collision monitor reset timed out')
        except (RuntimeError, TimeoutError) as exc:
            response.success = False
            response.message = str(exc)
            return response
        if monitor_response is None or not monitor_response.success:
            response.success = False
            response.message = (
                'collision monitor rejected reset: '
                + ('empty response' if monitor_response is None
                   else monitor_response.message))
            return response
        with self._lock:
            self._safety_latched = False
            self._safety_reason = ''
            self._stop_requested.clear()
        self._publish_state('IDLE', 'safety latch reset by operator')
        response.success = True
        response.message = 'safety latch reset; verify workcell before restart'
        return response

    def _request_safety_stop(self, reason):
        with self._lock:
            self._safety_latched = True
            self._safety_reason = reason
            running = self._running
        self._stop_requested.set()
        if self._active_goal is not None:
            self._active_goal.cancel_goal_async()
        if self._detach.service_is_ready():
            self._detach.call_async(Trigger.Request())
        state = 'STOPPING' if running else 'SAFE_STOP'
        self._publish_state(state, reason)

    def _begin_run(self):
        with self._lock:
            if self._safety_latched:
                return False, (
                    'safety stop is latched; call /pick_place/reset_safety: '
                    f'{self._safety_reason}')
            if self._running:
                return False, 'task is already running'
            self._running = True
        self._stop_requested.clear()
        self._run_id = time.strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6]
        self._trajectory_path = self._log_dir / f'trajectory_{self._run_id}.csv'
        with self._trajectory_path.open('w', newline='', encoding='utf-8') as stream:
            csv.writer(stream).writerow(['time', 'name', 'position', 'velocity'])
        threading.Thread(target=self._execute, daemon=True).start()
        return True, f'task {self._run_id} started'

    def _execute(self):
        started = time.time()
        result, detail = 'FAILED', ''
        try:
            self._publish_state('VALIDATING', 'checking reach and joint limits')
            validate_task(self._config)
            for client, label in ((self._arm, 'arm'), (self._gripper, 'gripper')):
                if not client.wait_for_server(timeout_sec=5.0):
                    raise RuntimeError(f'{label} trajectory action is unavailable')
            self._require_collision_readiness()
            sequence = (
                ('OPEN_GRIPPER', self._gripper_move, self._config['gripper_open_rad']),
                ('HOME', self._arm_move, self._config['home_joints']),
                ('ABOVE_PICK', self._arm_move, self._config['pick_above_joints']),
                ('DESCEND_PICK', self._arm_move, self._config['pick_joints']),
                ('GRASP', self._gripper_move, self._config['gripper_closed_rad']),
                ('ATTACH_OBJECT', self._attach_object, None),
                ('LIFT_OBJECT', self._arm_move, self._config['pick_above_joints']),
                ('ABOVE_PLACE', self._arm_move, self._config['place_above_joints']),
                ('DESCEND_PLACE', self._arm_move, self._config['place_joints']),
                ('DETACH_OBJECT', self._detach_object, None),
                ('RELEASE', self._gripper_move, self._config['gripper_open_rad']),
                ('RETREAT', self._arm_move, self._config['place_above_joints']),
                ('RETURN_HOME', self._arm_move, self._config['home_joints']),
            )
            for state, operation, target in sequence:
                if self._stop_requested.is_set():
                    raise RuntimeError('task stopped by operator')
                self._publish_state(state, 'executing')
                operation(target)
                if state == 'ATTACH_OBJECT':
                    self._grasp_pub.publish(Bool(data=True))
                    self._publish_state(
                        'GRASP_CONFIRMED',
                        'bilateral contact accepted; physical joint attached')
                elif state == 'DETACH_OBJECT':
                    self._grasp_pub.publish(Bool(data=False))
            result, detail = 'SUCCEEDED', 'pick-and-place sequence completed'
            self._publish_state(result, detail)
        except (SafetyError, RuntimeError, TimeoutError) as exc:
            detail = str(exc)
            self._fail_safe(detail)
        except Exception as exc:  # keep unexpected failures fail-safe
            detail = f'unexpected error: {exc}'
            self._fail_safe(detail)
        finally:
            self._write_jsonl('results.jsonl', {
                'result': result, 'detail': detail,
                'duration_sec': round(time.time() - started, 3),
                'trajectory': str(self._trajectory_path),
            })
            with self._lock:
                self._active_goal = None
                self._running = False

    def _fail_safe(self, detail):
        with self._lock:
            self._safety_latched = True
            self._safety_reason = detail
        self._grasp_pub.publish(Bool(data=False))
        if self._detach.service_is_ready():
            self._detach.call_async(Trigger.Request())
        self._publish_state('SAFE_STOP', detail)
        self._write_jsonl('errors.jsonl', {'error': detail})
        self.get_logger().error(detail)

    def _require_collision_readiness(self):
        if not bool(self._config['require_collision_monitor']):
            return
        if not self._collision_readiness.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('collision monitor readiness service unavailable')
        deadline = time.monotonic() + float(
            self._config['collision_readiness_timeout_sec'])
        detail = 'no readiness response'
        while time.monotonic() < deadline:
            response = self._await(
                self._collision_readiness.call_async(Trigger.Request()), 2.0,
                'collision monitor readiness timed out')
            if response is not None and response.success:
                return
            detail = 'empty response' if response is None else response.message
            try:
                if json.loads(detail).get('unsafe_latched'):
                    break
            except (json.JSONDecodeError, AttributeError):
                pass
            time.sleep(0.2)
        raise RuntimeError(f'collision monitor not ready: {detail}')

    def _arm_move(self, positions):
        self._send_trajectory(
            self._arm, ARM_JOINTS, positions,
            float(self._config['motion_duration_sec']))

    def _gripper_move(self, position):
        self._send_trajectory(
            self._gripper, ['right_finger_joint'], [float(position)],
            float(self._config['gripper_duration_sec']))

    def _attach_object(self, _unused=None):
        if str(self._config['attachment_mode']).lower() != 'service':
            raise RuntimeError('physical service attachment is required')
        self._call_grasp_service(self._attach, 'attach')

    def _detach_object(self, _unused=None):
        self._call_grasp_service(self._detach, 'detach')

    def _call_grasp_service(self, client, operation):
        timeout = float(self._config['grasp_service_timeout_sec'])
        if not client.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f'grasp {operation} service is unavailable')
        response = self._await(
            client.call_async(Trigger.Request()), timeout,
            f'grasp {operation} service timed out')
        if response is None or not response.success:
            reason = 'empty response' if response is None else response.message
            raise RuntimeError(f'physical grasp {operation} failed: {reason}')

    def _send_trajectory(self, client, names, positions, duration):
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = names
        point = JointTrajectoryPoint()
        point.positions = [float(value) for value in positions]
        point.time_from_start = Duration(seconds=duration).to_msg()
        goal.trajectory.points = [point]
        send_future = client.send_goal_async(goal)
        goal_handle = self._await(send_future, 3.0, 'goal acknowledgement timeout')
        if not goal_handle.accepted:
            raise RuntimeError(f'trajectory rejected for {names}')
        self._active_goal = goal_handle
        result_future = goal_handle.get_result_async()
        deadline = time.monotonic() + float(self._config['action_timeout_sec'])
        while not result_future.done():
            if self._stop_requested.wait(0.05):
                goal_handle.cancel_goal_async()
                self._active_goal = None
                raise RuntimeError('trajectory interrupted by latched safety stop')
            if time.monotonic() >= deadline:
                self._active_goal = None
                raise TimeoutError(f'trajectory timeout for {names}')
        exception = result_future.exception()
        if exception is not None:
            self._active_goal = None
            raise RuntimeError(str(exception))
        wrapped = result_future.result()
        self._active_goal = None
        if wrapped.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(
                f'trajectory failed for {names}; action status={wrapped.status}')

    @staticmethod
    def _await(future, timeout, message):
        event = threading.Event()
        future.add_done_callback(lambda _future: event.set())
        if not event.wait(timeout):
            raise TimeoutError(message)
        exception = future.exception()
        if exception is not None:
            raise RuntimeError(str(exception))
        return future.result()

    def _joint_state(self, message):
        if not self._running or self._trajectory_path is None:
            return
        timestamp = self.get_clock().now().nanoseconds / 1e9
        velocities = list(message.velocity) or [''] * len(message.name)
        with self._trajectory_path.open('a', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            for name, position, velocity in zip(
                    message.name, message.position, velocities):
                writer.writerow([f'{timestamp:.6f}', name, position, velocity])

    def _publish_state(self, state, detail):
        payload = {
            'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'run_id': self._run_id, 'state': state, 'detail': detail,
        }
        self._state_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        self._write_jsonl('events.jsonl', payload)
        self.get_logger().info(f'[{state}] {detail}')

    def _write_jsonl(self, filename, values):
        record = {
            'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'run_id': self._run_id, **values,
        }
        with (self._log_dir / filename).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def main(args=None):
    rclpy.init(args=args)
    node = PickPlaceNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            executor.shutdown()
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
