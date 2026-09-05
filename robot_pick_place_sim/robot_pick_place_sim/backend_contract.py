"""Runtime audit for the simulator-independent ROS 2 interface contract."""

import json
from pathlib import Path
import sys
import time

import rclpy
from rclpy.action.graph import get_action_names_and_types
from rclpy.node import Node


EXPECTED = {
    'topics': {
        '/joint_states': 'sensor_msgs/msg/JointState',
        '/pick_place/state': 'std_msgs/msg/String',
    },
    'services': {
        '/pick_place/start': 'std_srvs/srv/Trigger',
        '/pick_place/stop': 'std_srvs/srv/Trigger',
        '/pick_place/reset_safety': 'std_srvs/srv/Trigger',
        '/collision_monitor/readiness': 'std_srvs/srv/Trigger',
        '/gazebo/get_entity_state': 'gazebo_msgs/srv/GetEntityState',
        '/gazebo/set_entity_state': 'gazebo_msgs/srv/SetEntityState',
        '/grasp/attach': 'std_srvs/srv/Trigger',
        '/grasp/detach': 'std_srvs/srv/Trigger',
    },
    'actions': {
        '/arm_controller/follow_joint_trajectory':
            'control_msgs/action/FollowJointTrajectory',
        '/gripper_controller/follow_joint_trajectory':
            'control_msgs/action/FollowJointTrajectory',
    },
}


def audit_graph(actual):
    """Compare graph dictionaries and return a deterministic report."""
    missing = []
    mismatched = []
    for kind, endpoints in EXPECTED.items():
        available = actual.get(kind, {})
        for name, expected_type in endpoints.items():
            types = available.get(name)
            if not types:
                missing.append({'kind': kind[:-1], 'name': name})
            elif expected_type not in types:
                mismatched.append({
                    'kind': kind[:-1], 'name': name,
                    'expected': expected_type, 'actual': sorted(types),
                })
    return {
        'passed': not missing and not mismatched,
        'missing': missing,
        'type_mismatches': mismatched,
        'checked_endpoints': sum(len(items) for items in EXPECTED.values()),
    }


class BackendContractCheck(Node):
    def __init__(self):
        super().__init__('backend_contract_check')
        self.declare_parameter('backend', 'fortress')
        self.declare_parameter('timeout_sec', 30.0)
        self.declare_parameter('output_path', '')

    def snapshot(self):
        return {
            'topics': dict(self.get_topic_names_and_types()),
            'services': dict(self.get_service_names_and_types()),
            'actions': dict(get_action_names_and_types(self)),
        }

    def run(self):
        timeout = float(self.get_parameter('timeout_sec').value)
        deadline = time.monotonic() + timeout
        report = audit_graph(self.snapshot())
        while not report['passed'] and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            report = audit_graph(self.snapshot())
        report.update({
            'backend': str(self.get_parameter('backend').value),
            'contract': 'pick_place_ros2_v1',
        })
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        output_path = str(self.get_parameter('output_path').value)
        if output_path:
            path = Path(output_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + '\n', encoding='utf-8')
        print(rendered)
        return report['passed']


def main(args=None):
    rclpy.init(args=args)
    node = BackendContractCheck()
    try:
        passed = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(0 if passed else 2)


if __name__ == '__main__':
    main(sys.argv)
