"""Pure-Python audit of dynamic pick-and-place acceptance artifacts."""

import csv
import json
from pathlib import Path


REQUIRED_STATES = (
    'VALIDATING', 'OPEN_GRIPPER', 'HOME', 'ABOVE_PICK', 'DESCEND_PICK',
    'GRASP', 'ATTACH_OBJECT', 'GRASP_CONFIRMED', 'LIFT_OBJECT',
    'ABOVE_PLACE', 'DESCEND_PLACE', 'DETACH_OBJECT', 'RELEASE', 'RETREAT',
    'RETURN_HOME', 'SUCCEEDED',
)


def _jsonl(path):
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _ordered_subsequence(actual, required):
    cursor = iter(actual)
    return all(any(value == expected for value in cursor) for expected in required)


def _trajectory_stats(path, start_xyz, place_xyz, place_tolerance):
    if not path.exists():
        return {'passed': False, 'reason': f'missing {path.name}'}
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 100:
        return {'passed': False, 'reason': 'too few object samples',
                'samples': len(rows)}
    points = [tuple(float(row[key]) for key in ('x', 'y', 'z')) for row in rows]
    pre_grasp_states = {
        'VALIDATING', 'OPEN_GRIPPER', 'HOME', 'ABOVE_PICK',
        'DESCEND_PICK', 'GRASP',
    }
    pre_grasp_points = [
        point for row, point in zip(rows, points)
        if row.get('stage') in pre_grasp_states]
    # The recorder is enabled by VALIDATING while the asynchronous one-time
    # reset is still in flight.  Audit the whole pre-grasp interval so that a
    # legitimate staging sample cannot mask the confirmed A-point condition.
    initial_candidates = pre_grasp_points or points[:min(50, len(points))]
    initial_error = min(
        sum((point[index] - start_xyz[index]) ** 2 for index in range(3)) ** 0.5
        for point in initial_candidates)
    final = points[-1]
    placement_error = sum(
        (final[index] - place_xyz[index]) ** 2 for index in range(2)) ** 0.5
    max_z = max(point[2] for point in points)
    passed = (
        initial_error <= 0.03
        and placement_error <= place_tolerance
        and 0.74 <= final[2] <= 0.85
        and max_z >= start_xyz[2] + 0.08)
    return {
        'passed': passed, 'samples': len(rows),
        'initial_error_m': round(initial_error, 5),
        'placement_error_m': round(placement_error, 5),
        'max_z_m': round(max_z, 5),
        'final_xyz': [round(value, 5) for value in final],
    }


def analyze_acceptance(log_directory, successful_run_ids, start_xyz=(0.22, 0.12, 0.77),
                       place_xyz=(0.20, -0.16, 0.77), place_tolerance=0.07):
    """Return a machine-readable, fail-closed audit for successful runs."""
    root = Path(log_directory)
    task_events = _jsonl(root / 'events.jsonl')
    contacts = _jsonl(root / 'contacts.jsonl')
    results = _jsonl(root / 'results.jsonl')
    try:
        collision = json.loads(
            (root / 'collision_summary.json').read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        collision = {}

    sources = collision.get('sources', {})
    monitor_ok = bool(collision) and not collision.get('unsafe_latched', True)
    monitor_ok = monitor_ok and not collision.get('unavailable_topics', ['missing'])
    monitor_ok = monitor_ok and len(sources) == 3
    monitor_ok = monitor_ok and all(item.get('ready') for item in sources.values())

    audits = []
    for run_id in successful_run_ids:
        states = [
            item.get('state') for item in task_events
            if item.get('run_id') == run_id]
        run_contacts = [
            item for item in contacts if item.get('run_id') == run_id]
        fingers = {
            side for side in ('left_finger', 'right_finger')
            if any(
                item.get('rule') == 'finger_target_grasp_phase'
                and side in (item.get('collision1', '') + item.get('collision2', ''))
                for item in run_contacts)}
        forbidden = sum(
            item.get('verdict') == 'forbidden' for item in run_contacts)
        task_result = next((
            item for item in reversed(results)
            if item.get('run_id') == run_id), None)
        joint_path = root / f'trajectory_{run_id}.csv'
        joint_samples = 0
        if joint_path.exists():
            with joint_path.open(encoding='utf-8') as stream:
                joint_samples = max(0, sum(1 for _line in stream) - 1)
        object_stats = _trajectory_stats(
            root / f'object_trajectory_{run_id}.csv',
            start_xyz, place_xyz, place_tolerance)
        checks = {
            'state_sequence_complete': _ordered_subsequence(states, REQUIRED_STATES),
            'result_log_succeeded': bool(
                task_result and task_result.get('result') == 'SUCCEEDED'),
            'joint_trajectory_recorded': joint_samples >= 100,
            'bilateral_finger_contact': fingers == {'left_finger', 'right_finger'},
            'no_forbidden_contact': forbidden == 0,
            'object_trajectory_valid': object_stats['passed'],
        }
        audits.append({
            'run_id': run_id, 'passed': all(checks.values()), 'checks': checks,
            'joint_samples': joint_samples, 'forbidden_contacts': forbidden,
            'finger_contacts': sorted(fingers), 'object': object_stats,
        })
    return {
        'collision_monitor_healthy': monitor_ok,
        'successful_runs_audited': len(audits),
        'runs': audits,
        'passed': monitor_ok and bool(audits)
        and all(item['passed'] for item in audits),
    }
