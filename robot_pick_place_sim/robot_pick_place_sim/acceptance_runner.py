"""Run and record the required five-cycle simulation acceptance test."""

import json
from pathlib import Path
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


class AcceptanceRunner(Node):
    """Sequentially request runs and count terminal states."""

    def __init__(self):
        super().__init__('acceptance_runner')
        self.declare_parameter('repeat_count', 5)
        self.declare_parameter('task_timeout_sec', 90.0)
        self.declare_parameter('between_runs_sec', 2.0)
        self.declare_parameter('log_directory', 'logs')
        self._repeat_count = int(self.get_parameter('repeat_count').value)
        self._timeout = float(self.get_parameter('task_timeout_sec').value)
        self._delay = float(self.get_parameter('between_runs_sec').value)
        self._log_dir = Path(
            str(self.get_parameter('log_directory').value)).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._start = self.create_client(Trigger, '/pick_place/start')
        self._condition = threading.Condition()
        self._terminal = None
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
                self._detail = payload.get('detail', '')
                self._condition.notify_all()

    def _run(self):
        records = []
        if not self._start.wait_for_service(timeout_sec=20.0):
            records.append({'run': 0, 'result': 'FAILED',
                            'detail': 'start service unavailable'})
            self._finish(records)
            return
        for index in range(1, self._repeat_count + 1):
            with self._condition:
                self._terminal = None
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
            records.append({
                'run': index, 'result': result, 'detail': detail,
                'duration_sec': round(time.time() - started, 3),
            })
            self.get_logger().info(f'acceptance run {index}: {result}')
            time.sleep(self._delay)
        self._finish(records)

    def _finish(self, records):
        succeeded = sum(item['result'] == 'SUCCEEDED' for item in records)
        summary = {
            'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'required_runs': self._repeat_count,
            'succeeded': succeeded,
            'passed': succeeded >= max(1, self._repeat_count - 1),
            'runs': records,
        }
        path = self._log_dir / 'acceptance_summary.json'
        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        self.get_logger().info(
            f"acceptance: {succeeded}/{self._repeat_count}; "
            f"passed={summary['passed']}; report={path}")
        self._shutdown_timer = self.create_timer(1.0, rclpy.shutdown)


def main(args=None):
    rclpy.init(args=args)
    node = AcceptanceRunner()
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
