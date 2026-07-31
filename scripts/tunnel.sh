#!/bin/bash
# Start a quick tunnel, wire its URL into .env, and point the A1 number at it.
# The server reads PUBLIC_BASE_URL fresh on every webhook, so no restart needed.
set -e
cd "$(dirname "$0")/.."
PORT=$(grep '^PORT=' .env 2>/dev/null | cut -d= -f2)
PORT=${PORT:-3000}
LOG=$(mktemp)

cloudflared tunnel --url "http://localhost:$PORT" > "$LOG" 2>&1 &
CF_PID=$!
trap 'kill $CF_PID 2>/dev/null' EXIT

echo "starting tunnel for localhost:$PORT ..."
URL=""
for _ in $(seq 1 30); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "tunnel failed to start:"; tail -5 "$LOG"; exit 1
fi

sed -i '' "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$URL|" .env
echo ""
echo "  PUBLIC URL / DASHBOARD:  $URL"
echo "  (written to .env)"
echo ""
node --env-file-if-exists=.env scripts/point-number.mjs \
  || echo "(pointing failed — is the number claimed? run: npm run point)"
echo ""
echo "tunnel is live — keep this terminal open (Ctrl-C stops it)"
wait $CF_PID
