"""Optimize a rotor-driven rigid-body reference trajectory for the Unity course."""
import sys,json,argparse
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/optimal_control'))
import casadi as ca

ap=argparse.ArgumentParser();ap.add_argument('--race-steps',type=int,default=100)
ap.add_argument('--entry-steps',type=int,default=45);ap.add_argument('--exit-steps',type=int,default=20)
ap.add_argument('--initial');ap.add_argument('--corridor',action='store_true');ap.add_argument('--time-opt',action='store_true');ap.add_argument('--all-time-opt',action='store_true');ap.add_argument('--schedule');ap.add_argument('--label',default='');ap.add_argument('--rotor-limit',type=float,default=1000);ap.add_argument('--safe-stop',action='store_true');ap.add_argument('--start-z',type=float,default=2.67);args=ap.parse_args()
force_scale=.001*args.rotor_limit**2
dt=.02;raceN=args.race_steps;entryN=args.entry_steps;exitN=args.exit_steps
gates=json.loads((ROOT/'results/gates.json').read_text());gp=np.array([g['position'] for g in gates])
schedule=ROOT/'results/reference_subsecond/relaxation_time_60'
if args.schedule:schedule=Path(args.schedule)
if (schedule/'model_status.json').exists():
    st=json.loads((schedule/'model_status.json').read_text());ss=np.genfromtxt(schedule/'reference.csv',delimiter=',',names=True)
    gt=ss['t'][st['gate_indices']];fraction=(gt-gt[0])/(gt[-1]-gt[0])
else:
    st=json.loads((schedule/'status.json').read_text());ss=np.genfromtxt(schedule/'states.csv',delimiter=',',names=True)
    fraction=ss['t'][st['gate_indices']]/ss['t'][-1]
gateidx=entryN+np.rint(fraction*raceN).astype(int)
N=entryN+raceN+exitN;ts=np.arange(N+1)*dt
start=np.array([.4,8,args.start_z]);end=gp[-1]+(2 if args.safe_stop else 3)*np.array(gates[-1]['normal'])
knots=np.r_[0,gateidx,N];centres=np.vstack([start,gp,end])
curve=CubicSpline(knots*dt,centres,axis=0,bc_type=((1,np.zeros(3)),(1,np.zeros(3))))
pg=curve(ts);vg=curve(ts,1);ag=curve(ts,2);ag[:,2]+=9.81
rg=[];prev=Rotation.from_euler('z',-2.903331).as_matrix()
for i in range(N+1):
    b=ag[i]/max(np.linalg.norm(ag[i]),1e-8)
    if b@prev[:,2]<0:b=-b
    axis=np.cross(prev[:,2],b);angle=np.arctan2(np.linalg.norm(axis),prev[:,2]@b)
    if np.linalg.norm(axis)>1e-7:prev=Rotation.from_rotvec(axis/np.linalg.norm(axis)*angle).as_matrix()@prev
    rg.append(prev.copy())
rg=np.array(rg);qg=Rotation.from_matrix(rg).as_quat();qg[0]=Rotation.from_euler('z',-2.903331).as_quat()
wg=np.zeros((N+1,3))
wg[1:]=Rotation.from_matrix(rg[1:]@rg[:-1].transpose(0,2,1)).as_rotvec()/dt
wg*=np.minimum(1,6.8/np.maximum(np.linalg.norm(wg,axis=1),1e-8))[:,None]
arm=.3/np.sqrt(2);M=np.array([[1,1,1,1],[arm,arm,-arm,-arm],[-arm,arm,arm,-arm],[.01,-.01,.01,-.01]])
ug=np.zeros((N,4))
for i in range(N):
    force=ag[i]@rg[i,:,2]
    torque=np.diag([.1,.2,.1])@rg[i].T@((wg[i+1]-wg[i])/dt)
    ug[i]=np.linalg.solve(M,np.r_[force,torque])/force_scale
ug=np.clip(ug,-.95,.95)
if args.initial:
    prevdir=Path(args.initial);old=np.genfromtxt(prevdir/'reference.csv',delimiter=',',names=True)
    oldcfg=json.loads((prevdir/'model_status.json').read_text());oldg=old['t'][oldcfg['gate_indices']]
    newg=gateidx*dt
    src=np.interp(ts,np.r_[0,newg,ts[-1]],np.r_[0,oldg,old['t'][-1]])
    pg=np.column_stack([np.interp(src,old['t'],old[k]) for k in ['x','y','z']])
    vg=np.column_stack([np.interp(src,old['t'],old[k]) for k in ['vx','vy','vz']])
    qg=np.column_stack([np.interp(src,old['t'],old[k]) for k in ['qx','qy','qz','qw']]);qg/=np.linalg.norm(qg,axis=1)[:,None]
    wg=np.column_stack([np.interp(src,old['t'],old[k]) for k in ['wx','wy','wz']])
    ug=np.column_stack([np.interp(src[:-1],old['t'],old[k]) for k in ['u0','u1','u2','u3']])/force_scale

def rot(q):
    x,y,z,w=q[0],q[1],q[2],q[3]
    return ca.vertcat(ca.horzcat(1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)),ca.horzcat(2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)),ca.horzcat(2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)))
def qmul(a,b):return ca.vertcat(a[3]*b[:3]+b[3]*a[:3]+ca.cross(a[:3],b[:3]),a[3]*b[3]-ca.dot(a[:3],b[:3]))
op=ca.Opti();p=op.variable(3,N+1);v=op.variable(3,N+1);q=op.variable(4,N+1);w=op.variable(3,N+1);u=op.variable(4,N)
if args.time_opt:
    race_h=op.variable(1,raceN);op.subject_to(op.bounded(.003,race_h,.05));op.set_initial(race_h,dt)
    if args.all_time_opt:
        entry_h=op.variable(1,entryN);op.subject_to(op.bounded(.003,entry_h,.05));op.set_initial(entry_h,dt)
    else:entry_h=ca.DM.ones(1,entryN)*dt
    h=ca.horzcat(entry_h,race_h,ca.DM.ones(1,exitN)*dt)
