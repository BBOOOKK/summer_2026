from pathlib import Path
import math,json,csv
import numpy as np
from scipy.linalg import null_space
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]; FIG=ROOT.parent/'report/source/figures'; OUT=ROOT/'experiments'
FIG.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','Times','STIXGeneral','DejaVu Serif'],'mathtext.fontset':'stix','mathtext.fallback':'stix','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'black','text.color':'black','axes.titleweight':'bold','figure.facecolor':'white','axes.grid':True,'grid.alpha':.18,'savefig.bbox':'tight','pdf.fonttype':42,'legend.frameon':True,'legend.edgecolor':'black','legend.facecolor':'white','legend.framealpha':1,'legend.fancybox':False})
C=['blue','red','green','black']
def save(name):
 plt.savefig(FIG/(name+'.pdf')); plt.savefig(FIG/(name+'.png'),dpi=180); plt.close()
def basis(u,d=0,n=8):
 return np.array([math.factorial(j)/math.factorial(j-d)*u**(j-d) if j>=d else 0 for j in range(n)])
def solve(W,T,stop=False):
 k=len(T); n=8; Q=np.zeros((n*k,n*k)); rows=[]; rhs=[]
 for s,t in enumerate(T):
  for i in range(4,n):
   for j in range(4,n): Q[s*n+i,s*n+j]=math.factorial(i)/math.factorial(i-4)*math.factorial(j)/math.factorial(j-4)/(i+j-7)/t**7
  for u,w in [(0,W[s]),(1,W[s+1])]:
   r=np.zeros(n*k);r[s*n:(s+1)*n]=basis(u);rows.append(r);rhs.append(w)
 for s,u in [(0,0),(k-1,1)]:
  for d in range(1,4):
   r=np.zeros(n*k);r[s*n:(s+1)*n]=basis(u,d)/T[s]**d;rows.append(r);rhs.append(np.zeros(3))
 for s in range(k-1):
  for d in range(1,4):
   r=np.zeros(n*k);r[s*n:(s+1)*n]=basis(1,d)/T[s]**d;r[(s+1)*n:(s+2)*n]=-basis(0,d)/T[s+1]**d;rows.append(r);rhs.append(np.zeros(3))
   if stop:
    r=np.zeros(n*k);r[s*n:(s+1)*n]=basis(1,d)/T[s]**d;rows.append(r);rhs.append(np.zeros(3))
 A=np.array(rows);B=np.array(rhs);p=np.linalg.lstsq(A,B,rcond=None)[0];Z=null_space(A)
 if Z.shape[1]:p-=Z@np.linalg.solve(Z.T@Q@Z,Z.T@Q@p)
 return p.reshape(k,n,3),float(np.trace(p.T@Q@p)),float(np.max(abs(A@p-B)))
def sample(p,T,ts,d=0):
 bounds=np.r_[0,np.cumsum(T)];out=[]
 for t in ts:
  s=min(np.searchsorted(bounds[1:],t,side='right'),len(T)-1);u=np.clip((t-bounds[s])/T[s],0,1);out.append(basis(u,d)@p[s]/T[s]**d)
 return np.array(out)
W=np.array([[0,0,1],[3,0,1.5],[5,2,2],[3,4,2.4],[0,4,2],[-2,2,1.5],[0,0,1]],float);T=np.full(6,2.0)
p,J,res=solve(W,T);ps,Js,ress=solve(W,T,True);ts=np.linspace(0,12,2401)
D=[sample(p,T,ts,d) for d in range(5)];DS=[sample(ps,T,ts,d) for d in range(5)]
# Single segment solutions
x=np.linspace(0,1,500); fig,ax=plt.subplots(1,2,figsize=(9,3.25))
for c,label,y in [(C[0],'Endpoint positions only: t',x),(C[1],'Terminal velocity: degree 2',4*x-3*x*x),(C[2],'Terminal velocity: degree 3',.25*x+4.5*x*x-3.75*x**3)]:
 ax[0].plot(x,y,color=c,label=label,lw=2)
