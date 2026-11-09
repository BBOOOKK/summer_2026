#!/usr/bin/env python3
"""Native Unity + ROS controller supervisor with a Tk control panel."""
import argparse,json,os,queue,signal,socket,struct,subprocess,threading,time,re,shutil,ctypes as ct
from pathlib import Path
import tkinter as tk
from tkinter import ttk
parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);args=parser.parse_args()
base=Path('/opt/vnav-lab4');source=Path(args.source);runtime=base/'focal/work/lab4'
subsecond=os.environ.get('LAB4_SUBSECOND')=='1'
profile_file=source/'local'/('subsecond_profile.json' if subsecond else 'fast_profile.json')
fast_profile=json.loads(profile_file.read_text())
run='interactive_'+time.strftime('%Y%m%d_%H%M%S');out=runtime/'results'/run;out.mkdir(parents=True)
(base/'interactive.pid').write_text(str(os.getpid()))
env=os.environ.copy();env.update(ROS_MASTER_URI='http://127.0.0.1:11314',ROS_HOSTNAME='127.0.0.1')
processes={};handles=[];commands=queue.Queue();events=queue.Queue();closing=threading.Event();phase='Starting';round_number=0;active_target=None
def ros(cmd):return ['bash',str(base/'scripts/run_focal.sh')]+cmd
def launch(name,cmd):
 f=(out/(name+'.log')).open('a');handles.append(f)
 p=subprocess.Popen(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);processes[name]=p;return p
def stop(names):
 owned=[processes.pop(n) for n in names if n in processes]
 graceful=[]
 for p in owned:
  if p.stdin is not None:
   try:p.stdin.close();graceful.append(p)
   except (BrokenPipeError,OSError):pass
 for p in owned:
  if p.poll() is None and p not in graceful:os.killpg(p.pid,signal.SIGINT)
 for p in owned:
  try:p.wait(timeout=15 if p in graceful else 3)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
def packet(tag,*values):
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.sendto(tag.encode()+struct.pack('<'+'f'*len(values),*values),('127.0.0.1',9000))
def reset():
 if active_target is not None:(active_target/'capture.done').write_text('done')
 stop(['controller','planner','waypoints','recorder','bag','video','timer','native_encoder'])
 (runtime/'interactive_timer.json').unlink(missing_ok=True)
 packet('sPpS',0,0,0,0)
 # This quadrotor build ignores the generic ground-agent RSPN packet.
 # Reset the quadrotor to its measured initial pose through its supported API.
 for _ in range(3):
  if subsecond:packet('sPoS',.4,2.,8.,0.,.9929127,0.,.1188459)
  else:packet('sPoS',.4000291,2.,8.000004,0.,.7861341,0.,-.6180559)
  time.sleep(.1)
 time.sleep(.5)
def status(s):
 events.put(s);(source/'local/interactive_state.json').write_text(json.dumps({'phase':s,'run':str(out),'pid':os.getpid(),'updated_wall':time.time()},indent=2))
def call(cmd):
 r=subprocess.run(ros(cmd),env=env,capture_output=True,text=True,timeout=60)
 if r.returncode:raise RuntimeError(r.stderr[-400:] or str(cmd))
 return r
def bind_unity_reset(pid):
 # Register an application shortcut on this Unity window only. This also
 # resets the ROS planner, which the original game's R key cannot do.
 x=ct.CDLL('libX11.so.6');x.XOpenDisplay.restype=ct.c_void_p
 d=x.XOpenDisplay(env['DISPLAY'].encode())
 if not d:return
 x.XKeysymToKeycode.argtypes=[ct.c_void_p,ct.c_ulong];x.XKeysymToKeycode.restype=ct.c_uint
 x.XGrabKey.argtypes=[ct.c_void_p,ct.c_int,ct.c_uint,ct.c_ulong,ct.c_int,ct.c_int,ct.c_int]
 x.XPending.argtypes=[ct.c_void_p];x.XNextEvent.argtypes=[ct.c_void_p,ct.c_void_p];x.XFlush.argtypes=[ct.c_void_p];x.XCloseDisplay.argtypes=[ct.c_void_p]
 tree=subprocess.check_output(['xwininfo','-root','-tree'],env=env,text=True)
 for wid in re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+',tree,re.M):
  prop=subprocess.run(['xprop','-id',wid,'_NET_WM_PID'],env=env,capture_output=True,text=True)
  match=re.search(r'=\s*(\d+)',prop.stdout)
  if match and int(match.group(1))==pid:
   x.XGrabKey(d,x.XKeysymToKeycode(d,ord('r')),1<<15,int(wid,16),0,1,1)
   if env.get('LAB4_BROWSER_DISPLAY'):
    x.XMoveWindow.argtypes=[ct.c_void_p,ct.c_ulong,ct.c_int,ct.c_int]
    x.XMoveWindow(d,int(wid,16),0,0)
 x.XFlush(d)
 event=(ct.c_long*24)()
 while not closing.is_set():
  while x.XPending(d):
   x.XNextEvent(d,ct.byref(event))
   if ct.cast(ct.byref(event),ct.POINTER(ct.c_int))[0]==2:commands.put(('reset',1.0))
  time.sleep(.01)
 x.XCloseDisplay(d)
