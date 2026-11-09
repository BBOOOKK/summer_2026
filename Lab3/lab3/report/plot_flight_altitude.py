"""Plot measured Unity altitudes alongside the saved vertical-force experiments."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
flight = root.parent / 'flight'
plt.rcParams.update({'font.family':'serif', 'font.serif':['Times New Roman','Nimbus Roman','Liberation Serif'], 'mathtext.fontset':'stix', 'pdf.fonttype':42, 'font.size':10})
fig, axes = plt.subplots(1, 3, figsize=(9, 2.85), layout='constrained')
bias = []
for name, label, line in [('ros_unity_flight', 'Initial', '--'), ('unity_reflight', 'New flight', '-')]:
    d = np.genfromtxt(flight / (name + '.csv'), delimiter=',', names=True)
    t = d['mission_t'] if 'mission_t' in d.dtype.names else d['time']
    lo, hi = (30, 105.78) if name == 'ros_unity_flight' else (20, 100)
    valid = (t >= lo) & (t <= hi) & np.isfinite(d['error'])
    axes[0].plot(t[valid], d['z'][valid], line, color='#d62728' if name=='ros_unity_flight' else '#1f77b4', lw=.75, label=label)
    bias.append(d['z'][valid].mean() - 2)
for name, label, line in [('bias_none_ros', 'No external force', ':'), ('bias_unfixed', 'Baseline, -0.5 N', '--'), ('bias_fixed', 'Retuned, -0.5 N', '-')]:
    d = np.genfromtxt(root / 'results' / (name + '.csv'), delimiter=',', names=True)
    axes[1].plot(d['t'], d['z'], line, color={'bias_none_ros':'#2ca02c','bias_unfixed':'#d62728','bias_fixed':'#1f77b4'}[name], lw=.9, label=label)
model = json.loads((root/'results/altitude_bias_fix.json').read_text())
bias += [model[name]['height_bias'] for name in ('bias_unfixed', 'bias_fixed')]
for ax, title in zip(axes[:2], ['(a) Recorded flights','(b) Numerical force test']):
    ax.axhline(2, color='.65', lw=.7)
    ax.set(xlabel='Time (s)', ylabel='Height (m)', title=title)
    ax.legend(frameon=True, edgecolor='black', facecolor='white', framealpha=1.0, fancybox=False, fontsize=8)
axes[2].bar(range(4), bias, color=['#d62728','#1f77b4','#d62728','#1f77b4'])
axes[2].set_xticks(range(4), ['Unity\ninitial','Unity\nnew','Model\ninitial','Model\nretuned'], fontsize=8)
axes[2].set(ylabel='Mean height bias (m)', title='(c) Height bias')
axes[2].axhline(0,color='.3',lw=.7)
for ax in axes: ax.spines[['right','top']].set_visible(False)
fig.savefig(root/'figures/altitude_bias_postfix.pdf',bbox_inches='tight')
