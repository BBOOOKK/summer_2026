"""Spawn the detachable grasp plugin carrier into an already-running Gazebo world."""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:
    carrier = PathJoinSubstitution(
        [FindPackageShare('robot_grasp_joint'), 'models', 'grasp_plugin_carrier', 'model.sdf'],
    )
    return LaunchDescription(
        [
            Node(
                package='gazebo_ros',
                executable='spawn_entity.py',
                name='spawn_grasp_plugin_carrier',
                output='screen',
                arguments=[
                    '-entity', 'grasp_plugin_carrier',
                    '-file', carrier,
                    '-timeout', '30',
                ],
            ),
        ],
    )