def worker():
 global round_number,active_target
 try:
  unity_path=base/'simulator-nointerp/lab4/lab4.x86_64' if subsecond else base/'simulator-interactive/lab4.x86_64'
  launch('unity',[str(unity_path),'-screen-width','960','-screen-height','540','-screen-fullscreen','0','-job-worker-count','4','-logFile',str(out/'unity_player.log')])
  launch('roscore',ros(['roscore','-p','11314']))
  time.sleep(12)
  if processes['unity'].poll() is not None:raise RuntimeError('Unity failed; inspect '+str(out/'unity_player.log'))
  bridge_launch='tesse_quadrotor_bridge_sync.launch' if subsecond else 'tesse_quadrotor_bridge.launch'
  extra_bridge=['publish_clock:=false','publish_collisions:=false'] if subsecond else ['publish_collisions:=true']
  launch('bridge',ros(['roslaunch','tesse_ros_bridge',bridge_launch,'imu_rate:=100','publish_imu:=false']+extra_bridge))
  call(['rostopic','echo','-n','1','/tesse/asynchronous_state' if subsecond else '/current_state'])
  threading.Thread(target=bind_unity_reset,args=(processes['unity'].pid,),daemon=True).start()
  launch('status',ros(['python3','/work/lab4/scripts/monitor_interactive.py']))
  params=dict(kx=4.,kv=3.,kr=3.,komega=1.,yaw_rate_feedforward=False,max_rotor_speed=1000.,control_hz=100.,
              attitude_accel_feedforward=0.,feedback_attitude_rate=False,yaw_kr=3.,yaw_komega=1.,
              prioritize_thrust_tilt=False,kz=4.,kvz=3.,minimum_vertical_force=0.)
  (out/'params.json').write_text(json.dumps(params));call(['rosparam','load','/work/lab4/results/'+run+'/params.json'])
  status('Ready - live physics');commands.put(('fast',fast_profile['scale']));finished_notice=False
  while not closing.is_set():
   if processes['unity'].poll() is not None:closing.set();break
   if not finished_notice and 'recorder' in processes and processes['recorder'].poll()==0:
    (target/'capture.done').write_text('done')
    stop(['bag','video','timer','native_encoder'])
    call(['python3','/work/lab4/scripts/read_flight_data.py','--case',run+'/'+target.name])
    call(['python3','/work/lab4/scripts/race_timer.py','--gates','/work/lab4/results/gates.json','--replay','/work/lab4/results/'+run+'/'+target.name])
    checked=json.loads((target/'race_timer_replay.json').read_text())
    if not checked['valid']:
     checked['phase']='INVALID - RESTART' if checked['finish_stamp_ns'] is not None else 'INCOMPLETE - RESTART'
    tmp=runtime/'interactive_timer.json.tmp';tmp.write_text(json.dumps(checked));tmp.replace(runtime/'interactive_timer.json')
    shutil.copytree(target,source/'results'/run/target.name,dirs_exist_ok=True)
    status(('Race finished - ' if checked['valid'] else 'Trial incomplete/invalid - ')+checked['display']+'; results saved');finished_notice=True
   request=source/'local/interactive_command.json'
   if request.exists():
    try:
     v=json.loads(request.read_text());request.unlink();commands.put((v['action'],float(v.get('scale',1))))
    except (json.JSONDecodeError,FileNotFoundError):pass
   try:action,scale=commands.get(timeout=.2)
   except queue.Empty:continue
   if action=='close':closing.set();break
   if action in ['race','hover','fast']:
    status('Preparing '+action);reset();round_number+=1;finished_notice=False
    target=out/('round_%02d'%round_number);target.mkdir();active_target=target
    profile=json.loads(profile_file.read_text()) if action=='fast' else None
    rigid=bool(profile and profile.get('mode')=='rigid_reference')
    selected=dict(profile['params']) if rigid else (dict(profile['controller']) if action=='fast' else dict(params,attitude_rate_feedforward=False,drag_compensation=False))
    if rigid:selected['pilot_capture_frames']=True
    planner={} if rigid else (dict(profile['planner']) if action=='fast' else dict(first_segment_factor=1.,exit_distance=0.,exit_duration=1.,exit_speed=5.,segment_factors=''))
    planner.setdefault('segment_factors','')
    planner.setdefault('vertical_derivative_order',4)
    planner.setdefault('vertical_gate_velocities','')
    if action=='fast':scale=profile['scale']
    (target/'config.json').write_text(json.dumps(dict(name=target.name,scale=scale,controller=selected,planner=planner,mode='live interactive Unity')))
    if rigid:
     reference=runtime/profile['reference']
     (target/'optimized_reference.csv').write_bytes(reference.read_bytes())
     (target/'model_status.json').write_bytes((reference.parent/'model_status.json').read_bytes())
     (target/'profile.json').write_text(json.dumps(profile,indent=2))
    inner='/work/lab4/results/'+run+'/'+target.name
    (target/'params.json').write_text(json.dumps(selected));call(['rosparam','load',inner+'/params.json'])
    launch('bag',ros(['rosbag','record','-O',inner+'/race.bag','/current_state','/desired_state','/desired_traj_vertices','/clock','/tesse/collision','/tesse/native_metadata','/rotor_speed_cmds','/controller_diagnostics','/race_timer']))
    launch('timer',ros(['python3','/work/lab4/scripts/race_timer.py','--gates','/work/lab4/results/gates.json','--output',inner+'/race_timer.json','--live-output','/work/lab4/interactive_timer.json']))
    if action=='fast' and env.get('LAB4_BROWSER_DISPLAY'):
     launch('video',['ffmpeg','-y','-f','x11grab','-framerate','30','-video_size','960x540','-i',env['DISPLAY']+'.0+0,20','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p',str(target/'unity_live.mp4')])
    launch('recorder',ros(['python3','/work/lab4/scripts/record_race.py','--output',inner+'/telemetry.csv','--duration','20']))
    if rigid:
     launch('planner',ros(['python3','/work/lab4/scripts/rigid_reference_node.py','--reference','/work/lab4/'+profile['reference'],'--plan-output',inner+'/plan.csv','--params-json',json.dumps(selected)]))
    elif action in ['race','fast']:
     launch('controller',ros(['rosrun','controller_pkg','controller_node']))
     extra=['_'+k+':='+str(v) for k,v in planner.items()]
     launch('planner',ros(['rosrun','trajectory_generation','trajectory_generation_node','_time_scale:='+str(scale),'_plan_output:='+inner+'/plan.csv']+extra))
    else:
     launch('controller',ros(['rosrun','controller_pkg','controller_node']))
     launch('planner',ros(['rosrun','planner_pkg','simple_traj_planner']))
    time.sleep(.8)
    launch('waypoints',ros(['roslaunch','planner_pkg','traj_gen.launch','simulator_data_directory:=/work/lab4/simulator/lab4/lab4_Data']))
    status(('Racing'+(' optimized' if action=='fast' else '') if action in ['race','fast'] else 'Hover at gate 1')+' - live controller')
   elif action=='reset':reset();status('Reset - motors off')
   elif action=='stop':
    if active_target is not None:(active_target/'capture.done').write_text('done')
    stop(['controller','planner','waypoints','recorder','bag','video','timer','native_encoder']);packet('sPpS',0,0,0,0);status('Control stopped - motors off')
 except Exception as e:status('ERROR: '+str(e));events.put('ERROR: '+str(e))
 finally:
  stop(list(processes));closing.set()
  (base/'interactive.pid').unlink(missing_ok=True)
  for f in handles:f.close()
  status('Stopped')
