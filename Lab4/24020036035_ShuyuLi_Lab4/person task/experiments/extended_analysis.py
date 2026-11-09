"""Matched lag/saturation ablations and response-time sensitivity for LAB4."""
from pathlib import Path
import json,math,csv,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch, Rectangle
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments';FIG=ROOT.parent/'report/source/figures'
FIG.mkdir(parents=True,exist_ok=True)
z=np.load(OUT/'trajectories.npz');p=z['coefficients'];W=z['waypoints'];baseT=z['times']
BLUE='blue';RED='red';GREEN='green';BLACK='black';GRAY='gray'
plt.rcParams.update({'font.family':'serif','font.size':8,'axes.titlesize':8.5,'axes.labelsize':8,'legend.fontsize':7,'xtick.labelsize':7,'ytick.labelsize':7,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'grid.linewidth':.5,'axes.axisbelow':True,'pdf.fonttype':42,'lines.linewidth':1.6})
plt.rcParams.update({'font.serif':['Times New Roman','Times','STIXGeneral','DejaVu Serif'],'mathtext.fontset':'stix','mathtext.fallback':'stix','axes.titleweight':'bold','axes.labelcolor':'black','text.color':'black'})
def reference(ts,T,d):
 bounds=np.r_[0,np.cumsum(T)];seg=np.minimum(np.searchsorted(bounds[1:],ts,side='right'),len(T)-1);u=np.clip((ts-bounds[seg])/T[seg],0,1)
 B=np.array([math.factorial(j)/math.factorial(j-d)*u**(j-d) if j>=d else np.zeros_like(u) for j in range(8)]).T
 return np.einsum('ij,ijk->ik',B,p[seg])/T[seg,None]**d

def simulate(duration,tau=.12,limit=4,dt=.005):
 T=baseT*(duration/baseT.sum());ts=np.linspace(0,duration,round(duration/dt)+1);dt=ts[1]-ts[0];ref=np.stack([reference(ts,T,d) for d in range(3)],axis=1)
 state=np.r_[W[0],np.zeros(6 if tau>0 else 3)];hist=np.empty((len(ts),len(state)));saturated=0
 def f(st,r):
  cmd=r[2]+6*(r[0]-st[:3])+4*(r[1]-st[3:6]);n=np.linalg.norm(cmd)
  if limit is not None:cmd*=min(1,limit/max(n,1e-12))
  if tau==0:return np.r_[st[3:6],cmd]
  return np.r_[st[3:6],st[6:9],(cmd-st[6:9])/tau]
 for i in range(len(ts)):
  hist[i]=state;cmd=ref[i,2]+6*(ref[i,0]-state[:3])+4*(ref[i,1]-state[3:6]);saturated+=limit is not None and np.linalg.norm(cmd)>limit
  if i+1<len(ts):
   r0=ref[i];r1=ref[i+1];rm=(r0+r1)/2;k1=f(state,r0);k2=f(state+dt*k1/2,rm);k3=f(state+dt*k2/2,rm);k4=f(state+dt*k3,r1);state+=dt*(k1+2*k2+2*k3+k4)/6
 err=np.linalg.norm(hist[:,:3]-ref[:,0,:],axis=1)
 return {'duration':duration,'tau':tau,'limit':limit,'rmse':float(np.sqrt(np.mean(err*err))),'max_error':float(max(err)),'end_error':float(err[-1]),'sat_percent':100*saturated/len(ts)},(ts,hist,err)
configs=[('Ideal response',0,None,GRAY),('Lag only',.12,None,BLUE),('Saturation only',0,4,RED),('Lag + saturation',.12,4,BLACK)]
rows=[];traces={}
durations=[8.4,10.2,12.,13.8,15.6];taus=[.04,.08,.12,.18,.24]
if '--plots-only' in sys.argv:
 out=json.loads((OUT/'extended_results.json').read_text())
 rows,sweep=out['ablation'],out['sensitivity']
 stored=np.load(OUT/'ablation_traces.npz')
 for duration in [12.,10.2,8.4]:
  for name,_,_,_ in configs:
   error=stored[f'{duration:g}_{name.replace(" ","_")}_error']
   traces[(duration,name)]=(np.linspace(0,duration,len(error)),None,error)
