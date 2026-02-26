Rail Debugging Assistant

Overview
- FastAPI service that retrieves rail control system context and analyzes issues using an LLM.
- Modular architecture with DI for retrieval (Weaviate) and analysis (OpenAI, Quantized, DSPy).
- Advanced GenAI/LLM engineering features including PEFT fine-tuning, quantization, and systematic prompt engineering.

Run Locally
- Create `.env` with `WEAVIATE_URL`, `WEAVIATE_API_KEY`, `OPENAI_API_KEY` if using real backends.
- For quantized models: Set `ANALYZER_TYPE=quantized` and `QUANTIZED_MODEL_PATH=./models/rail-debug-model.gguf`
- For DSPy optimization: Set `ANALYZER_TYPE=dspy`
- From repo root: `pip install -r app/requirements.txt && pytest -q`
- Start dev server: `uvicorn app.main:app --reload --app-dir app`

Advanced Features
- **PEFT Fine-Tuning**: Use LoRA/QLoRA to adapt Llama 3 8B to rail debugging domain
- **Quantization**: GGUF format with hybrid CPU/GPU inference using llama-cpp-python
- **Knowledge Distillation**: Transfer knowledge from large teacher to smaller student models
- **DSPy Optimization**: Systematic prompt engineering with BootstrapFewShot
- **Prompt Governance**: Langfuse integration for versioning and A/B testing

Training Pipeline
- Fine-tune: `cd training && python fine_tune.py`
- Convert to GGUF: `python convert_to_gguf.py`
- Knowledge Distillation: `python knowledge_distillation.py`

## Docker &amp; Deployment (Sprint 015)

### Local Development
\`\`\`bash
docker compose up -d  # postgres + server
curl localhost:8000/health
python cli.py --demo  # local
python cli.py --demo --docker  # prints docker run cmd
\`\`\`

### Heroku
\`\`\`bash
heroku create rail-debug-prod
heroku addons:create heroku-postgresql:hobby-dev
heroku config:set ANTHROPIC_API_KEY=sk-... XAI_API_KEY=...
./deploy/heroku.sh
\`\`\`

### VPS (Ubuntu 22.04+ w/ Docker)
1. Edit deploy/vps.sh (VPS_HOST VPS_USER)
2. Provision postgres externally, set DATABASE_URL
3. ./deploy/vps.sh
4. ssh: sudo systemctl status rail-debug

### GitHub Actions CI
Merge PR to \`master\` → build/push multi-arch image to \`ghcr.io/PhoenixWild29/rail-debug-prod:latest\`

### Smoke Tests
\`\`\`bash
pytest tests/test_sprint015.py
\`\`\`

Legacy Docker (pre-sprint015):
- Build: \`docker build -t rail-debug .\`
- Run: \`docker run -p 8000:8000 rail-debug\`


API
- POST `/debug-rail-code` { query, few_shot_examples?, docs? }
- Returns `{ result }`. Docs are accepted but not indexed per request.
- Interactive API docs at `/docs` (Swagger UI) and `/redoc` (ReDoc).

Testing
- Tests mock external services via FastAPI dependency overrides; no real keys required.

CI
- Caches pip, runs black+mypy, executes tests across Python 3.11/3.12.

Infra
- CDK v2 Fargate service; ECR repo parameterized. See `infra/deploy.sh` for push+deploy.

Notes
- Indexing is not performed in-request. Initialize Weaviate and collection out-of-band.
- If backends are not configured, API returns 400/500; tests override dependencies.

## Learning Loop (--memory flag)

- **Default: Enabled**
- SQLite DB (`rail_debug_memory.db`) stores past analyses by normalized traceback hash/snippet.
- Pre-analysis: Injects top 3 similar past fixes into LLM prompt.
- Post-analysis: Stores new analysis (confidence, success).
- Patterns: filename:line collapsed, SHA256 hash for uniqueness.
- CLI: `python cli.py --demo --memory` (default) or `--no-memory` to disable.