root=tk.Tk();root.title('Lab4 Control Panel');root.geometry('480x520+50+50')
if env.get('LAB4_BROWSER_DISPLAY'):root.geometry('460x520+970+20')
root.configure(padx=16,pady=12)
ttk.Label(root,text='MIT VNAV Lab4 - LIVE SIMULATION',font=('Sans',14,'bold')).pack(anchor='w')
ttk.Label(root,text='Native 20 ms physics | rotor limit 2000 rad/s' if subsecond else 'Original Unity scene + ROS planner + feedback controller').pack(anchor='w',pady=(4,12))
label=tk.StringVar(value='Starting Unity and ROS ...');ttk.Label(root,textvariable=label,wraplength=440).pack(anchor='w')
telemetry=tk.StringVar(value='Waiting for actual simulator state ...');ttk.Label(root,textvariable=telemetry,justify='left').pack(anchor='w',pady=10)
race_time=tk.StringVar(value='0.000 s');race_progress=tk.StringVar(value='WAITING FOR GATE 1 | 0/12')
flight_time=tk.StringVar(value='Flight: preparing start')
ttk.Label(root,textvariable=race_time,font=('DejaVu Sans Mono',30,'bold')).pack(anchor='w')
ttk.Label(root,textvariable=race_progress).pack(anchor='w')
if subsecond:ttk.Label(root,textvariable=flight_time).pack(anchor='w')
ttk.Label(root,text='Gate 1 -> Gate 12 | simulator clock | interpolated').pack(anchor='w',pady=(0,8))
# A real live HUD on the application display, also captured in the raw MP4.
hud=None
if env.get('LAB4_BROWSER_DISPLAY'):
 hud=tk.Toplevel(root);hud.overrideredirect(True);hud.geometry(('450x110+14+34' if subsecond else '350x91+14+34'));hud.configure(bg='#101820');hud.attributes('-topmost',True)
 tk.Label(hud,textvariable=race_time,font=('DejaVu Sans Mono',27,'bold'),fg='#00f0a8',bg='#101820').pack(anchor='w',padx=10)
 tk.Label(hud,textvariable=race_progress,font=('Sans',11),fg='white',bg='#101820').pack(anchor='w',padx=10)
 if subsecond:tk.Label(hud,textvariable=flight_time,font=('DejaVu Sans Mono',12),fg='#f5cd63',bg='#101820').pack(anchor='w',padx=10)
 tk.Label(hud,text='GATE 1 -> 12  |  SIM TIME / INTERPOLATED',font=('Sans',9),fg='#b4c8d0',bg='#101820').pack(anchor='w',padx=10)
