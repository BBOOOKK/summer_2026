from math import cos, hypot, sin
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).parents[1]


def test_xml_assets_are_well_formed():
    ET.parse(ROOT / 'package.xml')
    ET.parse(ROOT / 'worlds' / 'pick_place.world')
    ET.parse(ROOT / 'urdf' / 'mecharm270.urdf.xacro')


def test_robot_has_inertia_free_kdl_root():
    root = ET.parse(ROOT / 'urdf' / 'mecharm270.urdf.xacro').getroot()
    world = root.find("link[@name='world']")
    anchor = root.find("joint[@name='world_fixed_joint']")
    footprint = root.find("link[@name='base_footprint']")
    fixed = root.find("joint[@name='base_fixed']")
    assert world is not None and world.find('inertial') is None
    assert anchor is not None and anchor.attrib['type'] == 'fixed'
    assert anchor.find('origin').attrib['xyz'] == '0 0 0.75'
    assert footprint is not None and footprint.find('inertial') is None
    assert fixed is not None and fixed.attrib['type'] == 'fixed'


def test_pick_place_configuration_is_safe_and_complete():
    data = yaml.safe_load((ROOT / 'config' / 'pick_place.yaml').read_text())
    params = data['pick_place']['ros__parameters']
    assert params['safe_height_m'] >= 0.10
    assert len(params['home_joints']) == 6
    assert len(params['joint_lower_limits']) == 6
    assert len(params['joint_upper_limits']) == 6
    for key in ('home_joints', 'pick_above_joints', 'pick_joints',
                'place_above_joints', 'place_joints'):
        for value, lower, upper in zip(
                params[key], params['joint_lower_limits'], params['joint_upper_limits']):
            assert lower <= value <= upper
    assert params['reach_min_m'] < params['reach_max_m']
    assert params['require_collision_monitor'] is True


def test_world_contains_acceptance_entities():
    text = (ROOT / 'worlds' / 'pick_place.world').read_text()
    for entity in (
            'work_table', 'target_object', 'pickup_zone_A', 'place_zone_B',
            'grasp_plugin_carrier'):
        assert f'name="{entity}"' in text
    assert 'libgazebo_ros_state.so' in text
    assert 'librobot_grasp_joint.so' in text
    for topic in ('contacts/table', 'contacts/target'):
        assert topic in text


def test_launch_starts_runtime_collision_supervisor():
    launch = (ROOT / 'launch' / 'simulation.launch.py').read_text()
    setup = (ROOT / 'setup.py').read_text()
    package = (ROOT / 'package.xml').read_text()
    assert "executable='collision_monitor'" in launch
    assert 'collision_monitor = robot_pick_place_sim.collision_monitor:main' in setup
    assert '<exec_depend>diagnostic_msgs</exec_depend>' in package


def test_physical_grasp_replaces_transport_pose_writes():
    robot = (ROOT / 'urdf' / 'mecharm270.urdf.xacro').read_text()
    manager = (ROOT / 'robot_pick_place_sim' / 'object_manager.py').read_text()
    task = (ROOT / 'robot_pick_place_sim' / 'pick_place_node.py').read_text()
    assert 'left_finger_joint' in robot and 'right_finger_joint' in robot
    assert 'right_finger_fixed' not in robot
    assert 'libgazebo_ros_bumper.so' in robot
    assert 'self_collide' in robot
    assert 'lookup_transform' not in manager
    assert 'transport_set_state_writes' in manager
    assert "'/grasp/attach'" in task and "'/grasp/detach'" in task
    plugin = ROOT.parent / 'robot_grasp_joint' / 'src' / 'grasp_joint_plugin.cpp'
    assert plugin.exists()
    plugin_text = plugin.read_text()
    assert 'CreateJoint' in plugin_text and 'BilateralContactFreshLocked' in plugin_text


def test_taught_poses_match_a_b_and_safe_height():
    data = yaml.safe_load((ROOT / 'config' / 'pick_place.yaml').read_text())
    params = data['pick_place']['ros__parameters']

    def tool_position(joints):
        q1, q2, q3, q4, q5, q6 = joints
        assert q4 == 0.0 and q5 == 0.0 and q6 == 0.0
        radial = 0.130 * sin(q2) + 0.310 * sin(q2 + q3)
        z = 0.165 + 0.130 * cos(q2) + 0.310 * cos(q2 + q3)
        return radial * cos(q1), radial * sin(q1), z

    for prefix in ('pick', 'place'):
        point = params[f'{prefix}_point_xyz']
        low = tool_position(params[f'{prefix}_joints'])
        above = tool_position(params[f'{prefix}_above_joints'])
        assert abs(hypot(low[0], low[1]) - hypot(point[0], point[1])) < 0.003
        assert abs(above[2] - low[2] - params['safe_height_m']) < 0.003
        assert abs(params[f'{prefix}_joints'][1] +
                   params[f'{prefix}_joints'][2] - 2.25) < 0.003
