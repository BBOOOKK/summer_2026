"""Pure contact classification and source-health logic."""

from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
import math


class Verdict(str, Enum):
    """Safety meaning of a Gazebo collision pair."""

    ALLOWED = 'allowed'
    FORBIDDEN = 'forbidden'
    IGNORED = 'ignored'


def normalize_collision(name):
    """Normalize a scoped Gazebo collision name without discarding scopes."""
    text = str(name).strip()
    return '::'.join(part.strip() for part in text.split('::')) or '<unnamed>'


def canonical_pair(first, second):
    """Return a stable unordered collision pair."""
    return tuple(sorted(
        (normalize_collision(first), normalize_collision(second)),
        key=lambda value: (value.casefold(), value)))


def link_name(collision):
    """Extract the link scope from model::link::collision."""
    parts = normalize_collision(collision).split('::')
    return parts[-2] if len(parts) >= 3 else ''


def _matches(name, patterns):
    folded = name.casefold()
    return any(fnmatchcase(folded, item.casefold()) for item in patterns)


@dataclass(frozen=True)
class Decision:
    """Classification result for one canonical collision pair."""

    pair: tuple
    verdict: Verdict
    rule: str
    stage: str


class ContactPolicy:
    """Fail-closed allowlist for contacts involving the arm or target."""

    def __init__(self):
        self.robot_patterns = ('*mecharm270::*',)
        self.target_patterns = ('*target_object::*',)
        self.table_patterns = ('*work_table::*',)
        self.base_patterns = ('*::base_link::*', '*::base_footprint::*')
        self.finger_patterns = (
            '*::left_finger::*', '*::right_finger::*')
        self.finger_stages = frozenset({
            'DESCEND_PICK', 'GRASP', 'ATTACH_OBJECT', 'GRASP_CONFIRMED',
            'LIFT_OBJECT', 'ABOVE_PLACE', 'DESCEND_PLACE',
            'DETACH_OBJECT', 'RELEASE', 'RETREAT', 'SAFE_STOP',
        })
        self.adjacent_links = frozenset({
            frozenset(('base_link', 'link1')),
            frozenset(('link1', 'link2')),
            frozenset(('link2', 'link3')),
            frozenset(('link3', 'link4')),
            frozenset(('link4', 'link5')),
            frozenset(('link5', 'link6')),
            frozenset(('link6', 'tool0')),
            frozenset(('tool0', 'left_finger')),
            frozenset(('tool0', 'right_finger')),
        })

    def classify(self, first, second, stage):
        """Classify one pair; all monitored contacts default to forbidden."""
        pair = canonical_pair(first, second)
        current = str(stage).strip().upper() or 'UNKNOWN'
        roles = []
        for name in pair:
            robot = _matches(name, self.robot_patterns)
            roles.append({
                'robot': robot,
                'target': _matches(name, self.target_patterns),
                'table': _matches(name, self.table_patterns),
                'base': robot and _matches(name, self.base_patterns),
                'finger': robot and _matches(name, self.finger_patterns),
                'link': link_name(name) if robot else '',
            })
        left, right = roles

        if ((left['target'] and right['table']) or
                (right['target'] and left['table'])):
            return Decision(pair, Verdict.ALLOWED, 'target_table', current)
        if ((left['base'] and right['table']) or
                (right['base'] and left['table'])):
            return Decision(pair, Verdict.ALLOWED, 'fixed_base_table', current)
        if ((left['finger'] and right['target']) or
                (right['finger'] and left['target'])):
            if current in self.finger_stages:
                return Decision(
                    pair, Verdict.ALLOWED, 'finger_target_grasp_phase', current)
            return Decision(
                pair, Verdict.FORBIDDEN, 'finger_target_wrong_phase', current)
        if left['robot'] and right['robot']:
            links = frozenset((left['link'], right['link']))
            if len(links) == 2 and links in self.adjacent_links:
                return Decision(
                    pair, Verdict.ALLOWED, 'adjacent_robot_links', current)
            return Decision(
                pair, Verdict.FORBIDDEN, 'robot_self_collision', current)
        if not any(role['robot'] or role['target'] for role in roles):
            return Decision(
                pair, Verdict.IGNORED, 'unmonitored_environment', current)
        return Decision(
            pair, Verdict.FORBIDDEN, 'unexpected_monitored_contact', current)


class EpisodeGate:
    """Emit one event until a pair has disappeared for a configured gap."""

    def __init__(self, gap_seconds=0.5):
        self.gap_seconds = float(gap_seconds)
        if not math.isfinite(self.gap_seconds) or self.gap_seconds <= 0:
            raise ValueError('gap_seconds must be finite and positive')
        self._last_seen = {}

    def should_emit(self, decision, now):
        """Return true when this observation begins a new episode."""
        key = decision.pair + (decision.verdict.value, decision.rule)
        previous = self._last_seen.get(key)
        timestamp = float(now)
        self._last_seen[key] = timestamp
        expiry = timestamp - max(1.0, 4.0 * self.gap_seconds)
        for stale in [item for item, seen in self._last_seen.items()
                      if seen < expiry]:
            self._last_seen.pop(stale, None)
        return (previous is None or timestamp < previous or
                timestamp - previous > self.gap_seconds)


def source_readiness(topics, counts, last_seen, now, timeout):
    """Return topic health details and the list of unavailable sources."""
    details = {}
    unavailable = []
    for topic in topics:
        seen = last_seen.get(topic)
        age = None if seen is None else max(0.0, float(now) - float(seen))
        ready = counts.get(topic, 0) > 0 and age is not None and age <= timeout
        details[topic] = {
            'messages_received': int(counts.get(topic, 0)),
            'last_seen_age_sec': None if age is None else round(age, 3),
            'ready': ready,
        }
        if not ready:
            unavailable.append(topic)
    return details, unavailable
