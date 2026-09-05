"""Static regression gates for the Fortress + MoveIt 2 backend."""

from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[1]
MOVEIT = ROOT.parent / 'mecharm_moveit_config'


def test_fortress_world_has_audited_workcell_and_contact_sources():
    world = ET.parse(ROOT / 'worlds' / 'pick_place_fortress.sdf').getroot()
    text = ET.tostring(world, encoding='unicode')
    assert 'work_table' in text
    assert 'target_object' in text
    assert '/gazebo/contacts/table' in text
    assert '/gazebo/contacts/target' in text
    assert '<size>0.066 0.066 0.035</size>' in text


def test_fortress_robot_is_physically_fixed_and_uses_real_joint_attach():
    robot = (ROOT / 'urdf' / 'mecharm270.urdf.xacro').read_text(
        encoding='utf-8')
    assert '<parent link="world"/><child link="base_footprint"/>' in robot
    assert 'gz_ros2_control/GazeboSimSystem' in robot
    assert 'DetachableJoint' in robot
    assert '<child_model>target_object</child_model>' in robot
    assert '/fortress/joint_states_raw' in robot


def test_fortress_launch_starts_bridge_moveit_safety_and_task_nodes():
    launch = (ROOT / 'launch' / 'fortress_moveit.launch.py').read_text(
        encoding='utf-8')
    for token in (
            'gz_sim.launch.py', 'parameter_bridge', 'fortress_adapter',
            'move_group.launch.py', 'planning_scene_node',
            'collision_monitor', 'object_manager', 'moveit_pick_place_node'):
        assert token in launch
    assert 'ignition.msgs.Empty' in launch
    assert 'ignition.msgs.StringMsg' in launch


def test_moveit_configuration_maps_shared_ros2_control_interfaces():
    controllers = yaml.safe_load(
        (MOVEIT / 'config' / 'moveit_controllers.yaml').read_text(
            encoding='utf-8'))
    configured = controllers['moveit_simple_controller_manager']
    assert configured['arm_controller']['joints'] == [
        f'joint{index}' for index in range(1, 7)]
    assert configured['gripper_controller']['joints'] == [
        'right_finger_joint']
    semantic = ET.parse(MOVEIT / 'config' / 'mecharm270.srdf').getroot()
    assert semantic.find("./group[@name='arm']/chain").attrib == {
        'base_link': 'base_link', 'tip_link': 'tool0'}