else:
 for duration in [12.,10.2,8.4]:
  for name,tau,limit,c in configs:
   m,r=simulate(duration,tau,limit);m['configuration']=name;rows.append(m);traces[(duration,name)]=r
 sweep=[]
 for tau in taus:
  for duration in durations:
   m,_=simulate(duration,tau,4);sweep.append(m)
 refined,_=simulate(8.4,.12,4,.0025)
 old=json.loads((OUT/'results.json').read_text())
 for m in old['tracking']:
  if m['duration'] in [12.,10.2,8.4]:
   new=next(r for r in rows if r['duration']==m['duration'] and r['configuration']=='Lag + saturation');assert abs(new['rmse']-m['rmse'])<1e-9
 p_global=p.copy();p=z['stop_coefficients'];stop_tracking,_=simulate(12.);p=p_global
 out={'stop_tracking_12s':stop_tracking,'ablation':rows,'sensitivity':sweep,'refined_aggressive':refined}
 (OUT/'extended_results.json').write_text(json.dumps(out,indent=2))
 for name,data in [('ablation',rows),('response_sensitivity',sweep)]:
  with (OUT/(name+'.csv')).open('w') as f:
   w=csv.DictWriter(f,fieldnames=data[0].keys());w.writeheader();w.writerows(data)
 np.savez(OUT/'ablation_traces.npz',**{f'{d:g}_{name.replace(" ","_")}_error':r[2] for (d,name),r in traces.items()})
def save(n):
 for axis in plt.gcf().axes:
  legend=axis.get_legend()
  if legend is not None:
   legend.set_frame_on(True);legend.get_frame().set_edgecolor('black')
   legend.get_frame().set_facecolor('white');legend.get_frame().set_alpha(1)
   legend.get_frame().set_linewidth(.8);legend.get_frame().set_boxstyle('square',pad=0)
 for ext in ['pdf','png']:
  temporary=FIG/(n+'.rendering.'+ext)
  plt.savefig(temporary,dpi=240,bbox_inches='tight')
  temporary.replace(FIG/(n+'.'+ext))
 plt.close()
fig,ax=plt.subplots(1,2,figsize=(7.1,2.75))
xx=np.arange(3);width=.19
for j,(name,tau,limit,c) in enumerate(configs):
 vals=[next(r['rmse'] for r in rows if r['duration']==d and r['configuration']==name) for d in [12.,10.2,8.4]]
 ax[0].bar(xx+(j-1.5)*width,vals,width,color=c,label=name,edgecolor='white',linewidth=.4)
ax[0].set(xticks=xx,xticklabels=['12.0','10.2','8.4'],xlabel='Duration (s)',ylabel='Position RMSE (m)',yscale='log',title='(a) Matched ablation across three durations');ax[0].set_ylim(1e-7,10);ax[0].legend(loc='upper left',fontsize=6.3,ncol=2,frameon=True)
for (name,tau,limit,c),ls in zip(configs,[':', '--','-.','-']):
 t,h,e=traces[(8.4,name)];ax[1].plot(t,e,color=c,ls=ls,label=name)
ax[1].set(xlabel='Time (s)',ylabel='Position error (m)',title='(b) Most aggressive reference: T = 8.4 s',ylim=(0,3.3));ax[1].legend(loc='upper right',fontsize=6.3,frameon=True)
fig.tight_layout(pad=.7,w_pad=1.4);save('icra_ablation')
M=np.array([[next(r['rmse'] for r in sweep if r['duration']==d and r['tau']==t) for d in durations] for t in taus])
fig,ax=plt.subplots(figsize=(3.45,2.95));cmap=LinearSegmentedColormap.from_list('paper',['white','blue'])
im=ax.imshow(M,cmap=cmap,aspect='auto',vmin=0,vmax=M.max())
for i in range(len(taus)):
 for j in range(len(durations)):
  item=next(r for r in sweep if r['duration']==durations[j] and r['tau']==taus[i])
  if item['max_error']<.10:
   ax.add_patch(Rectangle((j-.48,i-.48),.96,.96,facecolor='none',edgecolor='black',linewidth=1.1))
  ax.text(j,i,f'{M[i,j]:.3f}',ha='center',va='center',fontsize=7,color='white' if M[i,j]>.55*M.max() else 'black')
ax.set(xticks=range(5),xticklabels=[f'{v:g}' for v in durations],yticks=range(5),yticklabels=[f'{v:.2f}' for v in taus],xlabel='Duration (s)',ylabel='Response lag τ (s)');ax.grid(False);cb=fig.colorbar(im,ax=ax,pad=.03);cb.set_label('Position RMSE (m)')
fig.legend(handles=[Patch(facecolor='white',edgecolor='black',linewidth=1.1,label='Maximum error < 0.10 m')],loc='upper center',bbox_to_anchor=(.49,.995),frameon=True,edgecolor='black',facecolor='white',framealpha=1,fancybox=False,fontsize=6.6,borderpad=.35,handlelength=1.0)
fig.tight_layout(pad=.6,rect=(0,0,1,.91));save('icra_sensitivity')
print(json.dumps(out,indent=2))
