"""Tests for fail-closed collision classification and source health."""

import unittest

from robot_pick_place_sim.contact_policy import (
    ContactPolicy, EpisodeGate, Verdict, canonical_pair, source_readiness)


ROBOT = 'mecharm270::link3::link3_collision_collision'
BASE = 'mecharm270::base_footprint::base_link_collision_collision'
LEFT = 'mecharm270::left_finger::left_finger_collision_collision'
RIGHT = 'mecharm270::right_finger::right_finger_collision_collision'
TARGET = 'target_object::object::object_collision'
TABLE = 'work_table::table::table_collision'


class ContactPolicyTest(unittest.TestCase):
    """Exercise allowed, forbidden, ignored, and health branches."""

    def setUp(self):
        self.policy = ContactPolicy()

    def test_pair_is_unordered(self):
        self.assertEqual(canonical_pair(TARGET, TABLE), canonical_pair(TABLE, TARGET))

    def test_target_table_is_allowed(self):
        result = self.policy.classify(TARGET, TABLE, 'IDLE')
        self.assertEqual(result.verdict, Verdict.ALLOWED)
        self.assertEqual(result.rule, 'target_table')

    def test_fixed_base_table_is_allowed(self):
        self.assertEqual(
            self.policy.classify(BASE, TABLE, 'HOME').verdict,
            Verdict.ALLOWED)

    def test_finger_target_allowed_during_grasp(self):
        for stage in ('DESCEND_PICK', 'GRASP', 'GRASP_CONFIRMED', 'LIFT_OBJECT'):
            with self.subTest(stage=stage):
                self.assertEqual(
                    self.policy.classify(LEFT, TARGET, stage).verdict,
                    Verdict.ALLOWED)

    def test_finger_target_forbidden_at_idle(self):
        result = self.policy.classify(RIGHT, TARGET, 'IDLE')
        self.assertEqual(result.verdict, Verdict.FORBIDDEN)
        self.assertEqual(result.rule, 'finger_target_wrong_phase')

    def test_non_finger_robot_target_is_forbidden(self):
        result = self.policy.classify(ROBOT, TARGET, 'GRASP')
        self.assertEqual(result.verdict, Verdict.FORBIDDEN)

    def test_robot_table_is_forbidden(self):
        result = self.policy.classify(ROBOT, TABLE, 'ABOVE_PLACE')
        self.assertEqual(result.verdict, Verdict.FORBIDDEN)

    def test_unrelated_environment_is_ignored(self):
        result = self.policy.classify(
            'ground::link::collision', 'marker::link::collision', 'HOME')
        self.assertEqual(result.verdict, Verdict.IGNORED)

    def test_nonadjacent_self_collision_is_forbidden(self):
        other = 'mecharm270::link6::link6_collision_collision'
        result = self.policy.classify(ROBOT, other, 'HOME')
        self.assertEqual(result.verdict, Verdict.FORBIDDEN)
        self.assertEqual(result.rule, 'robot_self_collision')

    def test_adjacent_self_contact_is_allowed(self):
        first = 'mecharm270::link2::collision'
        second = 'mecharm270::link3::collision'
        self.assertEqual(
            self.policy.classify(first, second, 'HOME').verdict,
            Verdict.ALLOWED)

    def test_episode_gate_suppresses_continuous_contact(self):
        decision = self.policy.classify(TARGET, TABLE, 'IDLE')
        gate = EpisodeGate(0.5)
        self.assertTrue(gate.should_emit(decision, 1.0))
        self.assertFalse(gate.should_emit(decision, 1.2))
        self.assertTrue(gate.should_emit(decision, 1.8))

    def test_sources_require_messages_from_every_topic(self):
        topics = ('a', 'b', 'c')
        details, unavailable = source_readiness(
            topics, {'a': 1, 'b': 1, 'c': 0},
            {'a': 9.8, 'b': 9.7, 'c': None}, 10.0, 1.0)
        self.assertEqual(unavailable, ['c'])
        self.assertFalse(details['c']['ready'])

    def test_stale_source_fails_closed(self):
        details, unavailable = source_readiness(
            ('target',), {'target': 10}, {'target': 5.0}, 10.0, 2.0)
        self.assertEqual(unavailable, ['target'])
        self.assertFalse(details['target']['ready'])

    def test_fresh_sources_are_ready(self):
        details, unavailable = source_readiness(
            ('a', 'b'), {'a': 2, 'b': 3}, {'a': 9.0, 'b': 9.5}, 10.0, 2.0)
        self.assertEqual(unavailable, [])
        self.assertTrue(all(item['ready'] for item in details.values()))


if __name__ == '__main__':
    unittest.main()
