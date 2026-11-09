"""Plot local poles and measured yaw errors from the saved attitude-gain study."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
metrics = json.loads((root / 'results/attitude_metrics.json').read_text())
cases = ['nominal', 'lower_attitude_gain', 'higher_rate_gain']
labels = ['Nominal', 'Lower $k_R$', 'Higher $k_\\Omega$']
plt.rcParams.update({'font.family':'serif', 'font.serif':['Times New Roman','Nimbus Roman'],
                     'mathtext.fontset':'stix', 'pdf.fonttype':42, 'font.size':10,
                     'axes.spines.top':False, 'axes.spines.right':False})
fig, axes = plt.subplots(2, 1, figsize=(4.6, 4.1), layout='constrained')
ax = axes[0]
for i, (case, color) in enumerate(zip(cases, ['#1f77b4','#d62728','#2ca02c'])):
    poles = sorted(metrics[case]['local_poles'])
    ax.plot(poles, [i, i], color=color, lw=.9)
    ax.scatter(poles, [i, i], color=color, marker='x', s=45, linewidths=1.5, zorder=3)
    for j, pole in enumerate(poles):
        if i == 0 and j == 1:
            continue
        text = r'$-10$ (double)' if i == 0 else f'{pole:.2f}'
        ax.annotate(text, (pole, i), xytext=(0, -15), textcoords='offset points',
                    ha='center', fontsize=9)
ax.axvline(0, color='.5', ls=':', lw=.8)
ax.set(xlim=(-42, 3), ylim=(-.5, 2.7), yticks=range(3), yticklabels=labels,
       xlabel=r'Real part of pole (s$^{-1}$)', title='(a) Local attitude response')
ax.tick_params(axis='y', length=0)
ax.grid(axis='x', color='.88', lw=.5)
ax.invert_yaxis()
ax = axes[1]
x = np.arange(3)
for offset, key, color, label in [
    (-.19, 'predicted_yaw_deg', '#1f77b4', 'Near-level prediction'),
    (.19, 'yaw_rmse_steady_deg', '#d62728', 'Measured yaw RMSE')]:
    values = [metrics[c][key] for c in cases]
    bars = ax.bar(x + offset, values, width=.34, color=color, label=label)
    ax.bar_label(bars, fmt='%.2f', fontsize=8, padding=3)
ax.set(xticks=x, xticklabels=['Nominal', 'Lower $k_R$', 'Higher $k_\\Omega$'],
       ylabel='Angle (deg)', ylim=(0, 16.5), title='(b) Predicted and observed heading lag')
ax.legend(loc='upper left', fontsize=8, frameon=True, fancybox=False,
          facecolor='white', edgecolor='black', framealpha=1)
ax.grid(axis='y', color='.9', lw=.4)
ax.set_axisbelow(True)
fig.savefig(root/'figures/gain_diagnosis.pdf', bbox_inches='tight')
plt.close(fig)