for c,y in [(C[0],np.ones_like(x)),(C[1],4-6*x),(C[2],.25+9*x-11.25*x*x)]:ax[1].plot(x,y,color=c,lw=2)
ax[0].set(xlabel='Normalized time',ylabel='Position',title='A  Optimal position');ax[1].set(xlabel='Normalized time',ylabel='Velocity',title='B  Endpoint derivative changes the solution');ax[0].legend(fontsize=8,loc='upper left');fig.tight_layout();save('single_segment')
fig,ax=plt.subplots(1,2,figsize=(9,3.1));a=np.linspace(-4,4,300);ax[0].plot(a,1+a*a/3,color=C[0],lw=2);ax[0].scatter([0],[1],color=C[1]);ax[0].set(xlabel='Quadratic coefficient p2',ylabel='Cost J',title='A  J = 1 + p2² / 3')
ns=np.arange(2,13)
for n,expected in [(2,np.array([4.,-3.])),(3,np.array([.25,4.5,-3.75]))]:
 q=np.fromfunction(lambda i,j:(i+1)*(j+1)/(i+j+1),(n,n));A=np.vstack([np.ones(n),np.arange(1,n+1)]); sol=np.linalg.solve(np.block([[2*q,A.T],[A,np.zeros((2,2))]]),np.r_[np.zeros(n),1,-2]);assert np.allclose(sol[:n],expected)
 assert np.isclose(sol[:n]@q@sol[:n],1+9/(n*n-1))
ax[1].plot(ns,1+9/(ns**2-1),'o-',color=C[2]);ax[1].axhline(1,color='gray',ls='--');ax[1].set(xlabel='Polynomial degree N',ylabel='Optimal cost J',title='B  With terminal velocity fixed');fig.tight_layout();save('cost')
fig=plt.figure(figsize=(9,3.8));ax=fig.add_subplot(121,projection='3d');ax.plot(*D[0].T,color=C[0],lw=2);ax.scatter(*W.T,color=C[1],s=35);ax.set(xlabel='x (m)',ylabel='y (m)',zlabel='z (m)',title='A  Smooth spatial trajectory');ax.view_init(27,-60)
ax=fig.add_subplot(122);ax.plot(*DS[0][:,:2].T,color=C[1],ls='--',label='Stop at each waypoint');ax.plot(*D[0][:,:2].T,color=C[0],label='Global minimum snap');ax.scatter(*W[:,:2].T,color='black',s=20)
for i,w in enumerate(W[:-1]):ax.annotate(str(i),w[:2],xytext=(4,5),textcoords='offset points')
ax.set(xlabel='x (m)',ylabel='y (m)',title='B  Top view');ax.axis('equal');ax.legend(fontsize=8);fig.tight_layout();save('trajectory')
fig,axes=plt.subplots(2,2,figsize=(9,5))
for d,ax in enumerate(axes.flat,1):
 ax.plot(ts,np.linalg.norm(DS[d],axis=1),color=C[1],lw=1.5,label='Stop at each waypoint');ax.plot(ts,np.linalg.norm(D[d],axis=1),color=C[0],lw=1.6,label='Global minimum snap');ax.set(xlabel='Time (s)',ylabel=['Speed (m/s)','Acceleration (m/s²)','Jerk (m/s³)','Snap (m/s⁴)'][d-1]);
 for t in np.cumsum(T)[:-1]:ax.axvline(t,color='gray',lw=.5,alpha=.35)
