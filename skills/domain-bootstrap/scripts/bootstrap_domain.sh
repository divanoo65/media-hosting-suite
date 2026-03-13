#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./bootstrap_domain.sh <project> <port> [custom_hostname]
#
# Example:
#   ./bootstrap_domain.sh myapp 3000
#   ./bootstrap_domain.sh image 1003 images.vyibc.com

PROJECT="${1:-app}"
PORT="${2:-3000}"
CUSTOM_HOSTNAME="${3:-}"
USER_ID="${USER_ID:-1001}"
BASE_DOMAIN="${BASE_DOMAIN:-vyibc.com}"
DOMAIN_API_BASE="${DOMAIN_API_BASE:-https://domain.vyibc.com/api}"

if ! [[ "$PORT" =~ ^[0-9]{2,5}$ ]]; then
  echo "[error] invalid port: $PORT" >&2
  exit 1
fi

register_payload=$(python3 - <<PY
import json
print(json.dumps({
  "user_id": "${USER_ID}",
  "project": "${PROJECT}",
  "target": "127.0.0.1:${PORT}",
  "base_domain": "${BASE_DOMAIN}",
}))
PY
)

register_resp="$(curl -fsSL -X POST "${DOMAIN_API_BASE}/sessions/register" -H 'Content-Type: application/json' -d "${register_payload}")"
tunnel_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["tunnel"]["id"])' <<<"${register_resp}")"
tunnel_token="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["tunnel"]["token"])' <<<"${register_resp}")"
auto_url="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["public_url"])' <<<"${register_resp}")"
auto_host="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["route"]["hostname"])' <<<"${register_resp}")"

final_host="${auto_host}"

if [[ -n "${CUSTOM_HOSTNAME}" ]]; then
  bind_payload=$(python3 - <<PY
import json
print(json.dumps({
  "tunnel_id": "${tunnel_id}",
  "hostname": "${CUSTOM_HOSTNAME}",
  "target": "127.0.0.1:${PORT}",
  "enabled": True
}))
PY
)
  tmp="$(mktemp)"
  code="$(curl -sS -o "${tmp}" -w '%{http_code}' -X POST "${DOMAIN_API_BASE}/routes" -H 'Content-Type: application/json' -d "${bind_payload}")"
  body="$(cat "${tmp}")"
  rm -f "${tmp}"
  if [[ "${code}" == "200" || "${code}" == "201" ]]; then
    final_host="${CUSTOM_HOSTNAME}"
  elif [[ "${code}" == "409" ]]; then
    echo "[warn] hostname already bound: ${CUSTOM_HOSTNAME}; fallback to auto domain ${auto_host}"
  else
    echo "[error] custom hostname bind failed: status=${code} body=${body}" >&2
    exit 1
  fi
fi

mkdir -p /root/.tunneling/bin
if [[ ! -x /root/.tunneling/bin/agent ]]; then
  curl -fsSL -o /root/.tunneling/bin/agent "https://github.com/ChangfengHU/tunneling/releases/latest/download/agent-linux-amd64"
  chmod +x /root/.tunneling/bin/agent
fi

nohup /root/.tunneling/bin/agent \
  -server ws://152.32.214.95/connect \
  -token "${tunnel_token}" \
  -route-sync-url http://152.32.214.95/_tunnel/agent/routes \
  -tunnel-id "${tunnel_id}" \
  -tunnel-token "${tunnel_token}" \
  -admin-addr 127.0.0.1:17001 >/var/log/tunnel-agent-${PROJECT}.log 2>&1 &

echo "AUTO_URL=${auto_url}"
echo "FINAL_URL=https://${final_host}"
echo "TUNNEL_ID=${tunnel_id}"
echo "TUNNEL_TOKEN=${tunnel_token}"

