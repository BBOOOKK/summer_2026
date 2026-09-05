"""Launch MoveIt 2 move_group against the shared ros2_control interfaces."""

from pathlib import Path
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _yaml(path):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def generate_launch_description():
    moveit_share = Path(get_package_share_directory('mecharm_moveit_config'))
    sim_share = Path(get_package_share_directory('robot_pick_place_sim'))
    urdf = sim_share / 'urdf' / 'mecharm270.urdf.xacro'
    controllers = sim_share / 'config' / 'controllers.yaml'
    description = ParameterValue(Command([
        'xacro ', str(urdf), ' simulator:=', LaunchConfiguration('simulator'),
        ' controllers_file:=', str(controllers)]), value_type=str)
    semantic = (moveit_share / 'config' / 'mecharm270.srdf').read_text(
        encoding='utf-8')
    ompl = _yaml(moveit_share / 'config' / 'ompl_planning.yaml')
    parameters = [
        {'robot_description': description,
         'robot_description_semantic': semantic,
         'robot_description_kinematics': _yaml(
             moveit_share / 'config' / 'kinematics.yaml'),
         'robot_description_planning': _yaml(
             moveit_share / 'config' / 'joint_limits.yaml'),
         'planning_pipelines': ['ompl'],
         'default_planning_pipeline': 'ompl',
         'allow_trajectory_execution': True,
         'publish_monitored_planning_scene': True,
         'publish_robot_description': True,
         'publish_robot_description_semantic': True,
         'use_sim_time': LaunchConfiguration('use_sim_time')},
        {'ompl': ompl},
        _yaml(moveit_share / 'config' / 'moveit_controllers.yaml'),
        {'trajectory_execution.allowed_execution_duration_scaling': 1.4,
         'trajectory_execution.allowed_goal_duration_margin': 1.0,
         # The task node validates every commanded state against the URDF
         # limits. Disable MoveIt's duplicate wall-time freshness gate: it can
         # reject valid simulated states when amd64 ROS runs on an ARM host.
         'trajectory_execution.allowed_start_tolerance': 0.0},
    ]
    return LaunchDescription([
        DeclareLaunchArgument('simulator', default_value='fortress'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        Node(package='moveit_ros_move_group', executable='move_group',
             output='screen', parameters=parameters),
    ])
