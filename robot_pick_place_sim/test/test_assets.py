from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).parents[1]


def test_xml_assets_are_well_formed():
    ET.parse(ROOT / 'package.xml')
    ET.parse(ROOT / 'worlds' / 'pick_place.world')
    ET.parse(ROOT / 'urdf' / 'mecharm270.urdf.xacro')


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


def test_world_contains_acceptance_entities():
    text = (ROOT / 'worlds' / 'pick_place.world').read_text()
    for entity in ('work_table', 'target_object', 'place_zone'):
        assert f'name="{entity}"' in text
