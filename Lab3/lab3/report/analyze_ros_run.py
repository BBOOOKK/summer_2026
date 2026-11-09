#!/usr/bin/env python3
"""ROS / Unity flight metrics: sample RMSE, time-weighted RMSE, height bias, yaw, alignment notes."""
from pathlib import Path
import numpy as np, json, argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def yaw_from_quat(qx, qy, qz, qw):
    siny = 2 * (qw * qz + qx * qy)
    cosy = 1 - 2 * (qy * qy + qz * qz)
    return np.arctan2(siny, cosy)

def analyze(csv_path, out_dir, fig_stem='ros_flight_metrics', window=(30.0, None), label='Unity state'):
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    v = np.genfromtxt(csv_path, delimiter=',', names=True)
    names = v.dtype.names
    t = v['time']
    # Prefer mission_t window if present; else absolute time
    if 'mission_t' in names:
        tm = v['mission_t']
        t0, t1 = window[0], window[1] if window[1] is not None else tm.max()
        mask = (tm >= t0) & (tm <= t1) & np.isfinite(v['error'])
        tw = tm
    else:
        t0, t1 = window[0], window[1] if window[1] is not None else t.max()
        mask = (t >= t0) & (t <= t1) & np.isfinite(v['error'])
        tw = t
    d = v[mask]
    twm = tw[mask]
    e = d['error']
    dt = np.diff(twm)
    if len(e) < 2 or not np.all(dt > 0):
        raise ValueError("The evaluation window needs at least two strictly increasing timestamps.")
    w = np.r_[dt, 0.0]
    ez = d['z'] - 2.0
    rad = np.sqrt(d['x']**2 + d['y']**2) - 5.0
    # yaw
    yaw = yaw_from_quat(d['qx'], d['qy'], d['qz'], d['qw'])
    if np.isfinite(d['xd']).all():
        theta = np.arctan2(d['xd'], d['yd'])
    else:
        theta = np.arctan2(d['x'], d['y'])
    psi_d = -theta
    ye = np.arctan2(np.sin(yaw - psi_d), np.cos(yaw - psi_d))
    # Preserve the recorded tracking error; derive the other components from the logged fields.
    align_note = 'Position RMSE uses the recorded error column; radial, height and yaw errors are computed from logged state and reference fields.'
    phase = np.unwrap(np.arctan2(d['x'], d['y']))
    laps = abs(phase[-1] - phase[0]) / (2 * np.pi)
    mse = np.mean(e**2)
    vert_share = float(np.mean(ez**2) / mse * 100) if mse > 0 else 0.0
    m = {
        'csv': str(csv_path),
        'window_start_s': float(twm[0]),
        'window_end_s': float(twm[-1]),
        'samples': int(len(d)),
        'dt_min_s': float(dt.min()) if len(dt) else None,
        'dt_median_s': float(np.median(dt)) if len(dt) else None,
        'dt_max_s': float(dt.max()) if len(dt) else None,
        'position_rmse_sample_m': float(np.sqrt(np.mean(e**2))),
        'position_rmse_time_weighted_m': float(np.sqrt(np.sum(w * e**2) / np.sum(w))),
        'position_max_m': float(np.max(e)),
        'radial_rmse_m': float(np.sqrt(np.mean(rad**2))),
        'height_rmse_m': float(np.sqrt(np.mean(ez**2))),
        'height_rmse_time_weighted_m': float(np.sqrt(np.sum(w * ez**2) / np.sum(w))),
        'height_mean_m': float(np.mean(d['z'])),
        'height_bias_m': float(np.mean(d['z']) - 2.0),
        'vertical_mse_share_pct': vert_share,
        'yaw_rmse_deg': float(np.rad2deg(np.sqrt(np.mean(ye**2)))),
        'yaw_rmse_time_weighted_deg': float(np.rad2deg(np.sqrt(np.sum(w * ye**2) / np.sum(w)))),
        'laps_in_window': float(laps),
        'median_state_period_s': float(np.median(dt)),
        'rmse_definition': 'sample_equal_weight = sqrt(mean(e_i^2)); time_weighted = sqrt(sum(w_i e_i^2)/sum(w_i)) with w_i = Delta t_i (left rectangle).',
        'time_alignment_note': align_note,
    }
    (root / 'flight_metrics.json').write_text(json.dumps(m, indent=2))
    plt.rcParams.update({'font.family':'serif', 'font.serif':['Times New Roman','Nimbus Roman','Liberation Serif'], 'mathtext.fontset':'stix', 'pdf.fonttype':42, 'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False, 'axes.grid':True, 'grid.alpha':.18})
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 4.8), layout='constrained')
    ax = axes[0, 0]
    ax.plot(d['xd'], d['yd'], '--', color='#2ca02c', label='Reference')
    ax.plot(d['x'], d['y'], color='#1f77b4', lw=.8, label='Unity')
    ax.set(xlabel='x (m)', ylabel='y (m)', title='(a) Horizontal path', aspect='equal')
    ax.legend(frameon=True, edgecolor='black', facecolor='white', framealpha=1.0, fancybox=False)
    for ax, values, unit, title, metric in [
        (axes[0,1], e, 'Error (m)', '(b) Position error', m['position_rmse_sample_m']),
        (axes[1,0], d['z'], 'Altitude (m)', '(c) Vertical response', 2.0),
        (axes[1,1], np.rad2deg(ye), 'Yaw error (deg)', '(d) Heading error', m['yaw_rmse_deg'])]:
        ax.plot(twm, values, color='#1f77b4', lw=.75)
        ax.axhline(metric, color='#d62728', ls='--', lw=1, label='Target' if ax is axes[1,0] else 'Sample RMSE')
        ax.legend(frameon=True, edgecolor='black', facecolor='white', framealpha=1.0, fancybox=False, fontsize=8)
        ax.set(xlabel='Time (s)', ylabel=unit, title=title)
    fig_path = Path(__file__).resolve().parent / 'figures'
    fig_path.mkdir(exist_ok=True)
    fig.savefig(fig_path / f'{fig_stem}.pdf', bbox_inches='tight')
    fig.savefig(fig_path / f'{fig_stem}.png', dpi=180, bbox_inches='tight')
    plt.close(fig)
    print(json.dumps(m, indent=2))
    return m

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--out', default=None)
    ap.add_argument('--stem', default='ros_flight_metrics')
    ap.add_argument('--start', type=float, default=30.0)
    ap.add_argument('--end', type=float, default=None)
    a = ap.parse_args()
    out = a.out or str(Path(a.csv).resolve().parent)
    analyze(a.csv, out, fig_stem=a.stem, window=(a.start, a.end))
