#!/usr/bin/env bash
set -euo pipefail

VPS_HOST=&quot;${VPS_HOST:-138.197.126.127}&quot;
VPS_USER=&quot;${VPS_USER:-ubuntu}&quot;
SERVICE_NAME=&quot;rail-debug&quot;
OPT_DIR=&quot;/opt/$SERVICE_NAME&quot;
DOMAIN=&quot;debug.secureai.dev&quot;
EMAIL=&quot;hello@secureai.dev&quot;

echo &quot;=== Rail Debug VPS Deploy (Sprint 016) ===&quot;
echo &quot;Droplet: $VPS_USER@$VPS_HOST ($DOMAIN)&quot;

# Copy files
echo &quot;📦 Copying code and config...&quot;
rsync -avz --delete --exclude='venv' --exclude='.git' --exclude='*.db' . &quot;$VPS_USER@$VPS_HOST:$OPT_DIR/&quot;

scp &quot;deploy/nginx.conf&quot; &quot;$VPS_USER@$VPS_HOST:$OPT_DIR/deploy/&quot;

ssh &quot;$VPS_USER@$VPS_HOST&quot; &lt;&lt; 'EOF'
set -euo pipefail

OPT_DIR=&quot;$OPT_DIR&quot;
DOMAIN=&quot;$DOMAIN&quot;
EMAIL=&quot;$EMAIL&quot;

cd \$OPT_DIR

# Nginx + Certbot + static site
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

sudo mkdir -p /var/www/rail-debug
sudo cp -r web/* /var/www/rail-debug/
sudo chown -R www-data:www-data /var/www/rail-debug

sudo cp deploy/nginx.conf /etc/nginx/sites-available/rail-debug
sudo ln -sf /etc/nginx/sites-available/rail-debug /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t &amp;&amp; sudo systemctl reload nginx || sudo nginx -t

sudo certbot --nginx -d \$DOMAIN \\
  --non-interactive --agree-tos --email \$EMAIL \\
  --redirect

# Docker Compose for API + DB
docker compose pull
docker compose down
docker compose up -d

# Service (legacy)
sudo systemctl daemon-reload
sudo systemctl restart rail-debug.service || true
sudo systemctl enable rail-debug.service || true

echo &quot;✅ Marketing site: https://\$DOMAIN&quot;
echo &quot;✅ API: https://\$DOMAIN/api/health&quot;
EOF

echo &quot;🚀 Deploy complete!&quot;
echo &quot;Check: ssh $VPS_USER@$VPS_HOST 'docker compose ps &amp;&amp; sudo systemctl status nginx'&quot;