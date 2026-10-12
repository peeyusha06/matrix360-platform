#!/usr/bin/env bash
# Starts the whole platform on one laptop. Stop with: bash stop.sh
#   Shared DB (Mayur)       http://127.0.0.1:8000   dashboard: /  API docs: /docs
#   Chat widget (Avinash)   http://127.0.0.1:8001   demo: /demo
#   WhatsApp engage (Tanmayi) http://127.0.0.1:4000
#   Landing site (Shalini)  http://127.0.0.1:5173   (if services/site exists)
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD; S=$ROOT/services; L=$ROOT/logs; mkdir -p logs data
: "${ADMIN_API_KEY:=demo-admin-key}"            # change before showing anyone outside the team
: "${INTEGRATION_API_KEY:=demo-integration-key}"
DB=http://127.0.0.1:8000
for port in 8000 8001 4000; do
  if lsof -ti tcp:$port -sTCP:LISTEN >/dev/null 2>&1; then echo "Port $port is busy. Run: bash stop.sh"; exit 1; fi
done

(cd $S/shared-db && DATABASE_URL="sqlite:///$ROOT/data/matrix360.db" ADMIN_API_KEY=$ADMIN_API_KEY \
  INTEGRATION_API_KEY=$INTEGRATION_API_KEY AI_PROVIDER=${AI_PROVIDER:-demo} \
  nohup $ROOT/.venv/bin/python -m uvicorn app.main:app --port 8000 > $L/shared-db.log 2>&1 & echo $! > $L/shared-db.pid)

(cd $S/chat && ALLOW_LOCALHOST=1 ADMIN_KEY=$ADMIN_API_KEY DB_PATH="$ROOT/data/chat.db" \
  DB_API_URL=$DB/integrations/chat DB_API_KEY=$INTEGRATION_API_KEY DB_FLAVOR=generic \
  nohup $ROOT/.venv/bin/python -m uvicorn server:app --port 8001 > $L/chat.log 2>&1 & echo $! > $L/chat.pid)

(cd $S/engage && PORT=4000 USE_DEV_DB_ADAPTER=false SHARED_DB_URL=$DB/integrations/whatsapp \
  SHARED_DB_API_KEY=$INTEGRATION_API_KEY USE_MOCK_GROK=true WHATSAPP_MOCK_SEND=true \
  SENDING_WINDOW_START_HOUR=${SENDING_WINDOW_START_HOUR:-9} SENDING_WINDOW_END_HOUR=${SENDING_WINDOW_END_HOUR:-20} \
  nohup node server.js > $L/engage.log 2>&1 & echo $! > $L/engage.pid)

if [ -d $S/site ]; then
  (cd $S/site && VITE_FORM_ENDPOINT=$DB/integrations/landing/enquiry nohup npx vite --host 127.0.0.1 --port 5173 --strictPort \
    > $L/site.log 2>&1 & echo $! > $L/site.pid)
fi

URLS="$DB/health http://127.0.0.1:8001/health http://127.0.0.1:4000/api/health"
[ -d $S/site ] && URLS="$URLS http://127.0.0.1:5173/"
for url in $URLS; do
  for i in $(seq 1 40); do curl -sf $url >/dev/null && break; sleep 0.5; done
  curl -sf $url >/dev/null && echo "up   $url" || echo "DOWN $url (see logs/)"
done
