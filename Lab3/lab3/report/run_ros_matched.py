#!/usr/bin/env python3
"""Matched numerical experiment: ROS gains, ROS inertia, 1.25 m/s, smooth start."""
from pathlib import Path
import json, numpy as np
import sys
if '--plot-only' not in sys.argv:
    from scipy.integrate import solve_ivp
    from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
FIG, OUT = ROOT / 'figures', ROOT / 'results'
m = 1.0; g = 9.81
J_num = np.eye(3)
J_ros = np.diag([0.1, 0.2, 0.1])
cf, cd, arm = 1e-3, 1e-5, 0.3
F = np.array([[cf]*4,[1,1,-1,-1],[-1,1,1,-1],[cd,-cd,cd,-cd]], float)
F[1:3] *= cf * arm / np.sqrt(2); FI = np.linalg.inv(F)
e3 = np.array([0., 0., 1.]); D = np.array([.1, .1, .2])

def cross(a, b):
    return np.cross(a, b)

def ref(t, scale=4., smooth=True, hold=0.0):
    t = t - hold
    if t < 0:
        return np.array([0., 5., 2.]), np.zeros(3), np.zeros(3), 0.
    w = 1 / scale; T = 4.
    if smooth and t < T:
        u = t / T
        th = w * T * (2.5 * u**4 - 3 * u**5 + u**6)
        wd = w * (10 * u**3 - 15 * u**4 + 6 * u**5)
        wdd = w / T * (30 * u**2 - 60 * u**3 + 30 * u**4)
    else:
        th = w * (t - (T / 2 if smooth else 0)); wd = w; wdd = 0.
    sn, cs = np.sin(th), np.cos(th)
    p = np.array([5 * sn, 5 * cs, 2.])
    v = np.array([5 * cs * wd, -5 * sn * wd, 0.])
    a = np.array([5 * (cs * wdd - sn * wd * wd), -5 * (sn * wdd + cs * wd * wd), 0.])
    return p, v, a, -th

def control(t, y, c):
    x, v, q, om = y[:3], y[3:6], y[6:10], y[10:13]
    R = Rotation.from_quat(q).as_matrix()
    J = c.get('J', J_num)
    pd, vd, ad, yaw = ref(t, c.get('scale', 4), c.get('smooth', True), c.get('hold', 0))
    kx, kv = c.get('kx', 2), c.get('kv', 2.8)
    kz = c.get('kz', kx)
    ki_z = c.get('ki_z', 0.0)
    # state carries iz in y[13] if present
    iz = y[13] if len(y) > 13 else 0.0
    A = -np.array([kx, kx, kz]) * (x - pd) - kv * (v - vd) + g * e3 + ad
    A = A + np.array([0., 0., ki_z * iz])
    b3 = A / np.linalg.norm(A)
    b1c = np.array([np.cos(yaw), np.sin(yaw), 0.])
    b2 = cross(b3, b1c); b2 /= np.linalg.norm(b2)
    Rd = np.column_stack([cross(b2, b3), b2, b3])
    E = (Rd.T @ R - R.T @ Rd) / 2
    er = np.array([E[2, 1], E[0, 2], E[1, 0]])
    f = A @ R[:, 2]
    M = -c.get('kR', 4) * er - c.get('kOmega', 1.2) * om + cross(om, J @ om)
    return f, M, R, pd, Rd, yaw

def rhs(t, y, c):
    f, M, R, *_ = control(t, y, c)
    om = y[10:13]; q = y[6:10]; J = c.get('J', J_num)
    qdot = np.r_[.5 * (q[3] * om + cross(q[:3], om)), -.5 * (q[:3] @ om)]
    # always integrate iz state if length>13
    acc = -g * e3 + f * R[:, 2]
    base = np.r_[y[3:6], acc, qdot, np.linalg.solve(J, M - cross(om, J @ om))]
    if len(y) > 13:
        ez = 2.0 - y[2]
        return np.r_[base, ez]
    return base

