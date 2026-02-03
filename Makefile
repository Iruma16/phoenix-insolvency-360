.PHONY: install-dev run-api run-ui init-db demo-data fmt fmt-check lint deadcode typecheck test test-all check

install-dev:
	python3 -m pip install --upgrade pip
	pip install -r requirements-dev.txt
	pip install -e .

init-db:
	python3 -m app.core.init_db

run-api:
	python3 -m uvicorn app.main:app --reload --port 8000

run-ui:
	streamlit run app/ui/streamlit_mvp.py

demo-data:
	@echo "Copiando datos demo a ./data/demo_ready/ ..."
	@mkdir -p data/demo_ready
	@cp -R data/sample/* data/demo_ready/ || true
	@echo "OK. Puedes subir estos ficheros desde Streamlit:"
	@echo "  data/demo_ready/"

fmt:
	python3 -m ruff format .

fmt-check:
	python3 -m ruff format --check .

lint:
	python3 -m ruff check .

deadcode:
	@echo "🔎 Vulture (reporte de código potencialmente no usado; no bloqueante por defecto)"
	@python3 -m vulture app scripts vulture_whitelist.py \
		--min-confidence 80 \
		--exclude migrations,legacy,runtime,clients_data,tests \
		|| true

typecheck:
	python3 -m mypy app || true

test:
	pytest -m "smoke and not llm and not slow"

test-all:
	pytest -m "not llm and not slow"

check: fmt-check lint deadcode test

