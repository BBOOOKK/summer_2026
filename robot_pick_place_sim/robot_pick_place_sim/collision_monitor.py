"""Runtime contact supervision, diagnostics, and fail-closed safe stop."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from gazebo_msgs.msg import ContactsState
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .contact_policy import ContactPolicy, EpisodeGate, Verdict, source_readiness


CONTACT_TOPICS = (
    '/gazebo/contacts/table',
    '/gazebo/contacts/target',
    '/gazebo/contacts/robot',
)


def _timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')


class CollisionMonitor(Node):
    """Classify live Gazebo contacts and request one latched safe stop."""

    def __init__(self):
        super().__init__('collision_monitor')
        self.declare_parameter('log_directory', 'logs')
        self.declare_parameter('source_timeout_sec', 2.0)
        self.declare_parameter('startup_grace_sec', 8.0)
        self.declare_parameter('episode_gap_sec', 0.5)
        self.declare_parameter('safe_stop_service', '/pick_place/collision_stop')
        self._log_dir = Path(
            str(self.get_parameter('log_directory').value)).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._timeout = float(self.get_parameter('source_timeout_sec').value)
        self._grace = float(self.get_parameter('startup_grace_sec').value)
        self._started = time.monotonic()
        self._stage = 'UNKNOWN'
        self._run_id = ''
        self._policy = ContactPolicy()
        self._gate = EpisodeGate(
            float(self.get_parameter('episode_gap_sec').value))
        self._counts = {topic: 0 for topic in CONTACT_TOPICS}
        self._last_seen = {topic: None for topic in CONTACT_TOPICS}
        self._unsafe_latched = False
        self._source_fault = None
        self._last_forbidden = None
        self._last_forbidden_seen = None
        self._stop_requested = False
        self._stop_result = 'not_requested'
        self._stats = {
            'messages_received': 0,
            'contact_states_raw': 0,
            'allowed_observations': 0,
            'forbidden_observations': 0,
            'ignored_observations': 0,
            'events_written': 0,
            'safe_stop_calls': 0,
            'safe_stop_successes': 0,
            'safe_stop_failures': 0,
        }
        qos = QoSProfile(depth=100)
        self._subscriptions_by_topic = []
        for topic in CONTACT_TOPICS:
            subscription = self.create_subscription(
                ContactsState, topic,
                lambda message, source=topic: self._contacts(source, message),
                qos)
            self._subscriptions_by_topic.append(subscription)
        self.create_subscription(
            String, '/pick_place/state', self._task_state, 20)
        self._event_pub = self.create_publisher(
            String, '/collision_monitor/events', 20)
        self._diagnostics_pub = self.create_publisher(
            DiagnosticArray, '/diagnostics', 10)
        self._stop = self.create_client(
            Trigger, str(self.get_parameter('safe_stop_service').value))
        self.create_service(
            Trigger, '/collision_monitor/readiness', self._readiness_service)
        self.create_service(
            Trigger, '/collision_monitor/reset', self._reset_service)
        self.create_timer(0.2, self._health_check)
        self.create_timer(1.0, self._write_summary)

    def _task_state(self, message):
        try:
            payload = json.loads(message.data)
            self._stage = str(payload.get('state', 'UNKNOWN'))
            self._run_id = str(payload.get('run_id', self._run_id))
        except (json.JSONDecodeError, AttributeError):
            self._stage = 'UNKNOWN'

    def _contacts(self, topic, message):
        now = time.monotonic()
        self._counts[topic] += 1
        self._last_seen[topic] = now
        self._stats['messages_received'] += 1
        self._stats['contact_states_raw'] += len(message.states)
        seen_pairs = set()
        for state in message.states:
            decision = self._policy.classify(
                state.collision1_name, state.collision2_name, self._stage)
            if decision.pair in seen_pairs:
                continue
            seen_pairs.add(decision.pair)
            key = f'{decision.verdict.value}_observations'
            self._stats[key] += 1
            if self._gate.should_emit(decision, now):
                self._record_contact(topic, state, decision)
            if decision.verdict is Verdict.FORBIDDEN:
                self._last_forbidden_seen = now
                self._last_forbidden = {
                    'pair': list(decision.pair),
                    'rule': decision.rule,
                    'stage': decision.stage,
                }
                self._latch(
                    f'forbidden contact: {decision.rule}: {decision.pair}')

    def _record_contact(self, topic, state, decision):
        depths = [float(value) for value in getattr(state, 'depths', ())]
        try:
            force = state.total_wrench.force
            force_norm = math.sqrt(force.x ** 2 + force.y ** 2 + force.z ** 2)
        except AttributeError:
            force_norm = 0.0
        record = {
            'time': _timestamp(), 'topic': topic,
            'run_id': self._run_id, 'stage': decision.stage,
            'collision1': decision.pair[0], 'collision2': decision.pair[1],
            'verdict': decision.verdict.value, 'rule': decision.rule,
            'max_depth_m': max(depths, default=0.0),
            'force_norm_n': round(force_norm, 6),
        }
        self._append('contacts.jsonl', record)
        self._event_pub.publish(String(data=json.dumps(record, ensure_ascii=False)))
        self._stats['events_written'] += 1

    def _health(self):
        return source_readiness(
            CONTACT_TOPICS, self._counts, self._last_seen,
            time.monotonic(), self._timeout)

    def _health_check(self):
        details, unavailable = self._health()
        elapsed = time.monotonic() - self._started
        if unavailable and elapsed >= self._grace and self._source_fault is None:
            self._source_fault = {
                'time': _timestamp(), 'unavailable_topics': unavailable,
                'details': details,
            }
            self._append('errors.jsonl', {
                'time': _timestamp(), 'error_code': 'CONTACT_SOURCE_FAULT',
                'run_id': self._run_id,
                'detail': self._source_fault,
            })
            self._latch(f'contact sources unavailable: {unavailable}')
        if self._unsafe_latched:
            self._request_stop()
        self._publish_diagnostics(details, unavailable)

    def _latch(self, reason):
        if self._unsafe_latched:
            return
        self._unsafe_latched = True
        self._append('errors.jsonl', {
            'time': _timestamp(), 'error_code': 'COLLISION_SAFETY_LATCH',
            'run_id': self._run_id, 'stage': self._stage, 'detail': reason,
        })
        self.get_logger().error(reason)
        self._request_stop()

    def _request_stop(self):
        if self._stop_requested or not self._stop.service_is_ready():
            return
        self._stop_requested = True
        self._stats['safe_stop_calls'] += 1
        future = self._stop.call_async(Trigger.Request())
        future.add_done_callback(self._stop_complete)

    def _stop_complete(self, future):
        response = future.result()
        success = response is not None and response.success
        self._stop_result = (
            response.message if response is not None else 'empty response')
        key = 'safe_stop_successes' if success else 'safe_stop_failures'
        self._stats[key] += 1
        self._write_summary()

    def _readiness_service(self, _request, response):
        details, unavailable = self._health()
        response.success = not unavailable and not self._unsafe_latched
        response.message = json.dumps({
            'ready': response.success,
            'unsafe_latched': self._unsafe_latched,
            'unavailable_topics': unavailable,
            'sources': details,
        }, ensure_ascii=False)
        return response

    def _reset_service(self, _request, response):
        details, unavailable = self._health()
        quiet_for = (
            None if self._last_forbidden_seen is None
            else time.monotonic() - self._last_forbidden_seen)
        if unavailable:
            response.success = False
            response.message = json.dumps({
                'reset': False, 'reason': 'contact sources are not healthy',
                'unavailable_topics': unavailable, 'sources': details,
            }, ensure_ascii=False)
            return response
        if quiet_for is not None and quiet_for < 1.0:
            response.success = False
            response.message = json.dumps({
                'reset': False, 'reason': 'forbidden contact is not yet quiet',
                'quiet_for_sec': round(quiet_for, 3),
            }, ensure_ascii=False)
            return response
        self._unsafe_latched = False
        self._source_fault = None
        self._stop_requested = False
        self._stop_result = 'reset_by_operator'
        event = {
            'time': _timestamp(), 'event': 'collision_monitor_reset',
            'run_id': self._run_id,
            'quiet_for_sec': None if quiet_for is None else round(quiet_for, 3),
        }
        self._append('events.jsonl', event)
        self._write_summary()
        response.success = True
        response.message = json.dumps({
            'reset': True, 'message': 'safety latch reset after healthy quiet period',
        }, ensure_ascii=False)
        return response

    def _publish_diagnostics(self, details, unavailable):
        status = DiagnosticStatus()
        status.name = 'robot_pick_place_sim/collision_monitor'
        status.hardware_id = 'gazebo_pick_place_world'
        if self._unsafe_latched:
            status.level = DiagnosticStatus.ERROR
            status.message = 'unsafe contact/source fault latched'
        elif unavailable:
            status.level = DiagnosticStatus.WARN
            status.message = 'waiting for fresh contact sources'
        else:
            status.level = DiagnosticStatus.OK
            status.message = 'all contact sources fresh; no unsafe contact'
        values = {
            'stage': self._stage,
            'unsafe_latched': self._unsafe_latched,
            'unavailable_topics': unavailable,
            'safe_stop_calls': self._stats['safe_stop_calls'],
        }
        for topic, detail in details.items():
            values[f'{topic}.messages'] = detail['messages_received']
            values[f'{topic}.age_sec'] = detail['last_seen_age_sec']
        status.values = [
            KeyValue(key=str(key), value=json.dumps(value, ensure_ascii=False))
            for key, value in values.items()
        ]
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        array.status = [status]
        self._diagnostics_pub.publish(array)

    def _summary(self):
        details, unavailable = self._health()
        return {
            'time': _timestamp(), 'run_id': self._run_id, 'stage': self._stage,
            'contact_topics': list(CONTACT_TOPICS),
            'sources': details, 'unavailable_topics': unavailable,
            'unsafe_latched': self._unsafe_latched,
            'source_fault': self._source_fault,
            'last_forbidden': self._last_forbidden,
            'safe_stop_result': self._stop_result,
            **self._stats,
        }

    def _write_summary(self):
        path = self._log_dir / 'collision_summary.json'
        temporary = self._log_dir / 'collision_summary.json.tmp'
        temporary.write_text(
            json.dumps(self._summary(), indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        temporary.replace(path)

    def _append(self, name, record):
        with (self._log_dir / name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    def destroy_node(self):
        self._write_summary()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CollisionMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
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
