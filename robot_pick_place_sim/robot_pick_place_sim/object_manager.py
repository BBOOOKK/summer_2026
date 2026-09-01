"""Deterministic Gazebo object reset and grasp following for the teaching demo."""

import json

from gazebo_msgs.msg import EntityState
from gazebo_msgs.srv import SetEntityState
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener


class ObjectManager(Node):
    """Reset the cube at A and make it follow tool0 while grasped."""

    def __init__(self):
        super().__init__('object_manager')
        self.declare_parameter('entity_name', 'target_object')
        self.declare_parameter('tool_frame', 'tool0')
        self.declare_parameter('world_frame', 'world')
        self.declare_parameter('initial_pose', [0.22, 0.12, 0.77])
        self.declare_parameter('grasp_offset_z', -0.07)
        self._entity = self.get_parameter('entity_name').value
        self._tool = self.get_parameter('tool_frame').value
        self._world = self.get_parameter('world_frame').value
        self._initial = self.get_parameter('initial_pose').value
        self._offset_z = float(self.get_parameter('grasp_offset_z').value)
        self._grasped = False
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._set_state = self.create_client(SetEntityState, '/gazebo/set_entity_state')
        self.create_subscription(Bool, '/pick_place/grasped', self._grasp, 10)
        self.create_subscription(String, '/pick_place/state', self._task_state, 10)
        self.create_timer(0.05, self._follow)

    def _grasp(self, message):
        self._grasped = message.data

    def _task_state(self, message):
        try:
            state = json.loads(message.data).get('state')
        except (json.JSONDecodeError, AttributeError):
            return
        if state == 'VALIDATING':
            self._grasped = False
            self._place(self._initial[0], self._initial[1], self._initial[2])

    def _follow(self):
        if not self._grasped or not self._set_state.service_is_ready():
            return
        try:
            transform = self._tf_buffer.lookup_transform(
                self._world, self._tool, Time())
        except TransformException as exc:
            self.get_logger().warning(
                f'waiting for {self._world}->{self._tool}: {exc}',
                throttle_duration_sec=2.0)
            return
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        self._place(
            translation.x, translation.y, translation.z + self._offset_z,
            (rotation.x, rotation.y, rotation.z, rotation.w))

    def _place(self, x, y, z, quaternion=(0.0, 0.0, 0.0, 1.0)):
        if not self._set_state.service_is_ready():
            return
        request = SetEntityState.Request()
        request.state = EntityState()
        request.state.name = self._entity
        request.state.reference_frame = self._world
        request.state.pose.position.x = float(x)
        request.state.pose.position.y = float(y)
        request.state.pose.position.z = float(z)
        request.state.pose.orientation.x = float(quaternion[0])
        request.state.pose.orientation.y = float(quaternion[1])
        request.state.pose.orientation.z = float(quaternion[2])
        request.state.pose.orientation.w = float(quaternion[3])
        request.state.twist.linear.x = 0.0
        request.state.twist.linear.y = 0.0
        request.state.twist.linear.z = 0.0
        self._set_state.call_async(request)


def main(args=None):
    rclpy.init(args=args)
    node = ObjectManager()
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
