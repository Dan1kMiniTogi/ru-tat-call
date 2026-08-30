#!/usr/bin/env bash
# Quick Cloudflare Tunnel to local signaling (HTTPS + WSS, no Cloudflare account).
#
# Usage (servers already listening on 8000/8001):
#     ./infra/tunnel.sh
#     ./infra/tunnel.sh 8000
#
# Prints a https://*.trycloudflare.com URL — open that on the phone.
set -euo pipefail

PORT="${1:-8000}"
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed." >&2
  echo "Debian/WSL: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  echo "Or: ngrok http ${PORT}" >&2
  exit 1
fi

exec cloudflared tunnel --url "http://127.0.0.1:${PORT}"