axes[0,0].legend(fontsize=8);fig.tight_layout();save('derivatives')
# Explicit reduced model: p_dot=v; v_dot=a; tau a_dot=sat(a_des+kp ep+kd ev)-a
# RK4, no disturbances. Its numerical results are independent of Unity.
def track(scale,dt=.005):
 TT=T*scale; t=np.arange(0,TT.sum()+dt/2,dt);ref=[sample(p,TT,t,d) for d in range(3)];state=np.r_[W[0],np.zeros(6)];hist=[];sat=0
 def fun(st,rr):
  cmd=rr[2]+6*(rr[0]-st[:3])+4*(rr[1]-st[3:6]);norm=np.linalg.norm(cmd);cmd=cmd*min(1,4/max(norm,1e-12));return np.r_[st[3:6],st[6:9],(cmd-st[6:9])/.12]
 for i in range(len(t)):
  hist.append(state.copy());rr=[r[i] for r in ref];cmd=rr[2]+6*(rr[0]-state[:3])+4*(rr[1]-state[3:6]);sat+=np.linalg.norm(cmd)>4
  if i+1<len(t):
   rr1=[r[i+1] for r in ref];rm=[(a+b)/2 for a,b in zip(rr,rr1)];k1=fun(state,rr);k2=fun(state+dt*k1/2,rm);k3=fun(state+dt*k2/2,rm);k4=fun(state+dt*k3,rr1);state+=dt*(k1+2*k2+2*k3+k4)/6
 hist=np.array(hist);err=np.linalg.norm(hist[:,:3]-ref[0],axis=1)
 return {'scale':scale,'duration':float(TT.sum()),'rmse':float(np.sqrt(np.mean(err**2))),'max_error':float(max(err)),'sat_percent':100*sat/len(t),'v_peak':float(max(np.linalg.norm(ref[1],axis=1))),'a_peak':float(max(np.linalg.norm(ref[2],axis=1))),'cost':J/scale**7},(t,hist,err,ref)
metrics=[];runs=[]
for scale in [1.3,1,.85,.7]:
 m,r=track(scale);metrics.append(m);runs.append(r)
fig,ax=plt.subplots(1,2,figsize=(9,3.4))
for c,m,r in zip(C,metrics,runs):ax[0].plot(r[0]/m['duration'],r[2],color=c,label=f"α={m['scale']:g}, T={m['duration']:g} s")
ax[0].set(xlabel='Normalized progress',ylabel='Position error (m)',title='A  Tracking error');ax[0].legend(fontsize=8);ax[1].plot([m['duration'] for m in metrics],[m['rmse'] for m in metrics],'o-',color=C[0]);ax[1].set(xlabel='Duration (s)',ylabel='Position RMSE (m)',title='B  Speed–accuracy trade-off');fig.tight_layout();save('tracking')
fig,ax=plt.subplots(1,2,figsize=(9,3.1));alpha=np.linspace(.65,1.4,200)
for d,c,l in [(1,C[0],'Peak speed'),(2,C[1],'Peak acceleration'),(7,C[2],'Snap cost')]:ax[0].plot(alpha,alpha**-d,color=c,label=l)
ax[0].set(xlabel='Time scale α',ylabel='Ratio to baseline',yscale='log',title='A  Time compression amplifies derivatives');ax[0].legend(fontsize=8)
angles=np.array([170,179,-175,-160,-145]);un=np.rad2deg(np.unwrap(np.deg2rad(angles)));ax[1].plot(angles,'o--',color=C[1],label='Wrapped yaw');ax[1].plot(un,'o-',color=C[0],label='Unwrapped yaw');ax[1].set(xlabel='Waypoint index',ylabel='Yaw (deg)',title='B  Continuous heading across ±180°');ax[1].legend(fontsize=8);fig.tight_layout();save('scaling_yaw')
# diagnostic exact derivatives at joins
jump={str(d):max(float(np.max(abs(basis(1,d)@p[s]/T[s]**d-basis(0,d)@p[s+1]/T[s+1]**d))) for s in range(5)) for d in range(1,7)}
summary={'global':{'cost':J,'constraint_residual':res,'peaks':[float(max(np.linalg.norm(a,axis=1))) for a in D[1:]]},'stop':{'cost':Js,'constraint_residual':ress,'peaks':[float(max(np.linalg.norm(a,axis=1))) for a in DS[1:]]},'join_residuals':jump,'tracking':metrics,'dt_refinement':{'dt_0.0025':track(1,.0025)[0]}}
(OUT/'results.json').write_text(json.dumps(summary,indent=2));np.savez(OUT/'trajectories.npz',waypoints=W,times=T,coefficients=p,stop_coefficients=ps,time=ts,position=D[0],velocity=D[1],acceleration=D[2])
with (OUT/'time_scaling.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=metrics[0].keys());w.writeheader();w.writerows(metrics)
print(json.dumps(summary,indent=2))

assert res < 1e-8 and ress < 1e-8 and J < Js
assert max(jump.values()) < 1e-7
