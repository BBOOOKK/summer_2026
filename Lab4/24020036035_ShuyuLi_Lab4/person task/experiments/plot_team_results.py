"""Plot native Unity states at the final two-column report dimensions.

The tracking figure connects the measured course, execution error, and gate
aperture offsets. Timing uses saved gate events; error uses native pose samples
and the saved reference on the same simulation clock. Screenshots are arranged
without cropping, retouching, or changing their contents.
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from mpl_toolkits.mplot3d import proj3d

ROOT = Path(__file__).resolve().parents[1]
TEAM = ROOT.parent / "team task"
DATA = TEAM / "data"
FIG = ROOT.parent / "report" / "source" / "figures"
FRAMES = ROOT.parent / "report" / "source" / "frames"
FIG.mkdir(parents=True, exist_ok=True)
BLACK, BLUE, GREEN, RED = "black", "blue", "green", "red"
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix", "mathtext.fallback": "stix",
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .65, "axes.labelcolor": BLACK, "text.color": BLACK,
    "xtick.color": BLACK, "ytick.color": BLACK, "axes.axisbelow": True,
    "grid.alpha": .18, "grid.linewidth": .5, "lines.linewidth": 1.4,
    "legend.frameon": True, "legend.edgecolor": "black",
    "legend.facecolor": "white", "legend.framealpha": 1,
    "legend.fancybox": False, "pdf.fonttype": 42, "svg.fonttype": "none",
    "savefig.facecolor": "white", "figure.facecolor": "white",
})


def read(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def export(fig, name):
    for axis in fig.axes:
        legend = axis.get_legend()
        if legend is not None:
            legend.set_frame_on(True)
            legend.get_frame().set_edgecolor("black")
            legend.get_frame().set_linewidth(.8)
    for ext in ["pdf", "svg", "png"]:
        temporary = FIG / f"{name}.rendering.{ext}"
        fig.savefig(temporary, dpi=400 if name=='team_unity_frames' else 260)
        temporary.replace(FIG / f"{name}.{ext}")
    plt.close(fig)


def panel(ax, letter, title):
    ax.set_title(f"{letter}  {title}" if letter else title,
                 loc="left", fontweight="bold", pad=8)
    ax.grid(True)
    ax.tick_params(length=3, width=.6)


state = np.genfromtxt(DATA / "actual_states.csv", delimiter=",", names=True)
ref = np.genfromtxt(DATA / "optimized_reference.csv", delimiter=",", names=True)
rotor = np.genfromtxt(DATA / "actual_rotors.csv", delimiter=",", names=True)
timer = read("race_timer.json")
gates = read("gates.json")
origin = read("pilot_start.json")["stamp"]
t = state["stamp_ns"] / 1e9 - origin
start, finish = [(timer[k] / 1e9 - origin) for k in ["start_stamp_ns", "finish_stamp_ns"]]
active = (t >= -1e-7) & (t <= ref["t"][-1] + 1e-6)
race = (state["stamp_ns"] >= timer["start_stamp_ns"]) & (state["stamp_ns"] <= timer["finish_stamp_ns"])
p = np.column_stack([state[k] for k in "xyz"])
v = np.column_stack([state[k] for k in ["vx", "vy", "vz"]])
reference = np.column_stack([np.interp(t, ref["t"], ref[k]) for k in "xyz"])
error = p - reference
norm_error = np.linalg.norm(error, axis=1)
speed = np.linalg.norm(v, axis=1)
crossings = timer["crossings"]
hs = np.array([c["horizontal_m"] for c in crossings])
zs = np.array([c["vertical_m"] for c in crossings])
margin = .5 - np.maximum(abs(hs), abs(zs))
saved_runs = read("run_times.json")
repeated = [r for r in saved_runs if round(r["race_ms"] / 1000, 3) == .640]


def metrics(mask):
    return {"native_samples": int(mask.sum()),
            "position_rmse_m": float(np.sqrt(np.mean(norm_error[mask] ** 2))),
            "maximum_position_error_m": float(norm_error[mask].max())}


summary = {
    "timing_definition": "Ordered forward gate 1 to gate 12 crossings in simulation time",
    "native_physics_step_s": .02, "gate_to_gate_s": timer["elapsed_ms"] / 1000,
    "launch_to_finish_s": finish, "trajectory_execution": metrics(active),
    "gate_to_gate": metrics(race), "minimum_point_to_aperture_edge_m": float(margin.min()),
    "peak_native_pose_speed_m_s": float(speed[active].max()),
    "saved_valid_0640_runs": len(repeated),
    "repeat_range_us": (max(r["race_ms"] for r in repeated) - min(r["race_ms"] for r in repeated)) * 1000,
    "reference_alignment": "Linear interpolation of saved reference at native state timestamps",
}
(ROOT / "experiments" / "team_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
with (ROOT / "experiments" / "team_source_data.csv").open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["time_since_launch_s", "race_sample", "x", "y", "z", "ref_x", "ref_y", "ref_z", "position_error_m", "speed_m_s"])
    for i in np.flatnonzero(active):
        writer.writerow([t[i], int(race[i]), *p[i], *reference[i], norm_error[i], speed[i]])

gate_centres=np.array([gate['position'] for gate in gates])
fig,ax=plt.subplots(figsize=(.96,.36))
fig.subplots_adjust(left=.02,right=.98,bottom=.04,top=.96)
ax.plot(gate_centres[:,0],gate_centres[:,1],color='gray',ls='--',lw=.45)
for gate in gates:
    centre,tangent=np.array(gate['position']),np.array(gate['horizontal'])
    ends=centre+np.array([-.65,.65])[:,None]*tangent
    ax.plot(ends[:,0],ends[:,1],color=BLACK,lw=.6)
ax.scatter(gate_centres[:,0],gate_centres[:,1],s=2,color=BLACK)
ax.set_aspect('equal');ax.set_axis_off()
export(fig,'pipeline_geometry')

fig,ax=plt.subplots(figsize=(.96,.36))
fig.subplots_adjust(left=.02,right=.98,bottom=.04,top=.96)
ax.plot(ref['x'],ref['y'],color=BLUE,lw=.7)
ax.scatter(gate_centres[:,0],gate_centres[:,1],s=2,color=BLACK,zorder=3)
ax.set_aspect('equal');ax.set_axis_off()
export(fig,'pipeline_reference')

fig,ax=plt.subplots(figsize=(.96,.36))
fig.subplots_adjust(left=.03,right=.97,bottom=.04,top=.96)
window=(ref['t']>=.30-1e-8)&(ref['t']<=.50+1e-8)
ax.vlines(ref['t'][window],0,ref['z'][window],color=BLACK,lw=.45)
ax.plot(ref['t'][window],ref['z'][window],color='gray',lw=.35)
ax.scatter(ref['t'][window],ref['z'][window],color=BLUE,s=3.5,zorder=3)
ax.axhline(0,color=BLACK,lw=.45)
ax.set(ylim=(0,float(ref['z'][window].max())*1.12))
ax.set_axis_off()
export(fig,'pipeline_samples')

# Hero trajectory with three aligned quantitative panels.
fig = plt.figure(figsize=(7.1, 4.00))
grid = fig.add_gridspec(3, 2, width_ratios=[1.05, 1.10], hspace=.88, wspace=.42,
                       left=.045, right=.985, bottom=.11, top=.90)
ax = fig.add_subplot(grid[:, 0], projection='3d')
ax.set_proj_type('ortho')
ax.plot(ref['x'],ref['y'],ref['z'],color='gray',ls='--',lw=1,label='Optimized reference')
ax.plot(*p[active].T,color=GREEN,lw=1.1,label='Native Unity poses')
ax.plot(*p[race].T,color=RED,lw=1.5,label='Timed interval')
for i, gate in enumerate(gates):
    centre, tangent = np.array(gate["position"]), np.array(gate["horizontal"])
    ring=centre+np.array([-.5,.5,.5,-.5,-.5])[:,None]*tangent+np.array([-.5,-.5,.5,.5,-.5])[:,None]*np.array([0,0,1])
    ax.plot(*ring.T,color=BLACK,lw=.65)
ax.set(xlabel='x (m)',ylabel='y (m)',zlabel='z (m)',zlim=(.5,5.5))
ax.view_init(elev=26,azim=-61);ax.set_box_aspect((1.45,1,.80))
ax.tick_params(pad=0,labelsize=6)
label_offsets={1:(5,5),2:(5,5),3:(5,5),4:(-6,5),5:(-7,5),6:(7,8),7:(7,5),8:(-8,10),9:(5,5),10:(-5,5),11:(-5,7),12:(11,9)}
for i,gate in enumerate(gates,1):
    x2,y2,_=proj3d.proj_transform(*gate['position'],ax.get_proj())
    ax.annotate(str(i),xy=(x2,y2),xytext=label_offsets[i],textcoords='offset points',
                ha='center',va='bottom',fontsize=6.2,color=BLACK,
                bbox={'facecolor':'white','edgecolor':'none','pad':.25},
                arrowprops={'arrowstyle':'-','color':'black','linewidth':.4,'shrinkA':1,'shrinkB':1})
for axis in [ax.xaxis,ax.yaxis,ax.zaxis]:
    axis.pane.fill=False;axis._axinfo['grid']['color']=(0,0,0,.13)
ax.legend(loc='upper left',fontsize=5.9,handlelength=1.6,borderaxespad=.2)
panel(ax, 'a', 'Native course and gate geometry')
ax.set_title('',loc='left')
fig.text(.045,.922,'a  Native course and gate geometry',fontsize=8.5,fontweight='bold',va='bottom')

ax = fig.add_subplot(grid[0, 1])
ax.axvspan(start, finish, color=RED, alpha=.075, lw=0)
ax.plot(t[active], norm_error[active], color=BLUE)
ax.scatter(t[race], norm_error[race], s=9, color=BLUE, zorder=3)
ax.axvline(start, color=RED, lw=.8, ls=":")
ax.axvline(finish, color=RED, lw=.8, ls=":")
ax.set(xlim=(0, ref["t"][-1]), ylim=(0, .112), xlabel="Time since launch (s)", ylabel="Position error (m)")
ax.text(.02, .91, "Timed RMSE  0.06267 m", transform=ax.transAxes, fontsize=7.5,
        va="top", bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
panel(ax, "b", "Tracking through launch, race, and braking")

ax = fig.add_subplot(grid[2, 1])
idx = np.arange(1, 13)
ax.bar(idx - .18, hs, width=.34, color=BLUE, label="Horizontal")
ax.bar(idx + .18, zs, width=.34, color=RED, label="Vertical")
ax.axhline(.5, color=BLACK, ls="--", lw=.8)
ax.axhline(-.5, color=BLACK, ls="--", lw=.8)
ax.set(xlim=(.35, 12.65), ylim=(-.62, .90), xticks=idx, xlabel="Gate", ylabel="Crossing offset (m)")
ax.legend(loc="upper left", ncol=2, fontsize=6.7, borderaxespad=.3)
ax.text(.97, .04, "Minimum margin  0.287 m", transform=ax.transAxes, fontsize=7.2, ha="right",
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
panel(ax, "d", "Every crossing remains inside the aperture")
ax = fig.add_subplot(grid[1, 1])
ax.axvspan(start, finish, color=RED, alpha=.075, lw=0)
ax.plot(t[active], speed[active], color=GREEN)
ax.set(xlabel="Time since launch (s)", ylabel="Speed (m/s)", xlim=(0, 1.54))
ax.text(.98, .95, "Peak 435.34 m/s", transform=ax.transAxes,
        ha="right", va="top", fontsize=7.2)
panel(ax, "c", "Native-pose speed")
export(fig, "team_tracking")

fig, axes = plt.subplots(4,1,sharex=True,figsize=(3.45,2.60))
fig.subplots_adjust(left=.23,right=.98,bottom=.18,top=.89,hspace=.16)
rt = rotor["stamp_ns"] / 1e9 - origin
rm = (rt >= -1e-7) & (rt <= ref["t"][-1] + 1e-6)
for k,(ax,c) in enumerate(zip(axes,[BLUE,RED,GREEN,BLACK])):
    ax.plot(rt[rm],rotor[f'rotor{k}'][rm],color=c,lw=.85)
    for bound in [-2000,2000]:ax.axhline(bound,color=BLACK,ls='--',lw=.4)
    ax.set(xlim=(0,1.54),ylim=(-2350,2350),yticks=[-2000,0,2000])
    ax.tick_params(axis='y',labelsize=5.2,length=2,pad=2)
    ax.tick_params(axis='x',labelsize=6,length=2)
    ax.grid(True,alpha=.12)
    ax.text(.82,.79,f'Rotor {k+1}',transform=ax.transAxes,ha='right',va='top',fontsize=6,
            bbox={'facecolor':'white','edgecolor':'black','linewidth':.5,'pad':1.1})
axes[-1].set_xlabel('Time since launch (s)')
fig.text(.025,.55,'Rotor command (rad/s)',rotation=90,va='center',fontsize=8)
fig.suptitle('Native-grid rotor actuation',fontsize=8.5,fontweight='bold',y=.98)
export(fig, "team_execution")

# Preserve saved-run identity; sorting denotes score order, not time sequence.
fig, ax = plt.subplots(figsize=(3.45, 2.60))
fig.subplots_adjust(left=.20, right=.97, bottom=.18, top=.88)
times = np.array([r["race_ms"] for r in repeated])
excess = (times - times.min()) * 1000
ax.scatter(np.arange(1, len(times) + 1), excess, color=GREEN, s=20, zorder=3)
ax.vlines(np.arange(1,len(times)+1),0,excess,color='black',lw=.7,zorder=2)
ax.axhline(0, color=RED, ls="--", lw=.9)
ax.set(xlabel="Saved valid run (ordered by elapsed time)", ylabel="Excess time ($\\mu$s)",
       xlim=(.4, 13.6), ylim=(-5, 65), xticks=[1, 4, 7, 10, 13])
ax.grid(True)
fig.suptitle('13 saved runs round to 0.640 s',fontsize=8.5,fontweight='bold',y=.98)
ax.text(.03,.91,'Baseline: 639.703796 ms',transform=ax.transAxes,fontsize=6.6)
ax.annotate(f'{excess[-1]:.3f} $\\mu$s',xy=(13,excess[-1]),xytext=(8.8,61),fontsize=6.4,
            arrowprops={'arrowstyle':'-','color':'black','linewidth':.6})
detail=ax.inset_axes([.15,.36,.55,.39])
detail.scatter(np.arange(1,11),excess[:10],s=8,color=GREEN,zorder=3)
detail.vlines(np.arange(1,11),0,excess[:10],lw=.5,color='black')
detail.set(xlim=(.5,10.5),ylim=(-.05,1.05),xticks=[1,5,10],yticks=[0,.5,1])
detail.set_title('First ten runs: $\\mu$s detail',fontsize=5.9,pad=2)
detail.tick_params(labelsize=5,length=2,pad=1)
detail.grid(True,alpha=.12)
for spine in detail.spines.values():spine.set_visible(True);spine.set_color('black');spine.set_linewidth(.55)
ax.indicate_inset_zoom(detail,edgecolor='black',linewidth=.5,alpha=.6,zorder=1)
export(fig, "team_repeatability_vector")

# Native frames: no crop, contrast changes, or generated visual content.
fig, axes = plt.subplots(3, 4, figsize=(7.1, 4.55))
fig.subplots_adjust(left=.005, right=.995, bottom=.015, top=.80, wspace=.035, hspace=.18)
timeline=fig.add_axes([.055,.900,.90,.055])
event_ms=np.array([c['elapsed_ms'] for c in crossings])
timeline.hlines(.5,0,event_ms[-1],color='black',lw=.8)
timeline.scatter(event_ms,np.full(12,.5),s=12,color=BLUE,zorder=3)
timeline.scatter(event_ms[-1],.5,s=18,color=RED,zorder=4)
for j,moment in enumerate(event_ms):timeline.text(moment,.85,f'{j+1:02d}',ha='center',va='bottom',fontsize=6)
timeline.set(xlim=(-8,648),ylim=(0,1.3),yticks=[],xticks=[0,200,400,event_ms[-1]])
timeline.set_xticklabels(['0','200','400','640'])
timeline.tick_params(axis='x',labelsize=6,length=2,pad=1)
timeline.set_xlabel('Gate-crossing timeline: simulation time from gate 1 (ms)',fontsize=6.7,labelpad=2)
for spine in ['top','right','left']:timeline.spines[spine].set_visible(False)
timeline.spines['bottom'].set_linewidth(.5);timeline.grid(False)
fig.suptitle('Twelve-gate Unity flight sequence',fontsize=9,fontweight='bold',y=.993)
for i, ax in enumerate(axes.flat):
    ax.imshow(plt.imread(FRAMES / f"gate_{i+1:02d}.png"))
    ax.set_axis_off()
    ax.set_title(f"Gate {i+1:02d}  |  {crossings[i]['elapsed_ms']:.3f} ms", fontsize=7.0,
                 loc="left", color=BLACK, pad=4)
export(fig, "team_unity_frames")
print(json.dumps(summary, indent=2))
