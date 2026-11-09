from pathlib import Path
import json, os
import numpy as np
if not (os.environ.get('LAB3_OVERVIEW_ONLY') or os.environ.get('LAB3_REPLOT')):
    from scipy.integrate import solve_ivp
    from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
ROOT=Path(__file__).resolve().parent
FIG=ROOT/'figures'; OUT=ROOT/'results'
plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','Nimbus Roman','Liberation Serif'], 'mathtext.fontset':'stix','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'normal','axes.grid':True,'grid.color':'0.84','grid.linewidth':0.45,'figure.dpi':150,'savefig.bbox':'tight','pdf.fonttype':42})
C=['#1f77b4','#d62728','#2ca02c','#ff7f0e']
m=1.; g=9.81; J=np.eye(3); cf=1e-3; cd=1e-5; arm=.3
F=np.array([[cf]*4,[1,1,-1,-1],[-1,1,1,-1],[cd,-cd,cd,-cd]],float);F[1:3]*=cf*arm/np.sqrt(2); FI=np.linalg.inv(F)
e3=np.array([0.,0.,1.]); D=np.array([.1,.1,.2])
def cross(a,b):
    return np.array([a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]])
def ref(t,scale=2.,smooth=False,hover=False):
    if hover:return np.array([0.,5.,2.]),np.zeros(3),np.zeros(3),0.
    w=1/scale; T=4.
    if smooth and t<T:
        u=t/T; th=w*T*(2.5*u**4-3*u**5+u**6); wd=w*(10*u**3-15*u**4+6*u**5); wdd=w/T*(30*u**2-60*u**3+30*u**4)
    else:th=w*(t-(T/2 if smooth else 0));wd=w;wdd=0.
    sn,cs=np.sin(th),np.cos(th)
    p=np.array([5*sn,5*cs,2]);v=np.array([5*cs*wd,-5*sn*wd,0]);a=np.array([5*(cs*wdd-sn*wd*wd),-5*(sn*wdd+cs*wd*wd),0])
    return p,v,a,-th

def control(t,y,c):
    x,v,q,om=y[:3],y[3:6],y[6:10],y[10:13]
    R=Rotation.from_quat(q).as_matrix(); pd,vd,ad,yaw=ref(t,c.get('scale',2),c.get('smooth',False),c.get('hover',False))
    vb=R.T@v; drag=-R@(D*vb*np.abs(vb))*c.get('drag',0)
    dhat=-R@(D*vb*np.abs(vb))*c.get('comp',0)
    A=-c.get('kx',4)*(x-pd)-c.get('kv',4)*(v-vd)+g*e3+ad-dhat
    b3=A/np.linalg.norm(A); b1c=np.array([np.cos(yaw),np.sin(yaw),0]); b2=cross(b3,b1c);b2/=np.linalg.norm(b2);Rd=np.column_stack([cross(b2,b3),b2,b3])
    E=(Rd.T@R-R.T@Rd)/2; er=np.array([E[2,1],E[0,2],E[1,0]])
    f=A@R[:,2]; M=-c.get('kR',100)*er-c.get('kOmega',20)*om+cross(om,J@om)
    return f,M,drag,R,pd,vd,ad,Rd

def rhs(t,y,c):
    f,M,drag,R,*_=control(t,y,c); om=y[10:13];q=y[6:10]
    qdot=np.r_[.5*(q[3]*om+cross(q[:3],om)),-.5*(q[:3]@om)]
    force=np.array([1.,0,0]) if c.get('pulse') and 12<=t<13 else np.zeros(3)
    return np.r_[y[3:6],-g*e3+f*R[:,2]+drag+force,qdot,M-cross(om,J@om)]

