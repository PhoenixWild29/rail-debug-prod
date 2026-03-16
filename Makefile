.PHONY: install-hooks test lint format dev

install-hooks:
	@echo "Installing git hooks..."
	cp hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Done — pre-commit hook active."

test:
	pytest tests/test_sprint011.py tests/test_sprint012.py tests/test_sprint013.py -v --tb=short

lint:
	python3 -m py_compile core/*.py routes/*.py services/*.py utils/*.py server.py
	@echo "All Python files compile OK."

format:
	black .

dev:
	uvicorn server:app --reload --host 0.0.0.0 --port 8000
