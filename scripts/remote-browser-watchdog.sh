#!/bin/bash
# remote-browser-watchdog.sh — keep Xvfb + openbox + Chrome + x11vnc + websockify alive
NOVNC_PORT="${NOVNC_PORT:-1006}"
NOVNC_WEB="/usr/share/novnc"
for d in /usr/share/novnc /usr/share/novnc-web /usr/local/share/novnc; do
  if [ -f "$d/vnc_lite.html" ]; then NOVNC_WEB="$d"; break; fi
done
while true; do
  if ! pgrep -x Xvfb > /dev/null; then
    Xvfb :1 -screen 0 1280x800x24 &
    sleep 2
  fi
  if ! pgrep -x openbox > /dev/null; then
    DISPLAY=:1 openbox > /dev/null 2>&1 &
    sleep 2
  fi
  if ! pgrep -f 'google-chrome|chromium' > /dev/null; then
    BROWSER=google-chrome
    command -v chromium &>/dev/null && BROWSER=chromium
    command -v chromium-browser &>/dev/null && BROWSER=chromium-browser
    DISPLAY=:1 "$BROWSER" --no-sandbox --disable-dev-shm-usage --disable-gpu --start-maximized > /dev/null 2>&1 &
    sleep 3
  fi
  if ! pgrep -x x11vnc > /dev/null; then
    x11vnc -display :1 -nopw -forever -shared -bg -o /var/log/x11vnc.log 2>/dev/null
    sleep 2
  fi
  if ! ss -tlnp | grep -q ":${NOVNC_PORT}"; then
    nohup websockify --web="$NOVNC_WEB" "$NOVNC_PORT" localhost:5900 >> /var/log/novnc.log 2>&1 &
    sleep 2
  fi
  sleep 5
done
