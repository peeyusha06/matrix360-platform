#!/usr/bin/env bash
# Stops every platform service by its port.
cd "$(dirname "$0")"
for port in 8000 8001 4000 5173; do
  pids=$(lsof -ti tcp:$port -sTCP:LISTEN 2>/dev/null) && kill $pids 2>/dev/null
done
rm -f logs/*.pid
echo stopped
