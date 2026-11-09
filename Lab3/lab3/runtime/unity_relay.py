#!/usr/bin/env python3
"""Transport relay for the official TESSE UDP/TCP protocol; no dynamics here."""
import socket,struct,json,time,threading
from socketserver import ThreadingTCPServer,StreamRequestHandler
lock=threading.Lock()
def send(tag,values=(),port=9000):
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(tag+struct.pack('<'+'f'*len(values),*values),('127.0.0.1',port));s.close()
def exact(s,n):
 out=b''
 while len(out)<n:
  x=s.recv(n-len(out))
  if not x:raise ConnectionError('metadata disconnected')
  out+=x
 return out
def metadata():
 with socket.socket() as listener:
  listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.settimeout(10);listener.bind(('127.0.0.1',9001));listener.listen(1)
  send(b'rMET',port=9001)
  c,_=listener.accept()
  with c:
   tag=exact(c,4);n=struct.unpack('<I',exact(c,4))[0];return exact(c,n).decode()
class Handler(StreamRequestHandler):
 def handle(self):
  for line in self.rfile:
   try:
    m=json.loads(line)
    with lock:
     if m.get('reset'):send(b'RSPN');time.sleep(.2)
     if m.get('initialize'):send(b'sPoS',[0,2,5,0,0,0,1]);send(b'sPpS',[49.5227]*4);time.sleep(.02)
     if 'rotors' in m:send(b'sPpS',m['rotors'])
     data=metadata()
    self.wfile.write((json.dumps({'xml':data})+'\n').encode());self.wfile.flush()
   except Exception as ex:self.wfile.write((json.dumps({'error':str(ex)})+'\n').encode());self.wfile.flush()
class Server(ThreadingTCPServer):allow_reuse_address=True
print('TESSE relay listening on 0.0.0.0:9010',flush=True)
Server(('0.0.0.0',9010),Handler).serve_forever()