def run(name,c,maxstep=.02):
    y0=np.r_[np.array([0.,5.,2.])+np.array(c.get('offset',[0,0,0])),np.zeros(3),[0.,0.,0.,1.],np.zeros(3)]
    t=np.arange(0,30.0001,.01)
    # Integrate pulse at its discontinuities explicitly.
    stops=[0,12,13,30] if c.get('pulse') else [0,30]
    chunks=[];cur=y0
    for l,r in zip(stops[:-1],stops[1:]):
        tt=t[(t>=l)&(t<=r)]
        sol=solve_ivp(lambda a,b:rhs(a,b,c),(l,r),cur,t_eval=tt,method='DOP853',rtol=1e-9,atol=1e-11,max_step=maxstep)
        assert sol.success;cur=sol.y[:,-1];chunks.append(sol.y.T if not chunks else sol.y.T[1:])
    y=np.concatenate(chunks); vals=[control(a,b,c) for a,b in zip(t,y)]
    pd=np.array([z[4] for z in vals]); err=np.linalg.norm(y[:,:3]-pd,axis=1);v=np.linalg.norm(y[:,3:6],axis=1)
    wrench=np.array([np.r_[z[0],z[1]] for z in vals]); u=wrench@FI.T;rot=np.sign(u)*np.sqrt(abs(u)); tilt=np.array([np.arccos(np.clip(z[3][2,2],-1,1))*180/np.pi for z in vals])
    yaw=np.array([np.arctan2(z[3][1,0],z[3][0,0]) for z in vals]); yd=np.array([ref(a,c.get('scale',2),c.get('smooth',False),c.get('hover',False))[3] for a in t]); ye=np.rad2deg(np.arctan2(np.sin(yaw-yd),np.cos(yaw-yd)))
    mask=t>=10;first=t<=4
    metrics={'rmse_all':float(np.sqrt(np.mean(err**2))),'rmse_steady':float(np.sqrt(np.mean(err[mask]**2))),'max_steady':float(err[mask].max()),'p95_steady':float(np.quantile(err[mask],.95)),'max_start':float(err[first].max()),'max_tilt':float(tilt.max()),'rotor_abs_max':float(abs(rot).max()),'negative_rotor_fraction':float(np.mean(rot<0)),'yaw_rmse_steady_deg':float(np.sqrt(np.mean(ye[mask]**2))),'max_quat_norm_error':float(abs(np.linalg.norm(y[:,6:10],axis=1)-1).max())}
    np.savetxt(OUT/(name+'.csv'),np.column_stack([t,y,pd,err,rot,tilt,ye]),delimiter=',',header='t,x,y,z,vx,vy,vz,qx,qy,qz,qw,wx,wy,wz,xd,yd,zd,error,rotor1,rotor2,rotor3,rotor4,tilt_deg,yaw_error_deg',comments='')
    print(name,metrics,flush=True)
    return dict(t=t,y=y,pd=pd,err=err,rot=rot,tilt=tilt,ye=ye,metrics=metrics,c=c)

def save(name):
    fig=plt.gcf()
    paired={'circle','combined_design','error_components','drag','hover_rotors','robustness'}
    if name in paired:
        fig.set_size_inches(4.5,5.5)
        grid=fig.add_gridspec(2,1)
        for i,ax in enumerate(fig.axes): ax.set_subplotspec(grid[i])
    for ax in fig.axes:
        if name not in {'overview','allocation'}:
            for line in ax.lines:
                if line.get_color() in C and len(ax.lines)>1:
                    line.set_linestyle(['-','--',':','-.'][C.index(line.get_color())])
            legend=ax.get_legend()
            if legend:
                handles,labels=ax.get_legend_handles_labels()
                ax.legend(handles,labels,loc='upper left' if ax.name=='3d' else 'best',fontsize=10,frameon=True, edgecolor='black', facecolor='white', framealpha=1.0, fancybox=False,ncol=1 if name!='error_components' else 2)
    if name in paired: fig.tight_layout(pad=.65,h_pad=1.1)
    plt.savefig(FIG/(name+'.pdf'));plt.savefig(FIG/(name+'.png'),dpi=180);plt.close()
def label(ax,title,x='Time (s)',y=None):
    ax.set_title(title,loc='left',fontsize=13,pad=10);ax.set_xlabel(x)
    if y:ax.set_ylabel(y)

