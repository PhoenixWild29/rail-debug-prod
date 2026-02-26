#!/usr/bin/env bash
set -euo pipefail

VPS_HOST="${VPS_HOST:-your.vps.example.com}"
VPS_USER="${VPS_USER:-ubuntu}"
SERVICE_NAME="rail-debug"
OPT_DIR="/opt/$SERVICE_NAME"

echo "=== Rail Debug VPS Deploy ==="
echo "VPS: $VPS_USER@$VPS_HOST"

# Copy files
echo "Copying service files..."
scp "deploy/rail-debug.service" "$VPS_USER@$VPS_HOST:/etc/systemd/system/"
scp ".env.example" "$VPS_USER@$VPS_HOST:$OPT_DIR/.env"
scp "Dockerfile" "$VPS_USER@$VPS_HOST:$OPT_DIR/"

ssh "$VPS_USER@$VPS_HOST" << EOF
  sudo mkdir -p $OPT_DIR
  sudo chown $VPS_USER:$VPS_USER $OPT_DIR
  cd $OPT_DIR
  sudo docker pull ghcr.io/phoenixwild29/rail-debug-prod:latest || true
  sudo systemctl daemon-reload
  sudo systemctl enable $SERVICE_NAME.service
  sudo systemctl restart $SERVICE_NAME.service
  sudo systemctl status $SERVICE_NAME.service
EOF

echo "✅ Deployed! Check service: ssh $VPS_USER@$VPS_HOST \"sudo systemctl status $SERVICE_NAME.service\""
echo "Edit $OPT_DIR/.env for DATABASE_URL, API keys before restart.