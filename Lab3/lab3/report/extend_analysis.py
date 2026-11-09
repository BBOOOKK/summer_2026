from pathlib import Path
import json, os
import numpy as np
import run_experiments as e
p=e.ROOT
if not (e.OUT/'combined.csv').exists() or os.environ.get('LAB3_RERUN_EXTENDED'):
    z=e.run('combined',{'smooth':True,'drag':1,'comp':1})
    (e.OUT/'combined_metrics.json').write_text(json.dumps(z['metrics'],indent=2))
def load(k):return np.loadtxt(e.OUT/(k+'.csv'),delimiter=',',skiprows=1)
rows={k:load(k) for k in ['nominal','drag','compensated','combined','pulse']}
summary={};components={}
for k,z in rows.items():
 t=z[:,0];err=z[:,1:4]-z[:,14:17];th=np.arctan2(z[:,14],z[:,15]);nr=np.column_stack([np.sin(th),np.cos(th),np.zeros(len(t))]);nt=np.column_stack([np.cos(th),-np.sin(th),np.zeros(len(t))]);comp=np.column_stack([(err*nr).sum(1),(err*nt).sum(1),err[:,2]]);components[k]=comp
 mask=t>=10
 rho=np.linalg.norm(z[:,1:3],axis=1)-5
 assert np.max(abs(np.sum(comp**2,axis=1)-z[:,17]**2))<1e-10
 summary[k]={'component_rms_m':np.sqrt(np.mean(comp[mask]**2,axis=0)).tolist(),'component_mean_m':comp[mask].mean(0).tolist(),'radius_rms_m':float(np.sqrt(np.mean(rho[mask]**2))),'startup_max_m':float(z[t<=4,17].max()),'steady_rmse_m':float(np.sqrt(np.mean(z[mask,17]**2))),'peak_rotor_rad_s':float(abs(z[:,18:22]).max()),'peak_tilt_deg':float(z[:,22].max()),'mean_tilt_deg':float(z[mask,22].mean())}
base=rows['combined'];pulse=rows['pulse'];t=base[:,0];delta=np.linalg.norm(pulse[:,1:4]-base[:,1:4],axis=1)
ix=np.flatnonzero((t>=13)&(delta>.01));settle=t[ix[-1]+1] if ix[-1]+1<len(t) else np.nan
summary['recovery']={'peak_incremental_position_m':float(delta.max()),'settling_time_absolute_s':float(settle),'settling_time_after_removal_s':float(settle-13),'tolerance_m':.01}
(p/'results/extended_metrics.json').write_text(json.dumps(summary,indent=2))
# Moving-frame errors, steady-state interval enlarged.
plt=e.plt;C=e.C
fig,axs=plt.subplots(1,2,figsize=(10,3.5))
conditions=[('nominal',C[2],'No drag'),('drag',C[1],'Uncompensated'),('compensated',C[0],'Compensated')]
for k,col,lab in conditions:
 mean=np.array(summary[k]['component_mean_m'])*1000
 axs[0].annotate('',xy=(mean[1],mean[0]),xytext=(0,0),arrowprops=dict(arrowstyle='-|>',lw=2,color=col,mutation_scale=14))
 axs[0].scatter(mean[1],mean[0],c=col,s=35,label=lab,zorder=3)
axs[0].axhline(0,c='#9AA8B2',lw=.7);axs[0].axvline(0,c='#9AA8B2',lw=.7)
e.label(axs[0],'(a) Mean horizontal offset','Tangential error (mm)','Radial error (mm)')
axs[0].set_xlim(-115,45);axs[0].set_ylim(-70,45);axs[0].legend(fontsize=9,loc='lower right')
shares=np.array([np.array(summary[k]['component_rms_m'])**2/summary[k]['steady_rmse_m']**2*100 for k,_,_ in conditions]);bottom=np.zeros(3)
for j,(lab,col) in enumerate([('Radial',C[0]),('Tangential',C[1]),('Vertical',C[2])]):
 axs[1].bar(np.arange(3),shares[:,j],bottom=bottom,color=col,label=lab,width=.56)
 for i in range(3):
  if shares[i,j]>5:axs[1].text(i,bottom[i]+shares[i,j]/2,f'{shares[i,j]:.1f}%',ha='center',va='center',fontsize=10,color='white',weight='bold')
 bottom+=shares[:,j]
axs[1].set_xticks(np.arange(3),['No drag','Uncomp.','Comp.']);axs[1].set_ylim(0,125);axs[1].set_yticks([0,25,50,75,100]);axs[1].legend(fontsize=8,ncol=3,loc='upper center',columnspacing=.8,handlelength=1)
e.label(axs[1],'(b) Mean-square error composition','', 'Contribution (%)');fig.tight_layout();e.save('error_components')
fig,axs=plt.subplots(1,2,figsize=(10,3.2))
for k,col,lab in [('drag',C[1],'Direct, no compensation'),('compensated',C[3],'Direct, compensation'),('combined',C[0],'Smooth, compensation')]:
 z=rows[k];axs[0].plot(z[:,0],z[:,17],c=col,label=lab);axs[1].plot(z[:,0],np.max(abs(z[:,18:22]),axis=1),c=col,label=lab)
e.label(axs[0],'(a) Startup tracking',y='Position error (m)');e.label(axs[1],'(b) Peak instantaneous rotor demand',y='Max. absolute rotor speed (rad/s)')
for ax in axs:ax.set_xlim(0,6)
axs[0].legend(fontsize=9);fig.tight_layout();e.save('combined_design')
# Existing robustness figure gains the matched, unperturbed baseline.
m=json.loads((e.OUT/'metrics.json').read_text());fig,axs=plt.subplots(1,2,figsize=(10,3.1));keys=['drag','undercomp','compensated','overcomp'];v=[m[k]['rmse_steady'] for k in keys]
axs[0].plot([0,.5,1,1.5],v,'o-',c=C[0]);e.label(axs[0],'(a) Drag-model sensitivity','Estimated / true drag coefficient','Steady RMSE (m)')
axs[1].plot(t,pulse[:,17],c=C[0],label='With force pulse');axs[1].plot(t,base[:,17],'--',c=C[2],label='Matched baseline');axs[1].axvspan(12,13,color=C[1],alpha=.22);e.label(axs[1],'(b) Disturbance response',y='Position error (m)');axs[1].legend(fontsize=9);axs[1].set_xlim(8,22);fig.tight_layout();e.save('robustness')
lines=[]
for pre,k in [('Free','nominal'),('Uncomp','drag'),('Exact','compensated'),('Joint','combined')]:
 for suf,val in zip(['Rad','Tan','Vert'],summary[k]['component_rms_m']):lines.append('\\newcommand{\\'+pre+suf+'}{'+f'{val:.4f}'+'}')
for key,val in [('JointStart',summary['combined']['startup_max_m']),('JointSteady',summary['combined']['steady_rmse_m']),('JointRotor',summary['combined']['peak_rotor_rad_s']),('JointTilt',summary['combined']['peak_tilt_deg']),('DeltaPeak',summary['recovery']['peak_incremental_position_m']),('RecoveryTime',summary['recovery']['settling_time_after_removal_s']),('JointGain',100*(1-summary['combined']['startup_max_m']/summary['drag']['startup_max_m']))]:lines.append('\\newcommand{\\'+key+'}{'+f'{val:.4f}'+'}')
(p/'results/extended_numbers.tex').write_text('\n'.join(lines))
print(json.dumps(summary,indent=2))