def make_overview():
    """Typeset the overview with the manuscript's Times and math fonts."""
    import shutil, subprocess, tempfile
    with tempfile.TemporaryDirectory(prefix='lab3-overview-') as build:
        latex = shutil.which('pdflatex') or '/Library/TeX/texbin/pdflatex'
        subprocess.run([latex,'-interaction=nonstopmode',
                        '-halt-on-error',f'-output-directory={build}',
                        'overview_figure.tex'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        shutil.copyfile(Path(build)/'overview_figure.pdf',FIG/'overview.pdf')
        subprocess.run(['pdftoppm','-singlefile','-scale-to', '2200','-png',
                        str(FIG/'overview.pdf'),str(FIG/'overview')],check=True)

def main():
    if os.environ.get('LAB3_OVERVIEW_ONLY'):
        make_overview();return
    cases={'nominal':{},'smooth':{'smooth':True},'drag':{'drag':1},'compensated':{'drag':1,'comp':1},'slow':{'drag':1,'scale':4},'fast':{'drag':1,'scale':1},'undercomp':{'drag':1,'comp':.5},'overcomp':{'drag':1,'comp':1.5},'hover':{'hover':True,'offset':[.5,-.5,-.5]},'pulse':{'smooth':True,'drag':1,'comp':1,'pulse':True},'lowdamping':{'kv':2}}
    if os.environ.get('LAB3_REPLOT'):
        stored=json.loads((OUT/'metrics.json').read_text());runs={}
        for k,c in cases.items():
            z=np.loadtxt(OUT/(k+'.csv'),delimiter=',',skiprows=1)
            runs[k]=dict(t=z[:,0],y=z[:,1:14],pd=z[:,14:17],err=z[:,17],rot=z[:,18:22],tilt=z[:,22],ye=z[:,23],metrics=stored[k],c=c)
        delta=stored['numerical_check']['max_position_difference_m']
    else:
        runs={k:run(k,v) for k,v in cases.items()}
        fine=run('nominal_fine',{},.01);delta=np.linalg.norm(runs['nominal']['y'][:,:3]-fine['y'][:,:3],axis=1).max()
    metrics={k:v['metrics'] for k,v in runs.items()};metrics['numerical_check']={'max_position_difference_m':float(delta)}
    metrics['allocation']={'rank_normal':int(np.linalg.matrix_rank(F)), 'rank_reversed':int(np.linalg.matrix_rank(F*np.array([[1,1,1,1]]*3+[[1,1,-1,-1]]))), 'hover_rotor_rad_s':float(np.sqrt(g/(4*cf)))}
    (OUT/'metrics.json').write_text(json.dumps(metrics,indent=2));(OUT/'conditions.json').write_text(json.dumps(cases,indent=2))
    r=runs['nominal'];fig=plt.figure(figsize=(10,3.2));ax=fig.add_subplot(121,projection='3d');ax.plot(*r['pd'].T,'--',c='#9AA8B2',lw=2,label='Reference');ax.plot(*r['y'][:,:3].T,c=C[0],lw=1.3,label='Tracked');ax.set(xlabel='x (m)',ylabel='y (m)',zlabel='z (m)',zlim=(1.8,2.2));ax.set_title('(a) Spatial trajectory',loc='left');ax.legend(fontsize=10);ax=fig.add_subplot(122);ax.plot(r['pd'][:,0],r['pd'][:,1],'--',c='#9AA8B2',lw=2,label='Reference');ax.plot(r['y'][:,0],r['y'][:,1],c=C[0],lw=1.2,label='Tracked');ax.scatter([0],[5],c=C[1],s=35,zorder=4,label='Start');label(ax,'(b) Top view','x (m)','y (m)');ax.axis('equal');ax.legend(fontsize=10);fig.tight_layout();save('circle')
    fig,axs=plt.subplots(2,2,figsize=(10,4.8));
    for i in range(3):axs[0,0].plot(r['t'],r['y'][:,i]-r['pd'][:,i],label=['x','y','z'][i],color=C[i])
    label(axs[0,0],'(a) Position error',y='Error (m)');axs[0,0].legend(ncol=3,fontsize=10)
    for k,col,lab in [('nominal',C[0],'kv = 4'),('lowdamping',C[1],'kv = 2')]:axs[0,1].plot(runs[k]['t'],runs[k]['err'],color=col,label=lab)
    label(axs[0,1],'(b) Damping comparison',y='Position error (m)');axs[0,1].legend(fontsize=10)
    axs[1,0].plot(r['t'],r['tilt'],color=C[2]);label(axs[1,0],'(c) Tilt response',y='Tilt (deg)')
    axs[1,1].plot(r['t'],r['ye'],color=C[3]);label(axs[1,1],'(d) Heading response',y='Yaw error (deg)');fig.tight_layout();save('tracking')
    tt=np.linspace(0,8,801);fig,axs=plt.subplots(1,3,figsize=(10,3.1))
    for sm,col,lab in [(False,C[1],'Direct start'),(True,C[0],'Smooth start')]:
        refs=[ref(t,smooth=sm) for t in tt];axs[0].plot(tt,[np.linalg.norm(z[1]) for z in refs],color=col,label=lab);axs[1].plot(tt,[np.linalg.norm(z[2]) for z in refs],color=col);rr=runs['smooth' if sm else 'nominal'];axs[2].plot(rr['t'],rr['err'],c=col)
    for ax,title,y in zip(axs,['(a) Reference speed','(b) Reference acceleration','(c) Startup tracking'],['Speed (m/s)','Acceleration (m/s²)','Position error (m)']):label(ax,title,y=y);ax.set_xlim(0,8)
    axs[0].legend(fontsize=10);fig.tight_layout();save('startup')
    fig,axs=plt.subplots(1,2,figsize=(10,3.3))
    for k,col,lab in [('nominal',C[2],'No drag'),('drag',C[1],'Drag, uncompensated'),('compensated',C[0],'Drag, compensated')]:axs[0].plot(runs[k]['t'],runs[k]['err'],c=col,label=lab)
    label(axs[0],'(a) Matched circular tracking',y='Position error (m)');axs[0].legend(fontsize=10);axs[0].set_ylim(0,.85)
    keys=['slow','drag','fast'];xs=np.arange(3);vv=[metrics[k]['rmse_steady'] for k in keys];bars=axs[1].bar(xs,vv,color=[C[2],C[0],C[1]],width=.55)
    for b,vv0 in zip(bars,vv):axs[1].text(b.get_x()+b.get_width()/2,b.get_height()+.015,f'{vv0:.3f}',ha='center',fontsize=11)
    axs[1].set_xticks(xs,['1.25','2.50','5.00']);label(axs[1],'(b) Speed and tracking accuracy','Reference speed (m/s)','Steady RMSE (m)');axs[1].set_ylim(0,max(vv)*1.25);fig.tight_layout();save('drag')
    fig,axs=plt.subplots(1,2,figsize=(10,3.1));keys=['drag','undercomp','compensated','overcomp'];v=[metrics[k]['rmse_steady'] for k in keys];axs[0].plot([0,.5,1,1.5],v,'o-',c=C[0]);label(axs[0],'(a) Drag-model sensitivity','Estimated / true drag coefficient','Steady RMSE (m)')
    p=runs['pulse'];axs[1].plot(p['t'],p['err'],c=C[0]);axs[1].axvspan(12,13,color=C[1],alpha=.22,label='1 N lateral force');label(axs[1],'(b) Disturbance response',y='Position error (m)');axs[1].legend(fontsize=10);axs[1].set_xlim(8,22);fig.tight_layout();save('robustness')
    fig,axs=plt.subplots(1,2,figsize=(10,3.1));h=runs['hover'];
    for i in range(3):axs[0].plot(h['t'],h['y'][:,i]-h['pd'][:,i],c=C[i],label=['x','y','z'][i])
    label(axs[0],'(a) Hover convergence',y='Position error (m)');axs[0].set_xlim(0,12);axs[0].legend(ncol=3,fontsize=10)
    for i in range(4):axs[1].plot(r['t'],r['rot'][:,i],c=C[i],lw=1,label=f'Rotor {i+1}')
    label(axs[1],'(b) Signed rotor commands',y='Angular speed (rad/s)');axs[1].legend(ncol=2,fontsize=10);fig.tight_layout();save('hover_rotors')
    make_overview()
    fig,axs=plt.subplots(1,2,figsize=(9,3.2))
    for ax,flip,title in zip(axs,[False,True],['(a) Standard layout: rank 4','(b) Rotors 3 and 4 reversed: rank 3']):
        for i,(x,y) in enumerate([(1,1),(-1,1),(-1,-1),(1,-1)]):
            ax.plot([0,x],[0,y],c='#6E7F8D',lw=4,zorder=1);sgn=[1,-1,1,-1][i]*(-1 if flip and i>=2 else 1);col=C[0] if sgn>0 else C[1];ax.add_patch(Circle((x,y),.32,facecolor='#F2F6F8',edgecolor=col,lw=2));ax.text(x,y,f'{i+1}\n'+('+' if sgn>0 else '−'),ha='center',va='center',color=col,fontsize=12)
        ax.annotate('',xy=(1.8,0),xytext=(0,0),arrowprops=dict(arrowstyle='->',color='#263445'));ax.text(1.83,0,'x');ax.annotate('',xy=(0,1.7),xytext=(0,0),arrowprops=dict(arrowstyle='->',color='#263445'));ax.text(0,1.8,'y');ax.set(xlim=(-1.6,2.1),ylim=(-1.5,2.1),aspect='equal');ax.axis('off');ax.set_title(title,fontsize=13)
    plt.close(fig)
    import shutil, subprocess, tempfile
    with tempfile.TemporaryDirectory(prefix='lab3-allocation-') as build_dir:
        subprocess.run(['pdflatex', '-interaction=batchmode', '-halt-on-error',
                        '-output-directory='+build_dir, 'allocation_figure.tex'],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        shutil.copy2(Path(build_dir)/'allocation_figure.pdf', FIG/'allocation.pdf')
if __name__=='__main__':main()
