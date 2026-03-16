# Contributing to Rail Debug

Thank you for your interest in contributing to Rail Debug! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.11 or 3.12
- Docker and Docker Compose
- PostgreSQL 16 (provided via Docker)

### Local Setup

```bash
# Clone the repo
git clone https://github.com/PhoenixWild29/rail-debug-prod.git
cd rail-debug-prod

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest black mypy

# Copy environment config
cp .env.example .env
# Edit .env with your API keys

# Start the database
docker compose up -d db

# Run the server
uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Verify it works
curl http://localhost:8000/api/health
```

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

- We use [Black](https://github.com/psf/black) for Python formatting (line length: 100)
- Run `black .` before committing
- Type hints are encouraged but not enforced via CI yet

## Project Structure

```
rail-debug-prod/
├── core/              # Analysis engine (analyzer, LLM, auth, GitHub client)
├── routes/            # FastAPI route handlers (auth, billing, webhooks, etc.)
├── services/          # Service layer (email, retrieval)
├── web/               # Static frontend (HTML, CSS, JS)
├── migrations/        # PostgreSQL migration scripts
├── tests/             # Test suite
├── deploy/            # Deployment configs (nginx, systemd)
├── sdk/               # Python SDK for Rail Debug API
├── vscode-extension/  # VS Code extension (TypeScript)
├── server.py          # FastAPI application entry point
├── cli.py             # CLI interface
└── docker-compose.yml # Local development stack
```

## Making Changes

### Branch Naming

- Features: `feature/description` or `sprint-RAIL-NNN-description`
- Bug fixes: `fix/description`
- Hotfixes: `hotfix/description`

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scope): add new feature
fix(scope): fix a bug
docs: update documentation
ci: update CI/CD workflows
refactor: code improvements without behavior change
test: add or update tests
```

### Pull Request Process

1. Create a feature branch from `master`
2. Make your changes with clear, focused commits
3. Ensure tests pass: `pytest tests/ -v`
4. Format code: `black .`
5. Push and open a PR against `master`
6. Fill in the PR template with a summary and test plan

### What We Look For in PRs

- Clear description of what changed and why
- Tests for new functionality
- No hardcoded secrets or credentials
- Follows existing code patterns

## Architecture Overview

Rail Debug uses a **Quad-Tier AI Analysis Engine**:

| Tier | Engine | Speed | Cost |
|------|--------|-------|------|
| 1 | Regex pattern matching | < 10ms | Free |
| 2 | xAI Grok | ~500ms | Low |
| 3 | Claude Haiku | ~1s | Medium |
| 4 | Claude Sonnet | ~3s | High |

The system automatically escalates through tiers based on error complexity, gated by user subscription tier.

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include reproduction steps for bugs
- Tag issues with appropriate labels

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
