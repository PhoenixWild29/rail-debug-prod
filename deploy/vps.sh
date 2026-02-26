#!/usr/bin/env bash
# deploy/vps.sh — Rail Debug VPS deploy
# Runs from LOCAL machine. Rsyncs code to Droplet then configures server.
# Usage: VPS_USER=root bash deploy/vps.sh
set -euo pipefail

VPS_HOST="${VPS_HOST:-138.197.126.127}"
VPS_USER="${VPS_USER:-root}"
OPT_DIR="/opt/rail-debug"
DOMAIN="debug.secureai.dev"
EMAIL="hello@secureai.dev"

echo "=== Rail Debug VPS Deploy (Sprint 016) ==="
echo "Droplet: $VPS_USER@$VPS_HOST → $DOMAIN"

# ── 1. Sync code to server ───────────────────────────────────────
echo "📦 Syncing code..."
rsync -avz --delete \
  --exclude='venv' \
  --exclude='.git' \
  --exclude='*.db' \
  --exclude='__pycache__' \
  . "$VPS_USER@$VPS_HOST:$OPT_DIR/"

# ── 2. Run server-side setup ─────────────────────────────────────
echo "🔧 Running server setup..."
ssh "$VPS_USER@$VPS_HOST" bash << ENDSSH
set -euo pipefail

# Install nginx + certbot if not present
if ! command -v nginx &>/dev/null; then
  apt-get update -q
  apt-get install -y nginx certbot python3-certbot-nginx
fi

# Deploy static marketing site
mkdir -p /var/www/rail-debug
cp -r $OPT_DIR/web/* /var/www/rail-debug/
chown -R www-data:www-data /var/www/rail-debug

# Install nginx config
cp $OPT_DIR/deploy/nginx.conf /etc/nginx/sites-available/rail-debug
ln -sf /etc/nginx/sites-available/rail-debug /etc/nginx/sites-enabled/rail-debug
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# SSL — skip if cert already exists
if [ ! -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]; then
  certbot --nginx -d $DOMAIN \
    --non-interactive --agree-tos --email $EMAIL \
    --redirect
else
  echo "SSL cert already present — skipping certbot"
fi

# Start FastAPI + Postgres via docker compose
cd $OPT_DIR
docker compose pull
docker compose down --remove-orphans
docker compose up -d

echo "✅ Marketing site: https://$DOMAIN"
echo "✅ API health: https://$DOMAIN/api/health"
ENDSSH

echo "🚀 Deploy complete!"
echo "Verify: curl -s https://$DOMAIN/api/health"
