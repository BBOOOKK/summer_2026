"""Create print-sized figures for the English ICRA report from the same experiments."""
import ast
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parents[1]
FIG=ROOT.parent/'report/source/figures'
FIG.mkdir(parents=True,exist_ok=True)
cached=np.load(ROOT/'experiments/trajectories.npz')
W,T,p,ts=[cached[k] for k in ['waypoints','times','coefficients','time']]
summary=json.loads((ROOT/'experiments/results.json').read_text())
J=summary['global']['cost']
module=ast.parse(Path(__file__).with_name('run_experiments.py').read_text())
functions=[node for node in module.body if isinstance(node,ast.FunctionDef)
           and node.name in {'basis','sample','track'}]
exec(compile(ast.Module(body=functions,type_ignores=[]),'<stored-reference plotting>','exec'))
D=[sample(p,T,ts,d) for d in range(5)]
DS=[sample(cached['stop_coefficients'],T,ts,d) for d in range(5)]
metrics=summary['tracking'];runs=[]
for original in metrics:
 measured,trace=track(original['scale'])
 assert abs(measured['rmse']-original['rmse'])<1e-10
 runs.append(trace)
C=['blue','red','green','black']
TC=['green','blue','red','black']
LS=[':', '-', '--', '-.']
plt.rcParams.update({'font.family':'serif','font.size':8,'axes.titlesize':8.5,'axes.labelsize':8,'legend.fontsize':7,'xtick.labelsize':7,'ytick.labelsize':7,'lines.linewidth':1.6,'axes.axisbelow':True,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.linewidth':.5,'grid.alpha':.18,'pdf.fonttype':42,'legend.frameon':True,'legend.edgecolor':'black','legend.facecolor':'white','legend.framealpha':1,'legend.fancybox':False})
plt.rcParams.update({'font.serif':['Times New Roman','Times','STIXGeneral','DejaVu Serif'],'mathtext.fontset':'stix','mathtext.fallback':'stix','axes.titleweight':'bold','axes.labelcolor':'black','text.color':'black'})
def save(name):
 for axis in plt.gcf().axes:
  legend=axis.get_legend()
  if legend is not None:
   legend.set_frame_on(True);legend.get_frame().set_edgecolor('black');legend.get_frame().set_linewidth(.8)
 for ext in ['pdf','png']:
  temporary=FIG/(name+'.rendering.'+ext)
  plt.savefig(temporary,dpi=220,bbox_inches='tight')
  temporary.replace(FIG/(name+'.'+ext))
 plt.close()
x=np.linspace(0,1,500)
fig,ax=plt.subplots(2,1,figsize=(3.45,3.65),sharex=True)
for c,lab,y,v in [(C[0],'Position endpoints only',x,np.ones_like(x)),(C[1],'Terminal velocity: quadratic',4*x-3*x*x,4-6*x),(C[2],'Terminal velocity: cubic',.25*x+4.5*x*x-3.75*x**3,.25+9*x-11.25*x*x)]:
 ax[0].plot(x,y,color=c,label=lab);ax[1].plot(x,v,color=c)
ax[0].set(ylabel='Position P(t)',title='(a) Optimal position profiles',ylim=(0,2.05));ax[0].legend(loc='upper left',fontsize=6.3)
ax[1].set(xlabel='Normalized time t',ylabel='Velocity dP/dt',title='(b) Terminal velocity equals −2');ax[1].scatter([1],[-2],color=C[2],zorder=4,s=18)
fig.tight_layout(pad=.6);save('icra_single')
fig,ax=plt.subplots(figsize=(3.45,2.10));n=np.arange(2,13);ax.plot(n,1+9/(n*n-1),'o-',color=C[2],markersize=3);ax.axhline(1,color='gray',ls='--',lw=1);ax.annotate('N=2: J=4',(2,4),xytext=(3,3.5),fontsize=7);ax.annotate('N=3: J=2.125',(3,2.125),xytext=(4.0,2.30),arrowprops={'arrowstyle':'-','color':'gray'},fontsize=7);ax.text(8,1.22,'Lower bound: 1',fontsize=7);ax.set(xlabel='Polynomial degree N',ylabel='Minimum velocity cost J');fig.tight_layout(pad=.6)
detail=ax.inset_axes([.53,.59,.43,.35])
detail.plot(n,9/(n*n-1),'o-',color=C[2],markersize=1.8,lw=.7)
detail.set(xscale='log',yscale='log',xlim=(1.8,13),ylim=(.05,4),xticks=[2,6,12],yticks=[.1,1])
detail.set_xticklabels(['2','6','12']);detail.set_yticklabels(['0.1','1'])
detail.minorticks_off();detail.tick_params(labelsize=5,length=2,pad=1)
detail.set_title(r'Cost gap $J_N^*-1$',fontsize=5.8,pad=2)
detail.grid(True,alpha=.15)
for spine in detail.spines.values():spine.set_visible(True);spine.set_color('black');spine.set_linewidth(.5)
save('icra_cost')
fig=plt.figure(figsize=(7.1,2.75));ax=fig.add_subplot(131,projection='3d');ax.set_proj_type('ortho')
ax.plot(*D[0].T,color=C[0],lw=1.5);ax.scatter(*W.T,color='white',edgecolors='black',linewidth=.7,s=20,depthshade=False)
for i,w in enumerate(W[:-1]):
 ax.text(*(w+np.array([.10,.10,.12])),'0/6' if i==0 else str(i),fontsize=6.2,color='black')
for j in np.searchsorted(ts,[1,3,5,7,9,11]):
 direction=D[1][j]/np.linalg.norm(D[1][j]);ax.quiver(*D[0][j],*direction,length=.55,arrow_length_ratio=.35,color=C[0],linewidth=.7)
ax.set(xlabel='x (m)',ylabel='y (m)',zlabel='',title='(a) Six-segment spatial path');ax.view_init(25,-58);ax.tick_params(pad=0);ax.set_box_aspect((1,1,.75));ax.text2D(.98,.78,'z (m)',transform=ax.transAxes,ha='right',fontsize=7)
for axis in [ax.xaxis,ax.yaxis,ax.zaxis]:
 axis.pane.fill=False;axis._axinfo['grid']['color']=(0,0,0,.12)
ax=fig.add_subplot(132);ax.plot(*DS[0][:,:2].T,color=C[1],ls='--',label='Stop at every waypoint');ax.plot(*D[0][:,:2].T,color=C[0],label='Global minimum snap');ax.scatter(*W[:,:2].T,s=14,color='black')
for i,w in enumerate(W[:-1]):ax.annotate('0/6' if i==0 else str(i),w[:2],xytext=(4,4),textcoords='offset points',fontsize=7)
ax.set(xlabel='x (m)',ylabel='y (m)',title='(b) Shared waypoints',ylim=(-2.1,4.8));ax.set_aspect('equal');ax.legend(loc='lower center',fontsize=5.8)
ax=fig.add_subplot(133)
for j,c,l in zip(range(3),C,['x','y','z']):ax.plot(ts,D[0][:,j],color=c,label=l)
ax.set(xlabel='Time (s)',ylabel='Position (m)',title='(c) Global reference coordinates',ylim=(-2.8,6.8));ax.legend(ncol=3,loc='upper right',fontsize=6)
for knot in np.cumsum(T)[:-1]:ax.axvline(knot,color='gray',lw=.55,ls=':',alpha=.5)
fig.tight_layout(pad=.6,w_pad=1.2);save('icra_path')
fig,axes=plt.subplots(2,2,figsize=(7.1,3.65),sharex=True)
for d,ax in enumerate(axes.flat,1):
 ax.plot(ts,np.linalg.norm(DS[d],axis=1),color=C[1],ls='--',label='Stop at every waypoint');ax.plot(ts,np.linalg.norm(D[d],axis=1),color=C[0],label='Global minimum snap')
 ax.set(ylabel=['Speed (m/s)',r'Acceleration (m/s$^2$)',r'Jerk (m/s$^3$)',r'Snap (m/s$^4$)'][d-1],title=['(a) Continuous speed through intermediate points','(b) Lower acceleration demand','(c) Reduced jerk peaks','(d) Reduced snap peaks'][d-1])
 for t in np.cumsum(T)[:-1]:ax.axvline(t,color='gray',lw=.5,alpha=.35)
for ax in axes[1]:ax.set_xlabel('Time (s)')
axes[0,0].set_ylim(0,4.65);axes[0,0].legend(loc='upper right',fontsize=6.5);fig.tight_layout(pad=.6);save('icra_derivatives')
fig,axes=plt.subplots(2,2,figsize=(7.1,4.25));ax=axes[0,0];ax.plot(*D[0][:,:2].T,'--',color='gray',label='Reference')
for i in [1,3]:ax.plot(*runs[i][1][:,:2].T,color=TC[i],ls=LS[i],label=f'T={metrics[i]["duration"]:g} s')
ax.scatter(*W[:,:2].T,color='black',s=10);ax.set(xlabel='x (m)',ylabel='y (m)',title='(a) Actual and desired paths');ax.set_aspect('equal');ax.legend(loc='center',fontsize=6.5)
ax=axes[0,1]
for c,ls,m,r in zip(TC,LS,metrics,runs):ax.plot(r[0]/m['duration'],r[2],color=c,ls=ls,label=f'{m["duration"]:g} s')
ax.set(xlabel='Normalized time t/T',ylabel='Position error (m)',title='(b) Error grows after time compression',ylim=(0,3.3));ax.legend(loc='upper right',ncol=2,fontsize=6.5)
ax=axes[1,0]
for c,ls,m,r in zip(TC,LS,metrics,runs):ax.plot(r[0]/m['duration'],np.linalg.norm(r[3][2],axis=1),color=c,ls=ls)
ax.axhline(4,color='black',ls='--',lw=1);ax.text(.02,4.25,'Acceleration limit: 4 m/s²',fontsize=7);ax.set(xlabel='Normalized time t/T',ylabel='Reference acceleration (m/s²)',title='(c) Compressed references exceed the limit')
ax=axes[1,1];dur=[m['duration'] for m in metrics];ax.plot(dur,[m['rmse'] for m in metrics],'o-',color=C[0],markersize=4,label='RMSE');ax.set(xlabel='Duration (s)',ylabel='Position RMSE (m)',title='(d) Saturation and error rise together');ar=ax.twinx();ar.plot(dur,[m['sat_percent'] for m in metrics],'s--',color=C[2],markersize=4,label='Saturation');ar.set_ylabel('Saturated samples (%)',color=C[2]);ar.grid(False);ax.legend([Line2D([0],[0],color=C[0],marker='o'),Line2D([0],[0],color=C[2],marker='s',ls='--')],['RMSE','Saturation'],fontsize=6.5,loc='upper right')
fig.tight_layout(pad=.7,w_pad=1.5,h_pad=1);save('icra_tracking')
fig,ax=plt.subplots(2,1,figsize=(3.45,3.35));alpha=np.linspace(.65,1.4,200)
for d,c,l in [(1,C[0],r'Speed: $\alpha^{-1}$'),(2,C[1],r'Acceleration: $\alpha^{-2}$'),(7,C[2],r'Snap cost: $\alpha^{-7}$')]:ax[0].plot(alpha,alpha**-d,color=c,label=l)
ax[0].set(xlabel='Time scale α',ylabel='Ratio to baseline',yscale='log',title='(a) Time-scaling laws');ax[0].legend(fontsize=6.5)
angles=np.array([170,179,-175,-160,-145]);un=np.rad2deg(np.unwrap(np.deg2rad(angles)));ax[1].plot(angles,'o--',color=C[1],label='Wrapped');ax[1].plot(un,'o-',color=C[0],label='Unwrapped');ax[1].set(xlabel='Waypoint index',ylabel='Yaw (deg)',title='(b) Continuous yaw across ±180°');ax[1].legend(fontsize=6.5);fig.tight_layout(pad=.6);save('icra_scaling')
