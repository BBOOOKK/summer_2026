import unittest

from robot_pick_place_sim.safety import SafetyError, validate_task


def valid_config():
    return {
        'pick_point_xyz': [0.22, 0.12, 0.02],
        'place_point_xyz': [0.20, -0.16, 0.02],
        'safe_height_m': 0.12,
        'reach_min_m': 0.08,
        'reach_max_m': 0.38,
        'joint_lower_limits': [-2.0] * 6,
        'joint_upper_limits': [2.0] * 6,
        'home_joints': [0.0] * 6,
        'pick_above_joints': [0.1] * 6,
        'pick_joints': [0.2] * 6,
        'place_above_joints': [-0.1] * 6,
        'place_joints': [-0.2] * 6,
    }


class SafetyTest(unittest.TestCase):

    def test_valid_task_passes(self):
        self.assertTrue(validate_task(valid_config()))

    def test_unreachable_target_stops_task(self):
        config = valid_config()
        config['pick_point_xyz'] = [0.8, 0.0, 0.02]
        with self.assertRaisesRegex(SafetyError, 'unreachable'):
            validate_task(config)

    def test_missing_solution_stops_task(self):
        config = valid_config()
        config['pick_joints'] = []
        with self.assertRaisesRegex(SafetyError, 'IK/teaching solution'):
            validate_task(config)

    def test_joint_limit_violation_stops_task(self):
        config = valid_config()
        config['place_joints'][3] = 3.0
        with self.assertRaisesRegex(SafetyError, 'exceeds'):
            validate_task(config)


if __name__ == '__main__':
    unittest.main()
