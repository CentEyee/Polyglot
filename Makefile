.PHONY: dev test api web example

dev:
	pip install -e ".[dev]"

test:
	pytest -q

api:
	uvicorn polyglot.api.main:app --reload --port 8000

web:
	cd frontend && npm install && npm run dev

example:
	@echo "Local demo repo: $(PWD)/examples/c-satadd"
	@echo "Instruction: Migrate this C library to safe idiomatic Rust"
