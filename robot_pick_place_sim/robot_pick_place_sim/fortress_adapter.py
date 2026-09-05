"""Adapt Gazebo Fortress transport bridges to the stable task interfaces."""

import threading
import time

from gazebo_msgs.msg import ContactState, ContactsState, EntityState
from gazebo_msgs.srv import GetEntityState, SetEntityState
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from ros_gz_interfaces.msg import Contacts, Entity
from ros_gz_interfaces.srv import SetEntityPose
import rclpy
from sensor_msgs.msg import JointState
from std_msgs.msg import Empty, String
from std_srvs.srv import Trigger
from tf2_msgs.msg import TFMessage


RAW_CONTACTS = {
    '/fortress/contacts/table': '/gazebo/contacts/table',
    '/fortress/contacts/target': '/gazebo/contacts/target',
    '/fortress/contacts/left_finger': '/gazebo/contacts/robot',
    '/fortress/contacts/right_finger': '/gazebo/contacts/robot',
}


class FortressAdapter(Node):
    """Keep task, logger, monitor, and acceptance APIs simulator-independent."""

    def __init__(self):
        super().__init__('fortress_adapter')
        self._group = ReentrantCallbackGroup()
        self._contact_publishers = {
            raw: self.create_publisher(ContactsState, stable, 100)
            for raw, stable in RAW_CONTACTS.items()}
        self._robot_contacts = self.create_publisher(
            ContactsState, '/gazebo/contacts/robot', 100)
        for raw in RAW_CONTACTS:
            self.create_subscription(
                Contacts, raw,
                lambda message, source=raw: self._contacts(source, message), 100)
        self.create_subscription(
            TFMessage, '/fortress/dynamic_pose', self._poses, 100)
        self._joint_states = self.create_publisher(JointState, '/joint_states', 100)
        self.create_subscription(
            JointState, '/fortress/joint_states_raw', self._adapt_joint_states, 100)
        self.create_subscription(
            String, '/grasp/attached', self._attached_state, 10)
        self._attach_command = self.create_publisher(
            Empty, '/grasp/attach_cmd', 10)
        self._detach_command = self.create_publisher(
            Empty, '/grasp/detach_cmd', 10)
        self._set_pose = self.create_client(
            SetEntityPose, '/world/pick_place/set_pose',
            callback_group=self._group)
        self.create_service(
            GetEntityState, '/gazebo/get_entity_state', self._get_entity,
            callback_group=self._group)
        self.create_service(
            SetEntityState, '/gazebo/set_entity_state', self._set_entity,
            callback_group=self._group)
        self.create_service(
            Trigger, '/grasp/attach', self._attach,
            callback_group=self._group)
        self.create_service(
            Trigger, '/grasp/detach', self._detach,
            callback_group=self._group)
        self._poses_by_name = {}
        self._finger_seen = {'left': None, 'right': None}
        # Fortress 6 DetachableJoint starts attached.  Do not expose healthy
        # task interfaces until the startup detach has been confirmed.
        self._attached = True
        self._startup_ready = False
        self._startup_started = time.monotonic()
        self._last_contact_message = {raw: None for raw in RAW_CONTACTS}
        self.create_timer(0.1, self._contact_heartbeats)
        self.create_timer(0.2, self._startup_detach)

    def _contacts(self, source, message):
        if not self._startup_ready:
            return
        self._last_contact_message[source] = time.monotonic()
        output = ContactsState()
        output.header = message.header
        for contact in message.contacts:
            state = ContactState()
            state.collision1_name = contact.collision1.name
            state.collision2_name = contact.collision2.name
            state.contact_positions = contact.positions
            state.contact_normals = contact.normals
            state.depths = list(contact.depths)
            state.info = 'gazebo_fortress_ros_gz_bridge'
            output.states.append(state)
            names = state.collision1_name + ' ' + state.collision2_name
            if 'target_object' in names:
                now = time.monotonic()
                if 'left_finger' in names:
                    self._finger_seen['left'] = now
                if 'right_finger' in names:
                    self._finger_seen['right'] = now
        self._contact_publishers[source].publish(output)
        # Target and table sensors together cover every robot-environment
        # collision relevant to this workcell; mirror their union as the
        # third, independently supervised policy input.
        self._robot_contacts.publish(output)

    def _contact_heartbeats(self):
        """Represent live bridges even when a Fortress sensor is contact-silent."""
        if not self._startup_ready:
            return
        now = time.monotonic()
        for raw, stable in RAW_CONTACTS.items():
            last = self._last_contact_message[raw]
            if (last is None or now - last > 0.09) and self.count_publishers(raw):
                empty = ContactsState()
                empty.header.stamp = self.get_clock().now().to_msg()
                self._contact_publishers[raw].publish(empty)
                if stable == '/gazebo/contacts/robot':
                    self._robot_contacts.publish(empty)

    def _poses(self, message):
        for transform in message.transforms:
            name = transform.child_frame_id.rsplit('/', 1)[-1]
            self._poses_by_name[name] = transform.transform

    def _adapt_joint_states(self, message):
        message.name = [
            'left_finger_joint' if name == 'left_finger_joint_mimic' else name
            for name in message.name]
        self._joint_states.publish(message)

    def _attached_state(self, message):
        state = str(message.data).strip().lower()
        self._attached = state in {'true', '1', 'attached'}
        if not self._attached and not self._startup_ready:
            self._startup_ready = True
            self.get_logger().info(
                'Fortress startup joint detached; task interfaces are ready')

    def _startup_detach(self):
        # Give parameter_bridge time to subscribe to the one-shot state event.
        if (not self._startup_ready and
                time.monotonic() - self._startup_started >= 2.0):
            self._detach_command.publish(Empty())

    def _get_entity(self, request, response):
        transform = self._poses_by_name.get(request.name)
        if transform is None:
            response.success = False
            response.status_message = f'no Fortress pose received for {request.name}'
            return response
        response.state = EntityState()
        response.state.name = request.name
        response.state.reference_frame = request.reference_frame or 'world'
        response.state.pose.position.x = transform.translation.x
        response.state.pose.position.y = transform.translation.y
        response.state.pose.position.z = transform.translation.z
        response.state.pose.orientation = transform.rotation
        response.success = True
        return response

    def _set_entity(self, request, response):
        if not self._set_pose.wait_for_service(timeout_sec=2.0):
            response.success = False
            return response
        forwarded = SetEntityPose.Request()
        forwarded.entity = Entity(name=request.state.name, type=Entity.MODEL)
        forwarded.pose = request.state.pose
        future = self._set_pose.call_async(forwarded)
        event = threading.Event()
        future.add_done_callback(lambda _future: event.set())
        response.success = bool(
            event.wait(3.0) and future.result() is not None
            and future.result().success)
        return response

    def _attach(self, _request, response):
        contact_deadline = time.monotonic() + 3.0
        fresh = False
        while time.monotonic() < contact_deadline:
            now = time.monotonic()
            fresh = all(
                stamp is not None and now - stamp <= 1.0
                for stamp in self._finger_seen.values())
            if fresh:
                break
            time.sleep(0.02)
        if not fresh:
            response.success = False
            response.message = 'bilateral target contact was not confirmed within 3 s'
            return response
        self._attach_command.publish(Empty())
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not self._attached:
            time.sleep(0.02)
        response.success = self._attached
        response.message = 'Fortress detachable joint attached' if self._attached else 'attach confirmation timed out'
        return response

    def _detach(self, _request, response):
        self._detach_command.publish(Empty())
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and self._attached:
            time.sleep(0.02)
        response.success = not self._attached
        response.message = 'Fortress detachable joint detached' if not self._attached else 'detach confirmation timed out'
        return response


def main(args=None):
    rclpy.init(args=args)
    node = FortressAdapter()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
