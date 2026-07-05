# Prosper Challenge — run everything from the repo root.
# Dependencies are managed with uv (https://docs.astral.sh/uv/).

PROJECT := backend

.PHONY: help install install-nltk run dev-frontend test test-fast test-llm clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install dependencies (from uv.lock)
	uv sync --directory $(PROJECT)

install-nltk: ## Download NLTK punkt_tab data into backend/.nltk_data
	mkdir -p $(PROJECT)/.nltk_data
	NLTK_DATA=$(PROJECT)/.nltk_data uv run --directory $(PROJECT) python -c "import nltk; nltk.download('punkt_tab', download_dir='$(PROJECT)/.nltk_data', quiet=True)"

run: ## Run the voice agent (then open http://localhost:7860/client)
	uv run --directory $(PROJECT) python bot.py

dev-frontend: ## Run the React UI dev server (http://localhost:5173)
	npm run dev --prefix frontend

test: ## Run the full backend test suite (unit tests + LLM evals, needs OPENAI_API_KEY)
	uv run --directory $(PROJECT) pytest

test-fast: ## Run only the fast, deterministic unit tests (no API calls)
	uv run --directory $(PROJECT) pytest -m "not llm"

test-llm: ## Run only the LLM eval tests (tool-calling + Copilot correctness)
	uv run --directory $(PROJECT) pytest -m llm

clean: ## Remove the venv and Python caches
	rm -rf $(PROJECT)/.venv
	find $(PROJECT) -type d -name __pycache__ -prune -exec rm -rf {} +
