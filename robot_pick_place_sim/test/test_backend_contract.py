from robot_pick_place_sim.backend_contract import EXPECTED, audit_graph


def test_complete_contract_passes():
    actual = {
        kind: {name: [type_name] for name, type_name in endpoints.items()}
        for kind, endpoints in EXPECTED.items()
    }
    report = audit_graph(actual)
    assert report['passed'] is True
    assert report['checked_endpoints'] == 12


def test_missing_action_fails_closed():
    actual = {
        kind: {name: [type_name] for name, type_name in endpoints.items()}
        for kind, endpoints in EXPECTED.items()
    }
    actual['actions'].pop('/arm_controller/follow_joint_trajectory')
    report = audit_graph(actual)
    assert report['passed'] is False
    assert report['missing'] == [{
        'kind': 'action',
        'name': '/arm_controller/follow_joint_trajectory',
    }]


def test_wrong_type_fails_closed():
    actual = {
        kind: {name: [type_name] for name, type_name in endpoints.items()}
        for kind, endpoints in EXPECTED.items()
    }
    actual['topics']['/joint_states'] = ['std_msgs/msg/String']
    report = audit_graph(actual)
    assert report['passed'] is False
    assert report['type_mismatches'][0]['name'] == '/joint_states'
