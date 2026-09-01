"""Run and record the required five-cycle simulation acceptance test."""

import json
from pathlib import Path
import threading
import time

from gazebo_msgs.srv import GetEntityState
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .evidence import analyze_acceptance


class AcceptanceRunner(Node):
    """Sequentially request runs and count terminal states."""

    def __init__(self):
        super().__init__('acceptance_runner')
        self.declare_parameter('repeat_count', 5)
        self.declare_parameter('task_timeout_sec', 90.0)
        self.declare_parameter('between_runs_sec', 2.0)
        self.declare_parameter('log_directory', 'logs')
        self.declare_parameter('object_name', 'target_object')
        self.declare_parameter('place_point_world', [0.20, -0.16, 0.77])
        self.declare_parameter('place_tolerance_m', 0.07)
        self._repeat_count = int(self.get_parameter('repeat_count').value)
        self._timeout = float(self.get_parameter('task_timeout_sec').value)
        self._delay = float(self.get_parameter('between_runs_sec').value)
        self._log_dir = Path(
            str(self.get_parameter('log_directory').value)).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._start = self.create_client(Trigger, '/pick_place/start')
        self._get_entity = self.create_client(
            GetEntityState, '/gazebo/get_entity_state')
        self._object_name = self.get_parameter('object_name').value
        self._place_world = self.get_parameter('place_point_world').value
        self._place_tolerance = float(
            self.get_parameter('place_tolerance_m').value)
        self._condition = threading.Condition()
        self._terminal = None
        self._terminal_run_id = ''
        self._detail = ''
        self.create_subscription(String, '/pick_place/state', self._state, 20)
        threading.Thread(target=self._run, daemon=True).start()

    def _state(self, message):
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            return
        if payload.get('state') in ('SUCCEEDED', 'SAFE_STOP'):
            with self._condition:
                self._terminal = payload['state']
                self._terminal_run_id = str(payload.get('run_id', ''))
                self._detail = payload.get('detail', '')
                self._condition.notify_all()

    def _run(self):
        records = []
        if not self._start.wait_for_service(timeout_sec=20.0):
            records.append({'run': 0, 'result': 'FAILED',
                            'detail': 'start service unavailable'})
            self._finish(records)
            return
        if not self._get_entity.wait_for_service(timeout_sec=20.0):
            records.append({'run': 0, 'result': 'FAILED',
                            'detail': 'Gazebo entity-state service unavailable'})
            self._finish(records)
            return
        for index in range(1, self._repeat_count + 1):
            with self._condition:
                self._terminal = None
                self._terminal_run_id = ''
                self._detail = ''
            started = time.time()
            future = self._start.call_async(Trigger.Request())
            event = threading.Event()
            future.add_done_callback(lambda _future: event.set())
            if not event.wait(5.0) or not future.result().success:
                detail = 'start request timed out or was rejected'
                if future.done() and future.result() is not None:
                    detail = future.result().message
                records.append({'run': index, 'result': 'FAILED', 'detail': detail})
                continue
            with self._condition:
                completed = self._condition.wait_for(
                    lambda: self._terminal is not None, timeout=self._timeout)
                result = self._terminal if completed else 'TIMEOUT'
                detail = self._detail if completed else 'task timeout'
                run_id = self._terminal_run_id if completed else ''
            position = None
            if result == 'SUCCEEDED':
                position, placement_detail = self._verify_placement()
                if placement_detail:
                    result, detail = 'FAILED_PLACEMENT', placement_detail
            records.append({
                'run': index, 'result': result, 'detail': detail,
                'run_id': run_id,
                'duration_sec': round(time.time() - started, 3),
                'object_position_world': position,
            })
            self.get_logger().info(f'acceptance run {index}: {result}')
            time.sleep(self._delay)
        self._finish(records)

    def _verify_placement(self):
        request = GetEntityState.Request()
        request.name = self._object_name
        request.reference_frame = 'world'
        future = self._get_entity.call_async(request)
        event = threading.Event()
        future.add_done_callback(lambda _future: event.set())
        if not event.wait(5.0):
            return None, 'entity-state query timed out'
        response = future.result()
        if response is None or not response.success:
            return None, 'entity-state query failed'
        point = response.state.pose.position
        position = [round(point.x, 4), round(point.y, 4), round(point.z, 4)]
        dx = point.x - self._place_world[0]
        dy = point.y - self._place_world[1]
        if (dx * dx + dy * dy) ** 0.5 > self._place_tolerance:
            return position, (
                f'object outside B zone: position={position}, '
                f'tolerance={self._place_tolerance:.3f} m')
        if not 0.74 <= point.z <= 0.85:
            return position, f'object height is unsafe: z={point.z:.3f} m'
        return position, ''

    def _finish(self, records):
        succeeded = sum(item['result'] == 'SUCCEEDED' for item in records)
        time.sleep(1.0)
        evidence = analyze_acceptance(
            self._log_dir,
            [item['run_id'] for item in records
             if item['result'] == 'SUCCEEDED' and item.get('run_id')],
            place_xyz=tuple(self._place_world),
            place_tolerance=self._place_tolerance)
        summary = {
            'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'required_runs': self._repeat_count,
            'succeeded': succeeded,
            'passed': (
                succeeded >= max(1, self._repeat_count - 1)
                and evidence['passed']),
            'runs': records,
            'evidence': evidence,
        }
        path = self._log_dir / 'acceptance_summary.json'
        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        self.get_logger().info(
            f"acceptance: {succeeded}/{self._repeat_count}; "
            f"passed={summary['passed']}; report={path}")
        rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = AcceptanceRunner()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
