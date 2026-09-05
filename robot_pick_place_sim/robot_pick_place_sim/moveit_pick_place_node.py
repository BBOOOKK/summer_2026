"""MoveIt 2 planned variant of the shared fixed-point task controller."""

import threading

from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint, MotionPlanRequest, PlanningOptions
from moveit_msgs.msg import MoveItErrorCodes
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor

from .pick_place_node import ARM_JOINTS, PickPlaceNode


class MoveItPickPlaceNode(PickPlaceNode):
    """Plan every arm segment in MoveIt and let move_group execute it."""

    def __init__(self):
        super().__init__()
        self._move_group = ActionClient(self, MoveGroup, '/move_action')

    def _execute(self):
        if not self._move_group.wait_for_server(timeout_sec=10.0):
            self._fail_safe('MoveIt /move_action is unavailable')
            with self._lock:
                self._running = False
            return
        super()._execute()

    def _arm_move(self, positions):
        request = MotionPlanRequest()
        request.group_name = 'arm'
        request.num_planning_attempts = 5
        request.allowed_planning_time = 3.0
        request.max_velocity_scaling_factor = 0.35
        request.max_acceleration_scaling_factor = 0.30
        constraints = Constraints()
        constraints.name = 'fixed_point_joint_goal'
        constraints.joint_constraints = [
            JointConstraint(
                joint_name=name, position=float(position),
                tolerance_above=0.002, tolerance_below=0.002, weight=1.0)
            for name, position in zip(ARM_JOINTS, positions)
        ]
        request.goal_constraints = [constraints]
        goal = MoveGroup.Goal()
        goal.request = request
        goal.planning_options = PlanningOptions(
            plan_only=False, look_around=False, replan=True,
            replan_attempts=2, replan_delay=0.1)
        handle = self._await(
            self._move_group.send_goal_async(goal), 5.0,
            'MoveIt goal acknowledgement timeout')
        if handle is None or not handle.accepted:
            raise RuntimeError('MoveIt rejected arm planning request')
        self._active_goal = handle
        future = handle.get_result_async()
        event = threading.Event()
        future.add_done_callback(lambda _future: event.set())
        timeout = float(self._config['action_timeout_sec']) + 8.0
        if not event.wait(timeout):
            handle.cancel_goal_async()
            self._active_goal = None
            raise TimeoutError('MoveIt plan/execution timed out')
        wrapped = future.result()
        self._active_goal = None
        if wrapped is None or wrapped.result.error_code.val != MoveItErrorCodes.SUCCESS:
            code = None if wrapped is None else wrapped.result.error_code.val
            raise RuntimeError(f'MoveIt planning/execution failed; error_code={code}')


def main(args=None):
    rclpy.init(args=args)
    node = MoveItPickPlaceNode()
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
