import csv
import json

from robot_pick_place_sim.evidence import REQUIRED_STATES, analyze_acceptance


def _write_jsonl(path, records):
    path.write_text(
        ''.join(json.dumps(item) + '\n' for item in records), encoding='utf-8')


def _valid_artifacts(root, run_id='run-1'):
    _write_jsonl(root / 'events.jsonl', [
        {'run_id': run_id, 'state': state} for state in REQUIRED_STATES])
    _write_jsonl(root / 'results.jsonl', [
        {'run_id': run_id, 'result': 'SUCCEEDED'}])
    _write_jsonl(root / 'contacts.jsonl', [
        {'run_id': run_id, 'verdict': 'allowed',
         'rule': 'finger_target_grasp_phase',
         'collision1': f'mecharm270::{side}', 'collision2': 'target_object'}
        for side in ('left_finger', 'right_finger')])
    (root / 'collision_summary.json').write_text(json.dumps({
        'unsafe_latched': False, 'unavailable_topics': [],
        'sources': {name: {'ready': True} for name in ('table', 'target', 'robot')},
    }), encoding='utf-8')
    with (root / f'trajectory_{run_id}.csv').open('w', encoding='utf-8') as stream:
        stream.write('header\n' + 'sample\n' * 100)
    with (root / f'object_trajectory_{run_id}.csv').open(
            'w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['x', 'y', 'z'])
        writer.writeheader()
        for index in range(120):
            fraction = index / 119
            z = 0.77 + 0.12 * min(1.0, fraction * 2)
            if fraction > 0.5:
                z = 0.89 - 0.12 * ((fraction - 0.5) * 2)
            writer.writerow({
                'x': 0.22 - 0.02 * fraction,
                'y': 0.12 - 0.28 * fraction, 'z': z})


def test_complete_physical_evidence_passes(tmp_path):
    _valid_artifacts(tmp_path)
    audit = analyze_acceptance(tmp_path, ['run-1'])
    assert audit['passed'] is True
    assert audit['runs'][0]['passed'] is True


def test_forbidden_contact_fails_closed(tmp_path):
    _valid_artifacts(tmp_path)
    with (tmp_path / 'contacts.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({
            'run_id': 'run-1', 'verdict': 'forbidden',
            'rule': 'robot_table', 'collision1': 'link3',
            'collision2': 'table'}) + '\n')
    audit = analyze_acceptance(tmp_path, ['run-1'])
    assert audit['passed'] is False
    assert audit['runs'][0]['checks']['no_forbidden_contact'] is False


def test_missing_contact_source_fails_closed(tmp_path):
    _valid_artifacts(tmp_path)
    summary = json.loads((tmp_path / 'collision_summary.json').read_text())
    summary['sources'].pop('robot')
    (tmp_path / 'collision_summary.json').write_text(json.dumps(summary))
    assert analyze_acceptance(tmp_path, ['run-1'])['passed'] is False
