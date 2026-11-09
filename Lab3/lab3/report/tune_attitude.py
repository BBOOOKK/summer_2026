"""Matched attitude-gain study and integrated tracking figure."""
import json, os
import numpy as np
import run_experiments as e
cases={'lower_attitude_gain':{'kR':50},'higher_rate_gain':{'kOmega':40}}
metrics={}
for name,c in cases.items():
    dest=e.OUT/(name+'.json')
    if not dest.exists() or os.environ.get('LAB3_RERUN_TUNING'):
        result=e.run(name,c)
        dest.write_text(json.dumps(result['metrics'],indent=2))
    metrics[name]=json.loads(dest.read_text())
metrics['nominal']=json.loads((e.OUT/'metrics.json').read_text())['nominal']
for name,c in {'nominal':{},**cases}.items():
    kr=c.get('kR',100);ko=c.get('kOmega',20)
    metrics[name]['predicted_yaw_deg']=float(np.rad2deg(np.arcsin(ko*.5/kr)))
    metrics[name]['local_poles']=np.roots([1,ko,kr]).tolist()
(e.OUT/'attitude_conditions.json').write_text(json.dumps(cases,indent=2))
(e.OUT/'attitude_metrics.json').write_text(json.dumps(metrics,indent=2))
def load(name):return np.loadtxt(e.OUT/(name+'.csv'),delimiter=',',skiprows=1)
r=load('nominal');low=load('lowdamping');fig,axs=e.plt.subplots(2,2,figsize=(10,4.8))
for i in range(3):axs[0,0].plot(r[:,0],r[:,i+1]-r[:,i+14],label=['x','y','z'][i],c=e.C[i])
e.label(axs[0,0],'(a) Position error',y='Error (m)');axs[0,0].legend(ncol=3,fontsize=10)
for z,col,lab in [(r,e.C[0],'kv = 4'),(low,e.C[1],'kv = 2')]:axs[0,1].plot(z[:,0],z[:,17],c=col,label=lab)
e.label(axs[0,1],'(b) Velocity damping',y='Position error (m)');axs[0,1].legend(fontsize=10)
axs[1,0].plot(r[:,0],r[:,22],c=e.C[2]);e.label(axs[1,0],'(c) Nominal tilt',y='Tilt (deg)')
for name,col,lab in [('nominal',e.C[0],'kR = 100, kΩ = 20'),('lower_attitude_gain',e.C[1],'kR = 50, kΩ = 20'),('higher_rate_gain',e.C[3],'kR = 100, kΩ = 40')]:
    z=load(name);axs[1,1].plot(z[:,0],z[:,23],c=col,label=lab)
e.label(axs[1,1],'(d) Attitude-gain comparison',y='Yaw error (deg)');axs[1,1].legend(fontsize=8,loc='lower right');fig.tight_layout();e.save('tracking')
rows=[]
for name,label,kr,ko in [('nominal','Nominal',100,20),('lower_attitude_gain','Lower attitude gain',50,20),('higher_rate_gain','Higher rate damping',100,40)]:
    m=metrics[name]
    rows.append(f"{label} & {kr} & {ko} & {m['predicted_yaw_deg']:.2f} & {m['yaw_rmse_steady_deg']:.2f} & {m['rmse_steady']:.4f}"+r'\\')
(e.OUT/'attitude_rows.tex').write_text(r'\begin{tabularx}{\columnwidth}{@{}Yrrrrr@{}}\toprule'+'\n'+r'\tablehead Condition & $k_R$ & $k_\Omega$ & \shortstack{Pred. lag\\($^\circ$)} & \shortstack{Yaw RMSE\\($^\circ$)} & \shortstack{Pos. RMSE\\(m)}\\\midrule'+'\n'+'\n'.join(rows)+'\n'+r'\bottomrule\end{tabularx}'+'\n')
print(json.dumps(metrics,indent=2))
