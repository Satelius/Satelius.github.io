#!/usr/bin/env python3
"""Audit frame/force alignment and decoded no-contact tactile values."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def audit(root: Path) -> dict:
    summary = json.loads((root / 'summary.json').read_text())
    trajectory = json.loads((root / 'trajectory.json').read_text())
    files = sorted((root / 'frames').glob('frame_*.npz'))
    fps = float(summary['fps'])
    errors = []
    sides = {side: {'contact_frames': 0, 'no_contact_frames': 0,
                    'active_tactile_frames': 0, 'saturated_indent_frames': 0}
             for side in ('left', 'right')}
    evidence = []
    if len(files) != len(trajectory) or len(files) != summary['frame_count']:
        errors.append('frame/trajectory/summary lengths differ')
    for index, (path, row) in enumerate(zip(files, trajectory)):
        with np.load(path) as f:
            if int(f['frame_index'][0]) != index or row['source_frame'] != index:
                errors.append(f'{index}: frame identity mismatch')
            if not np.isclose(float(f['timestamp'][0]), index / fps, atol=1e-6):
                errors.append(f'{index}: timestamp mismatch')
            if not np.allclose(f['action'], row['target_action'], atol=1e-6):
                errors.append(f'{index}: recorded action differs from executed target')
            if not all(np.isfinite(f[key]).all() for key in ('action', 'observation.state')):
                errors.append(f'{index}: nonfinite action/state')
            for finger, side in enumerate(('left', 'right')):
                prefix = f'observation.tactile.cam_left_finger{finger}'
                depth = f[prefix + '.depth_uint16']
                mask = f[prefix + '.mask']
                fields = {key: (f[prefix + '.' + key + '_uint16'].astype(float) - 30000) / 1e6
                          for key in ('indent', 'deformation', 'shear')}
                contact = bool(row['physical_contact'][side])
                force_contact = row['contact_force_n'][side] >= summary['contact_force_threshold_n']
                if contact != force_contact:
                    errors.append(f'{index}/{side}: contact force/gate mismatch')
                sides[side]['contact_frames' if contact else 'no_contact_frames'] += 1
                active = bool(mask.any() and (fields['indent'] > 0).any())
                sides[side]['active_tactile_frames'] += int(active)
                sides[side]['saturated_indent_frames'] += int(np.mean(fields['indent'] >= .001499) > .95)
                if not contact and (depth.any() or mask.any() or any(a.any() for a in fields.values())):
                    errors.append(f'{index}/{side}: tactile signal without physical contact')
                if depth.shape != mask.shape or fields['indent'].shape != mask.shape:
                    errors.append(f'{index}/{side}: scalar shape mismatch')
                if any(fields[k].shape != (*mask.shape, 2) for k in ('deformation', 'shear')):
                    errors.append(f'{index}/{side}: vector shape mismatch')
        evidence.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    checks = {'frame_contract': not errors,
              'bilateral_contact_observed': all(s['contact_frames'] > 0 for s in sides.values()),
              'bilateral_tactile_observed': all(s['active_tactile_frames'] > 0 for s in sides.values()),
              'no_contact_observed_both_sides': all(s['no_contact_frames'] > 0 for s in sides.values()),
              'all_requested_actions_recorded': len(files) == summary['source_action_count']}
    fidelity_review = any(
        stats['contact_frames'] > 0 and stats['saturated_indent_frames'] == stats['contact_frames']
        for stats in sides.values())
    return {'schema': 'tacharness.p0_tactile_audit.v1', 'checks': checks,
            'frame_and_contact_contract_passed': all(checks.values()),
            'sensor_fidelity_review_required': fidelity_review,
            'passed': all(checks.values()) and not fidelity_review, 'task_success': summary['success'],
            'policy_mode': summary.get('policy_mode', 'recorded_action_replay'), 'p0_complete': False,
            'frames': len(files), 'sides': sides, 'errors': errors, 'frame_evidence': evidence,
            'note': 'Saturation counts require visual/geometry inspection; populated fields alone do not prove sensor fidelity.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'frame_evidence'}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