scale=tk.StringVar(value='1.0');row=ttk.Frame(root);row.pack(fill='x')
ttk.Label(row,text='Trajectory time scale:').pack(side='left');ttk.Combobox(row,textvariable=scale,values=['1.0','0.8','0.6','0.4','0.35'],width=8,state='readonly').pack(side='left',padx=10)
def send(action):commands.put((action,float(scale.get())))
buttons=[('Start / Restart fastest race + timer','fast'),('Reset (motors off)','reset'),('Stop control','stop')] if subsecond else [('Start / Restart fastest race + timer','fast'),('Start / Restart baseline race','race'),('Hover at first gate','hover'),('Reset (motors off)','reset'),('Stop control','stop')]
for title,action in buttons:
 ttk.Button(root,text=title,command=lambda a=action:send(a)).pack(fill='x',pady=3)
ttk.Label(root,text='Click Unity, then R: reset drone and stop controller.\nUse Restart race to start a fresh planned flight.').pack(anchor='w',pady=6)
root.protocol('WM_DELETE_WINDOW',lambda:closing.set())
class XImage(ct.Structure):
 _fields_=[('width',ct.c_int),('height',ct.c_int),('xoffset',ct.c_int),('format',ct.c_int),('data',ct.c_void_p),('byte_order',ct.c_int),('bitmap_unit',ct.c_int),('bitmap_bit_order',ct.c_int),('bitmap_pad',ct.c_int),('depth',ct.c_int),('bytes_per_line',ct.c_int)]
