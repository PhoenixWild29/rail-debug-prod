#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${HEROKU_APP_NAME:-rail-debug-prod}"

echo "=== Rail Debug Heroku Deploy ==="
echo "App: $APP_NAME"

echo "Logging into Heroku..."
heroku container:login

echo "Pushing container..."
heroku container:push web --app "$APP_NAME"
heroku container:release web --app "$APP_NAME"

echo "✅ Deployed! Live at: https://$APP_NAME.herokuapp.com/health"
echo ""
echo "Next steps:"
echo "  heroku addons:create heroku-postgresql:hobby-dev -a $APP_NAME"
echo "  heroku config:set ANTHROPIC_API_KEY=sk-... XAI_API_KEY=... -a $APP_NAME"
echo "  heroku open -a $APP_NAME