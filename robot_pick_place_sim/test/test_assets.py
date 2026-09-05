from math import cos, hypot, pi, sin
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
        def multiply(left, right):
            return [[sum(left[row][k] * right[k][col]
                         for k in range(4))
                     for col in range(4)] for row in range(4)]

        def transform(xyz=(0.0, 0.0, 0.0), axis=None, angle=0.0):
            matrix = [[1.0, 0.0, 0.0, xyz[0]],
                      [0.0, 1.0, 0.0, xyz[1]],
                      [0.0, 0.0, 1.0, xyz[2]],
                      [0.0, 0.0, 0.0, 1.0]]
            c, s = cos(angle), sin(angle)
            rotations = {
                'x': [[1, 0, 0, 0], [0, c, -s, 0],
                      [0, s, c, 0], [0, 0, 0, 1]],
                'y': [[c, 0, s, 0], [0, 1, 0, 0],
                      [-s, 0, c, 0], [0, 0, 0, 1]],
                'z': [[c, -s, 0, 0], [s, c, 0, 0],
                      [0, 0, 1, 0], [0, 0, 0, 1]],
            }
            return matrix if axis is None else multiply(matrix, rotations[axis])

        origins = (
            ((0, 0, 0.1), None, 0.0),
            ((0, 0, 0.038), 'x', -pi / 2),
            ((0, -0.1, 0), None, 0.0),
            ((0.108, -0.005, -0.001), 'y', pi / 2),
            ((-0.001, 0, 0), 'y', -pi / 2),
            ((0.06, 0, 0), 'y', pi / 2),
        )
        result = transform()
        for (xyz, axis, angle), joint in zip(origins, joints):
            result = multiply(result, transform(xyz, axis, angle))
            result = multiply(result, transform(axis='z', angle=joint))
        result = multiply(result, transform((0, 0, 0.038)))
        return result[0][3], result[1][3], result[2][3]

    for prefix in ('pick', 'place'):
        point = params[f'{prefix}_point_xyz']
        low = tool_position(params[f'{prefix}_joints'])
        above = tool_position(params[f'{prefix}_above_joints'])
        xy_error = hypot(low[0] - point[0], low[1] - point[1])
        if prefix == 'pick':
            assert abs(xy_error - 0.005) < 0.001
        else:
            assert xy_error < 0.001
        assert abs(above[2] - low[2] - params['safe_height_m']) < 0.003