capture={}
def capture_native_frame(timing):
 if not subsecond or active_target is None or (active_target/'capture.done').exists():return
 try:request=json.loads((active_target/'capture_request.json').read_text())
 except (OSError,ValueError):return
 if timing is None or timing.get('sample_stamp_ns',0)<request['native_stamp_ns']:return
 if capture.get('target')==active_target and request['index']<=capture.get('index',-1):return
 if 'display' not in capture:
  x=ct.CDLL('libX11.so.6');x.XOpenDisplay.restype=ct.c_void_p
  x.XDefaultRootWindow.argtypes=[ct.c_void_p];x.XDefaultRootWindow.restype=ct.c_ulong
  x.XGetImage.argtypes=[ct.c_void_p,ct.c_ulong,ct.c_int,ct.c_int,ct.c_uint,ct.c_uint,ct.c_ulong,ct.c_int];x.XGetImage.restype=ct.POINTER(XImage)
  x.XDestroyImage.argtypes=[ct.POINTER(XImage)]
  d=x.XOpenDisplay(env['DISPLAY'].encode())
  if not d:return
  capture.update(x=x,display=d,window=x.XDefaultRootWindow(d))
 if capture.get('target')!=active_target:
  log=(active_target/'native_video.log').open('a');handles.append(log)
  encoder=subprocess.Popen(['ffmpeg','-y','-f','rawvideo','-pixel_format','bgr0','-video_size','960x540','-framerate','50','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(active_target/'native_1x.mp4')],stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
  processes['native_encoder']=encoder;capture.update(target=active_target,index=-1,encoder=encoder)
 if hud is not None:hud.lift()
 root.update_idletasks()
 image=capture['x'].XGetImage(capture['display'],capture['window'],0,20,960,540,0xffffffff,2)
 if not image:return
 try:
  value=image.contents
  if value.bytes_per_line!=960*4:raise RuntimeError('Unexpected X11 pixel stride')
  pixels=ct.string_at(value.data,value.bytes_per_line*value.height)
  capture['encoder'].stdin.write(pixels)
 except (BrokenPipeError,OSError):return
 finally:capture['x'].XDestroyImage(image)
 capture['index']=request['index']
 acknowledgement=active_target/'capture_ack.json';temporary=acknowledgement.with_suffix('.tmp')
 temporary.write_text(json.dumps({'index':request['index']}));temporary.replace(acknowledgement)

def tick():
 while not events.empty():label.set(events.get_nowait())
 timing=None
 try:
  timing=json.loads((runtime/'interactive_timer.json').read_text())
  race_time.set(timing['display'])
  race_progress.set('%s | %d/%d%s'%(timing['phase'],timing['gates_passed'],timing['gates_total'],' | INVALID: COLLISION' if timing['collisions'] else ''))
  if subsecond and active_target is not None:
   start=json.loads((active_target/'pilot_start.json').read_text())['stamp']
   live=json.loads((active_target/'pilot_live.json').read_text())
   finish=timing['finish_stamp_ns']/1e9 if timing['finish_stamp_ns'] is not None else live['native_stamp_s']
   flight_time.set('Flight: %.3f s | rotor <= 2000 rad/s'%max(0,finish-start))
 except (OSError,ValueError,KeyError):
  race_time.set('0.000 s');race_progress.set('WAITING FOR GATE 1 | 0/12')
  flight_time.set('Flight: preparing start')
 if hud is not None:hud.lift()
 try:capture_native_frame(timing)
 except (OSError,ValueError,KeyError) as e:label.set('Capture error: '+str(e))
 try:
  s=json.loads((runtime/'interactive_status.json').read_text());telemetry.set('Position: %.2f, %.2f, %.2f m\nState: %.1f Hz | simulation/wall time: %.2fx'%(s['x'],s['y'],s['z'],s.get('state_hz',0),s.get('sim_per_wall',0)))
 except (OSError,ValueError,KeyError):pass
 if closing.is_set():
  if not thread.is_alive():root.destroy();return
 root.after(50,tick)
def stop_signal(*_):closing.set()
signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
signal.signal(signal.SIGHUP,stop_signal)
thread=threading.Thread(target=worker,daemon=True);thread.start();root.after(200,tick);root.mainloop();thread.join(timeout=15)