def run(name, c, T=80.0):
    use_iz = c.get('ki_z', 0) != 0
    y0 = np.r_[np.array([0., 5., 2.]), np.zeros(3), [0., 0., 0., 1.], np.zeros(3)]
    if use_iz:
        y0 = np.r_[y0, 0.0]
    t = np.arange(0, T + 1e-9, 0.01)
    sol = solve_ivp(lambda a, b: rhs(a, b, c), (0, T), y0, t_eval=t, method='DOP853',
                    rtol=1e-8, atol=1e-10, max_step=0.02)
    assert sol.success, sol.message
    y = sol.y.T
    vals = [control(a, b, c) for a, b in zip(t, y)]
    pd = np.array([z[3] for z in vals])
    err = np.linalg.norm(y[:, :3] - pd, axis=1)
    yaw = np.array([np.arctan2(z[2][1, 0], z[2][0, 0]) for z in vals])
    yd = np.array([ref(a, c.get('scale', 4), c.get('smooth', True), c.get('hold', 0))[3] for a in t])
    ye = np.rad2deg(np.arctan2(np.sin(yaw - yd), np.cos(yaw - yd)))
    # steady after 20s (past hold+ramp if any)
    mask = t >= 20
    z = y[:, 2]
    metrics = {
        'rmse_all': float(np.sqrt(np.mean(err**2))),
        'rmse_steady': float(np.sqrt(np.mean(err[mask]**2))),
        'height_mean_steady': float(z[mask].mean()),
        'height_bias_steady': float(z[mask].mean() - 2),
        'height_rmse_steady': float(np.sqrt(np.mean((z[mask] - 2)**2))),
        'yaw_rmse_steady_deg': float(np.sqrt(np.mean(ye[mask]**2))),
        'radial_rmse_steady': float(np.sqrt(np.mean((np.sqrt(y[mask, 0]**2 + y[mask, 1]**2) - 5)**2))),
        'max_steady': float(err[mask].max()),
    }
    np.savetxt(OUT / f'{name}.csv', np.column_stack([t, y[:, :13], pd, err, ye, z - 2]),
               delimiter=',', header='t,x,y,z,vx,vy,vz,qx,qy,qz,qw,wx,wy,wz,xd,yd,zd,error,yaw_error_deg,ez', comments='')
    print(name, metrics, flush=True)
    return dict(t=t, y=y, pd=pd, err=err, ye=ye, metrics=metrics, c=c)

def main():
    cases = {
        'ros_matched': dict(scale=4, smooth=True, hold=0, kx=2, kv=2.8, kR=4, kOmega=1.2, J=J_ros),
        'ros_matched_integral': dict(scale=4, smooth=True, hold=0, kx=2, kv=2.8, kR=4, kOmega=1.2, J=J_ros, ki_z=1.2, kz=3.5),
        'num_nominal_slow': dict(scale=4, smooth=True, hold=0, kx=4, kv=4, kR=100, kOmega=20, J=J_num),
    }
    runs = {k: run(k, v) for k, v in cases.items()}
    (OUT / 'ros_matched_metrics.json').write_text(json.dumps({k: v['metrics'] for k, v in runs.items()}, indent=2))
    plot_comparison()

def plot_comparison():
    plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'Nimbus Roman', 'Liberation Serif'], 'mathtext.fontset': 'stix', 'pdf.fonttype': 42, 'font.size': 10})
    fig, axes = plt.subplots(1, 3, figsize=(8.2, 2.7), layout='constrained')
    cases = [('num_nominal_slow', 'High gain', '-'), ('ros_matched', 'ROS baseline', '--'),
             ('ros_matched_integral', 'ROS integral', ':')]
    panels = [('error', '(a) Position error', 'Error (m)'), ('z', '(b) Altitude', 'Height (m)'),
              ('yaw_error_deg', '(c) Heading error', 'Error (deg)')]
    for (filename, label, style), color in zip(cases, ['#2ca02c','#1f77b4','#d62728']):
        data = np.genfromtxt(OUT / (filename + '.csv'), delimiter=',', names=True)
        for ax, (field, title, unit) in zip(axes, panels):
            ax.plot(data['t'], data[field], style, color=color, lw=1.3, label=label)
            ax.set(xlabel='Time (s)', ylabel=unit, title=title)
            ax.spines[['right', 'top']].set_visible(False)
    axes[0].legend(frameon=True, edgecolor='black', facecolor='white', framealpha=1.0, fancybox=False, fontsize=8)
    fig.savefig(FIG / 'ros_matched_postfix.pdf', bbox_inches='tight')
    plt.close(fig)

if __name__ == '__main__':
    if '--plot-only' in sys.argv:
        plot_comparison()
    else:
        main()
