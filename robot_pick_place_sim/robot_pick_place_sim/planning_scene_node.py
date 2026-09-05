"""Publish the fixed workcell geometry to the MoveIt PlanningScene."""

from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject, PlanningScene
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from shape_msgs.msg import SolidPrimitive


class WorkcellPlanningScene(Node):
    def __init__(self):
        super().__init__('workcell_planning_scene')
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._publisher = self.create_publisher(PlanningScene, '/planning_scene', qos)
        self._timer = self.create_timer(1.0, self._publish)

    def _publish(self):
        table = CollisionObject()
        table.header.frame_id = 'base_footprint'
        table.id = 'work_table'
        table.operation = CollisionObject.ADD
        primitive = SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[1.2, 0.8, 0.75])
        pose = Pose()
        pose.position.z = -0.375
        pose.orientation.w = 1.0
        table.primitives = [primitive]
        table.primitive_poses = [pose]
        scene = PlanningScene()
        scene.is_diff = True
        scene.world.collision_objects = [table]
        self._publisher.publish(scene)


def main(args=None):
    rclpy.init(args=args)
    node = WorkcellPlanningScene()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
