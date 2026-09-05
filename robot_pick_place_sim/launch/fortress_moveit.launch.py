"""Gazebo Fortress + MoveIt 2 authoritative simulation backend."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    RegisterEventHandler,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(get_package_share_directory('robot_pick_place_sim'))
    ros_gz_share = Path(get_package_share_directory('ros_gz_sim'))
    moveit_share = Path(get_package_share_directory('mecharm_moveit_config'))
    world = package_share / 'worlds' / 'pick_place_fortress.sdf'
    xacro = package_share / 'urdf' / 'mecharm270.urdf.xacro'
    controllers = package_share / 'config' / 'controllers.yaml'
    task_config = LaunchConfiguration('task_config')
    log_directory = LaunchConfiguration('log_directory')
    auto_start = LaunchConfiguration('auto_start')
    gui = LaunchConfiguration('gui')
    description = ParameterValue(Command([
        'xacro ', str(xacro), ' simulator:=fortress controllers_file:=',
        str(controllers)]), value_type=str)
    bridges = [
        '/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock',
        '/gazebo/contacts/table@ros_gz_interfaces/msg/Contacts[ignition.msgs.Contacts',
        '/gazebo/contacts/target@ros_gz_interfaces/msg/Contacts[ignition.msgs.Contacts',
        '/gazebo/contacts/left_finger@ros_gz_interfaces/msg/Contacts[ignition.msgs.Contacts',
        '/gazebo/contacts/right_finger@ros_gz_interfaces/msg/Contacts[ignition.msgs.Contacts',
        '/world/pick_place/dynamic_pose/info@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V',
        '/grasp/attach_cmd@std_msgs/msg/Empty]ignition.msgs.Empty',
        '/grasp/detach_cmd@std_msgs/msg/Empty]ignition.msgs.Empty',
        '/grasp/attached@std_msgs/msg/String[ignition.msgs.StringMsg',
        '/world/pick_place/set_pose@ros_gz_interfaces/srv/SetEntityPose',
    ]
    spawn_robot = Node(
        package='ros_gz_sim', executable='create', output='screen',
        arguments=['-world', 'pick_place', '-name', 'mecharm270',
                   '-topic', 'robot_description'])
    controllers_nodes = [
        Node(package='controller_manager', executable='spawner',
             arguments=['joint_state_broadcaster', '--controller-manager', '/controller_manager']),
        Node(package='controller_manager', executable='spawner',
             arguments=['arm_controller', '--controller-manager', '/controller_manager']),
        Node(package='controller_manager', executable='spawner',
             arguments=['gripper_controller', '--controller-manager', '/controller_manager']),
    ]
    task_nodes = [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(moveit_share / 'launch' / 'move_group.launch.py')),
            launch_arguments={'simulator': 'fortress', 'use_sim_time': 'true'}.items()),
        Node(package='robot_pick_place_sim', executable='planning_scene_node', output='screen',
             parameters=[{'use_sim_time': True}]),
        Node(package='robot_pick_place_sim', executable='collision_monitor', output='screen',
             parameters=[{'use_sim_time': True, 'log_directory': log_directory}]),
        Node(package='robot_pick_place_sim', executable='object_manager', output='screen',
             parameters=[{'use_sim_time': True, 'log_directory': log_directory}]),
        Node(package='robot_pick_place_sim', executable='moveit_pick_place_node', name='pick_place', output='screen',
             parameters=[task_config, {'auto_start': ParameterValue(auto_start, value_type=bool),
                                       'use_sim_time': True, 'log_directory': log_directory}]),
    ]
    return LaunchDescription([
        DeclareLaunchArgument('auto_start', default_value='true'),
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('task_config', default_value=str(package_share / 'config' / 'pick_place.yaml')),
        DeclareLaunchArgument('log_directory', default_value=str(Path.cwd() / 'logs' / 'fortress_moveit')),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(ros_gz_share / 'launch' / 'gz_sim.launch.py')),
            launch_arguments={'gz_args': f'-s {world}'}.items(),
            condition=UnlessCondition(gui)),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(ros_gz_share / 'launch' / 'gz_sim.launch.py')),
            launch_arguments={'gz_args': str(world)}.items(),
            condition=IfCondition(gui)),
        Node(package='robot_state_publisher', executable='robot_state_publisher', output='screen',
             parameters=[{'robot_description': description, 'use_sim_time': True}]),
        # Keep physics paused while inserting the robot.  On translated ARM
        # hosts this prevents the running DART loop from starving the first
        # UserCommands request.  Everything downstream is tied to the actual
        # completion event instead of an assumed machine speed.
        TimerAction(period=5.0, actions=[spawn_robot]),
        Node(package='ros_gz_bridge', executable='parameter_bridge', output='screen',
             arguments=bridges,
             remappings=[
                 ('/gazebo/contacts/table', '/fortress/contacts/table'),
                 ('/gazebo/contacts/target', '/fortress/contacts/target'),
                 ('/gazebo/contacts/left_finger', '/fortress/contacts/left_finger'),
                 ('/gazebo/contacts/right_finger', '/fortress/contacts/right_finger'),
                 ('/world/pick_place/dynamic_pose/info', '/fortress/dynamic_pose')]),
        Node(package='ros_gz_image', executable='image_bridge', output='screen',
             arguments=['/demo_camera/image']),
        Node(package='robot_pick_place_sim', executable='fortress_adapter', output='screen'),
        RegisterEventHandler(OnProcessExit(
            target_action=spawn_robot,
            on_exit=[
                ExecuteProcess(
                    cmd=['ign', 'service', '-s', '/world/pick_place/control',
                         '--reqtype', 'ignition.msgs.WorldControl',
                         '--reptype', 'ignition.msgs.Boolean', '--timeout', '5000',
                         '--req', 'pause: false'], output='screen'),
                TimerAction(period=2.0, actions=controllers_nodes),
                TimerAction(period=6.0, actions=task_nodes),
            ])),
    ])
