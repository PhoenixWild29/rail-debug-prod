# Rail Debug

**Quad-Tier AI Error Analysis Engine** — paste a stack trace, get an instant root cause analysis with a suggested fix.

Production: [https://debug.secureai.dev](https://debug.secureai.dev)

## What It Does

Rail Debug analyzes error tracebacks using a 4-tier AI engine that automatically escalates based on complexity:

| Tier | Engine | Latency | Use Case |
|------|--------|---------|----------|
| 1 | Regex pattern matching | < 10ms | Common errors (KeyError, ImportError, etc.) |
| 2 | xAI Grok | ~500ms | Moderate complexity |
| 3 | Claude Haiku | ~1s | Multi-file context needed |
| 4 | Claude Sonnet | ~3s | Deep architectural issues |

Supports **Python, JavaScript, Java, Go, Rust, and C++** tracebacks.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/PhoenixWild29/rail-debug-prod.git
cd rail-debug-prod
cp .env.example .env   # Add your API keys

# Start with Docker
docker compose up -d
curl http://localhost:8000/api/health
```

### CLI

```bash
pip install -r requirements.txt
python cli.py --demo          # Analyze a sample error
python cli.py --serve         # Start the API server
```

## API

Base URL: `https://debug.secureai.dev/api`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/analyze` | Analyze a single traceback |
| `POST` | `/analyze/chain` | Analyze chained/nested exceptions |
| `POST` | `/analyze/batch` | Batch analyze multiple errors |
| `POST` | `/project/scan` | Scan a project directory for issues |

### Example

```bash
curl -X POST https://debug.secureai.dev/api/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rd_your_key_here" \
  -d '{"traceback": "Traceback (most recent call last):\n  File \"app.py\", line 42\n    value = config[\"db_url\"]\nKeyError: \"db_url\""}'
```

### Authentication

- **Anonymous**: Tier 1 (regex) only, rate limited
- **API Key** (`X-API-Key` header): Access based on subscription tier
- **JWT** (`Authorization: Bearer` header): Full account access

## Project Structure

```
core/              # Analysis engine — analyzer, LLM clients, auth, GitHub integration
routes/            # FastAPI route handlers — auth, billing, dashboard, webhooks, teams
services/          # Email notifications, retrieval service
web/               # Static frontend — landing page, dashboard, analysis UI
migrations/        # PostgreSQL schema migrations
tests/             # Test suite (Python 3.11/3.12)
deploy/            # Nginx configs, systemd service, deployment scripts
sdk/               # Python SDK
vscode-extension/  # VS Code extension
server.py          # FastAPI application entry point
cli.py             # Command-line interface
```

## Development

```bash
# Set up virtual environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest black mypy

# Run tests
pytest tests/ -v

# Format code
black .

# Start dev server with hot reload
uvicorn server:app --reload --port 8000
```

## Deployment

### Production (DigitalOcean Droplet)

Merging to `master` triggers auto-deploy via GitHub Actions:
1. SSH into the droplet
2. Pull latest code
3. Rebuild Docker containers (if backend changed)
4. Copy static files (if frontend changed)
5. Run database migrations
6. Health check verification
7. Telegram notification

### Required GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `DROPLET_IP` | Production server IP |
| `DROPLET_SSH_KEY` | SSH private key for deployment |
| `DB_PASSWORD` | PostgreSQL password |
| `TELEGRAM_BOT_TOKEN` | Deploy notification bot |
| `TELEGRAM_CHAT_ID` | Deploy notification channel |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn
- **Database**: PostgreSQL 16
- **AI**: xAI Grok, Anthropic Claude (Haiku + Sonnet)
- **Auth**: JWT + API keys, bcrypt password hashing
- **Payments**: Stripe (subscriptions + usage billing)
- **CI/CD**: GitHub Actions, auto-deploy to DigitalOcean
- **Frontend**: Vanilla HTML/CSS/JS with Tailwind CSS

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style, and PR guidelines.

## License

[MIT](LICENSE)