else:h=ca.DM.ones(1,N)*dt
op.subject_to(p[:,0]==start);op.subject_to(v[:,0]==0);op.subject_to(w[:,0]==0)
op.subject_to(q[:,0]==Rotation.from_euler('z',-2.903331).as_quat())
op.subject_to(op.bounded(-1,u,1));op.subject_to(op.bounded(.65,p[2,:],5.1))
op.subject_to(v[:,-1]==0);op.subject_to(p[:,-1]==end)
if args.safe_stop:
    op.subject_to(w[:,-1]==0);op.subject_to(q[0:2,-1]==0)
    op.subject_to(op.bounded(-42,p[0,gateidx[-1]:],-36))
    op.subject_to(op.bounded(12,p[1,gateidx[-1]:],16.5))
    op.subject_to(op.bounded(1,p[2,gateidx[-1]:],4.5))
if args.corridor:
    op.subject_to(op.bounded(-.8,p[0,:entryN+1],1.5))
    op.subject_to(op.bounded(2.8,p[1,:entryN+1],8.3))
    for j in range(len(gates)-1):
        for i in range(int(gateidx[j]),int(gateidx[j+1])):
            fraction=(i-gateidx[j])/(gateidx[j+1]-gateidx[j])
            centre=(1-fraction)*gp[j]+fraction*gp[j+1]
            op.subject_to(ca.sumsqr(p[:2,i]-centre[:2])<=2.0**2)
cost=0
for i in range(N):
    R=rot(q[:,i]);wr=ca.DM(M)@(force_scale*u[:,i])
    step=h[i]
    wn=w[:,i]+step*R@ca.DM(np.diag([10,5,10]))@wr[1:]
    vn=v[:,i]+step*(wr[0]*R[:,2]+ca.DM([0,0,-9.81]))
    angle=ca.sqrt(ca.sumsqr(wn)+1e-12)*step
    dq=ca.vertcat(ca.sin(angle/2)/(angle/step)*wn,ca.cos(angle/2))
    op.subject_to(w[:,i+1]==wn);op.subject_to(q[:,i+1]==qmul(dq,q[:,i]))
    op.subject_to(v[:,i+1]==vn);op.subject_to(p[:,i+1]==p[:,i]+step*vn)
    op.subject_to(ca.sumsqr(w[:,i+1])<=6.85**2)
    # Broad path corridor; actual meshes/collisions are checked in Unity.
    cost+=.05*ca.sumsqr(p[:,i]-curve(ts[i]))+.001*ca.sumsqr(u[:,i])
    if i:cost+=.003*ca.sumsqr(u[:,i]-u[:,i-1])
for j,i in enumerate(gateidx):
    d=p[:,i]-gp[j]
    op.subject_to(ca.dot(d,ca.DM(gates[j]['normal']))==0)
    op.subject_to(op.bounded(-.15,ca.dot(d,ca.DM(gates[j]['horizontal'])),.15))
    op.subject_to(op.bounded(-.15,d[2],.15))
    op.subject_to(ca.dot(v[:,i],ca.DM(gates[j]['normal']))>=1)
    op.subject_to(ca.dot(p[:,i-1]-gp[j],ca.DM(gates[j]['normal']))<=-.12)
    op.subject_to(ca.dot(p[:,i+1]-gp[j],ca.DM(gates[j]['normal']))>=.12)
op.minimize(cost+(1000*ca.sum2(race_h)+ (1000*ca.sum2(entry_h) if args.all_time_opt else 0) if args.time_opt else 0));op.set_initial(p,pg.T);op.set_initial(v,vg.T);op.set_initial(q,qg.T);op.set_initial(w,wg.T);op.set_initial(u,ug.T)
op.solver('ipopt',{'expand':True},{'max_iter':2500,'tol':1e-6,'print_level':0,'max_cpu_time':90})
out=ROOT/'results/reference_subsecond'/(f'rigid_{entryN}_{raceN}_{exitN}'+('_corridor' if args.corridor else '')+('_time' if args.time_opt else '')+('_'+args.label if args.label else ''));out.mkdir(exist_ok=True)
try:sol=op.solve();ok=True
except RuntimeError:sol=op.debug;ok=False
P=sol.value(p).T;V=sol.value(v).T;Q=sol.value(q).T;W=sol.value(w).T;U=sol.value(u).T*force_scale
if args.time_opt:ts=np.r_[0,np.cumsum(sol.value(h))]
RR=Rotation.from_quat(Q).as_matrix();F=U@M.T
acc=np.vstack([F[:,0,None]*RR[:-1,:,2]+[0,0,-9.81],[0,0,0]])
data=np.column_stack([ts,P,V,acc,Q,W,np.vstack([U,U[-1]])])
np.savetxt(out/'reference.csv',data,delimiter=',',header='t,x,y,z,vx,vy,vz,ax,ay,az,qx,qy,qz,qw,wx,wy,wz,u0,u1,u2,u3',comments='')
status=dict(model_success=ok,uniform_20ms=not args.time_opt,rotor_limit_rad_s=args.rotor_limit,race_s=float(ts[gateidx[-1]]-ts[gateidx[0]]),entry_s=float(ts[entryN]),exit_s=float(ts[-1]-ts[gateidx[-1]]),gate_indices=gateidx.tolist(),arguments=vars(args))
(out/'model_status.json').write_text(json.dumps(status,indent=2,default=str));print(json.dumps({k:status[k] for k in ['model_success','race_s','entry_s']}))
