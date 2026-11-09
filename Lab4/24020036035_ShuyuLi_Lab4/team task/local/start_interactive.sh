#!/bin/bash
set -euo pipefail
SRC=$(cd "$(dirname "$0")/.." && pwd)
BASE=/opt/vnav-lab4
LAB4_BROWSER_PREFERRED=${LAB4_BROWSER_PREFERRED:-1}
export LAB4_BROWSER_PREFERRED
mkdir -p "$BASE/logs"
if { [ "$LAB4_BROWSER_PREFERRED" = 1 ] || [ ! -S /mnt/wslg/.X11-unix/X0 ]; } && [ "${LAB4_PRIVATE_X11:-}" != 1 ]; then
 exec unshare --mount --propagation private env LAB4_PRIVATE_X11=1 bash "$0"
fi
if [ "${LAB4_PRIVATE_X11:-}" = 1 ]; then
 mkdir -p "$BASE/interactive-x11"
 chmod 1777 "$BASE/interactive-x11"
 mount --bind "$BASE/interactive-x11" /tmp/.X11-unix
fi
exec 9>"$BASE/interactive.lock"
flock -n 9 || { echo 'Lab4 interactive is already running. Use the existing windows.'; exit 0; }
if [ "${LAB4_INTERACTIVE_NET:-}" != 1 ]; then
 export LAB4_INTERACTIVE_NET=1
 if [ "$LAB4_BROWSER_PREFERRED" != 1 ] && [ -S /mnt/wslg/.X11-unix/X0 ]; then
  export LAB4_DISPLAY=:0
  exec unshare --net bash "$SRC/local/start_interactive_inner.sh" "$SRC"
 fi
 echo 'Opening live Unity + visual race timer at http://localhost:6085/vnc.html?autoconnect=1&resize=scale'
 export LAB4_DISPLAY=:97 LAB4_BROWSER_DISPLAY=1
 children=()
 cleanup() { for p in "${children[@]}"; do kill "$p" 2>/dev/null || true; done; }
 trap cleanup EXIT
 Xvfb :97 -screen 0 1440x850x24 -ac -nolisten tcp +extension GLX > "$BASE/logs/interactive_xvfb.log" 2>&1 & children+=("$!")
 sleep 1
 DISPLAY=:97 openbox > "$BASE/logs/interactive_wm.log" 2>&1 & children+=("$!")
 env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 x11vnc -display :97 -localhost -rfbport 5905 -nopw -forever -shared > "$BASE/logs/interactive_vnc.log" 2>&1 & children+=("$!")
 websockify --web=/usr/share/novnc 127.0.0.1:6085 127.0.0.1:5905 > "$BASE/logs/interactive_browser.log" 2>&1 & children+=("$!")
 /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "Start-Process 'http://localhost:6085/vnc.html?autoconnect=1&resize=scale'" >/dev/null 2>&1 || true
 unshare --net bash "$SRC/local/start_interactive_inner.sh" "$SRC"
fi
