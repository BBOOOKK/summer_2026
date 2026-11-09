from pathlib import Path
import json,numpy as np
p=Path(__file__).resolve().parent
m=json.loads((p/'results/metrics.json').read_text()); d={}
for pre,key in [('Nom','nominal'),('Drag','drag'),('Comp','compensated'),('Smooth','smooth'),('Slow','slow'),('Fast','fast'),('Under','undercomp'),('Over','overcomp'),('Low','lowdamping')]:
 for su,me in [('RMSE','rmse_steady'),('All','rmse_all'),('Max','max_steady'),('Start','max_start'),('Tilt','max_tilt')]:d[pre+su]=f'{m[key][me]:.4f}' if su!='Tilt' else f'{m[key][me]:.2f}'
for pre,key in [('Comp','compensated'),('Under','undercomp'),('Over','overcomp')]:d[pre+'Gain']=f"{100*(1-m[key]['rmse_steady']/m['drag']['rmse_steady']):.1f}"
d['StartGain']=f"{100*(1-m['smooth']['max_start']/m['nominal']['max_start']):.1f}"
d['YawRMSE']=f"{m['nominal']['yaw_rmse_steady_deg']:.2f}"
def scientific(v):
 a,b=f'{v:.2e}'.split('e');return f'${a}\\times10^{{{int(b)}}}$'
d['HoverRMSE']=scientific(m['hover']['rmse_steady']);d['StepDiff']=scientific(m['numerical_check']['max_position_difference_m'])
r=np.loadtxt(p/'results/pulse.csv',delimiter=',',skiprows=1);d['PulseMax']=f'{r[(r[:,0]>=12)&(r[:,0]<=20),17].max():.4f}';d['PulseLate']=f'{np.sqrt(np.mean(r[r[:,0]>=20,17]**2)):.4f}'
(p/'results/numbers.tex').write_text('\n'.join('\\newcommand{\\'+k+'}{'+v+'}' for k,v in d.items()))
print(m['numerical_check']);print({k:v for k,v in d.items() if 'Gain' in k})
