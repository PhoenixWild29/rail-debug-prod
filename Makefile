.PHONY: install-hooks test lint

install-hooks:
	@echo "Installing git hooks..."
	cp hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Done — pre-commit hook active."

test:
	pytest -q tests/test_sprint011.py -v

lint:
	python3 -m py_compile core/*.py utils/*.py tests/*.py
	@echo "All Python files compile OK."
