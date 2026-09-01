"""Start Gazebo, mechArm controllers, task logic, and state/logging nodes."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(get_package_share_directory('robot_pick_place_sim'))
    gazebo_share = Path(get_package_share_directory('gazebo_ros'))
    world = package_share / 'worlds' / 'pick_place.world'
    xacro = package_share / 'urdf' / 'mecharm270.urdf.xacro'
    controllers = package_share / 'config' / 'controllers.yaml'
    task_config = package_share / 'config' / 'pick_place.yaml'
    robot_description = ParameterValue(
        Command(['xacro ', str(xacro), ' controllers_file:=', str(controllers)]),
        value_type=str)
    use_sim_time = LaunchConfiguration('use_sim_time')
    auto_start = LaunchConfiguration('auto_start')
    log_directory = LaunchConfiguration('log_directory')

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('auto_start', default_value='true'),
        DeclareLaunchArgument(
            'log_directory',
            default_value=str(Path.cwd() / 'logs' / 'robot_pick_place')),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                str(gazebo_share / 'launch' / 'gazebo.launch.py')),
            launch_arguments={'world': str(world),
                              'gui': LaunchConfiguration('gui')}.items()),
        Node(
            package='robot_state_publisher', executable='robot_state_publisher',
            output='screen', parameters=[{
                'robot_description': robot_description,
                'use_sim_time': use_sim_time,
            }]),
        Node(
            package='tf2_ros', executable='static_transform_publisher',
            name='world_to_base',
            arguments=['0', '0', '0.75', '0', '0', '0', 'world', 'base_link']),
        Node(
            package='gazebo_ros', executable='spawn_entity.py',
            arguments=['-entity', 'mecharm270', '-topic', 'robot_description',
                       '-x', '0', '-y', '0', '-z', '0.75'],
            output='screen'),
        TimerAction(period=3.0, actions=[
            Node(package='controller_manager', executable='spawner',
                 arguments=['joint_state_broadcaster',
                            '--controller-manager', '/controller_manager'],
                 output='screen'),
            Node(package='controller_manager', executable='spawner',
                 arguments=['arm_controller',
                            '--controller-manager', '/controller_manager'],
                 output='screen'),
            Node(package='controller_manager', executable='spawner',
                 arguments=['gripper_controller',
                            '--controller-manager', '/controller_manager'],
                 output='screen'),
        ]),
        TimerAction(period=7.0, actions=[
            Node(package='robot_pick_place_sim', executable='object_manager',
                 name='object_manager', output='screen',
                 parameters=[{'use_sim_time': use_sim_time}]),
            Node(package='robot_pick_place_sim', executable='pick_place_node',
                 name='pick_place', output='screen',
                 parameters=[str(task_config), {
                     'auto_start': ParameterValue(auto_start, value_type=bool),
                     'use_sim_time': use_sim_time,
                     'log_directory': log_directory,
                 }]),
        ]),
    ])
