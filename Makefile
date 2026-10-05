# TATPAR — common tasks.  `make all` builds data, models, benchmarks and the UI, then serves on :8000.
PY ?= backend/.venv/bin/python
PIP ?= backend/.venv/bin/pip

.PHONY: setup data train bench ui test serve dev all docker deck clean

setup:            ## create the Python venv and install backend + frontend dependencies
	python3 -m venv backend/.venv
	$(PIP) install -q -e "backend[dev]"
	cd frontend && npm install --no-audit --no-fund

data:             ## download public datasets + generate the notional fleet history
	cd backend && ../$(PY) -c "from tatpar.data import cmapss, maintnet; cmapss.ensure_downloaded(); maintnet.ensure_downloaded()"
	cd backend && ../$(PY) -m tatpar.datagen.history

train:            ## train all models (engine RUL, survival, NFF, rogue, snag NLP) and the belief layer
	cd backend && ../$(PY) -m tatpar.pipelines.build_all

bench:            ## Monte-Carlo policy study, RBS, plans, federated learning; writes docs/04-evaluation.md
	cd backend && ../$(PY) -m tatpar.pipelines.bench

ui:               ## production build of the React app (served by FastAPI from frontend/dist)
	cd frontend && npm run build

test:
	cd backend && ../$(PY) -m pytest -q

serve:            ## API + built UI on http://localhost:8000
	cd backend && ../$(PY) -m uvicorn tatpar.api.main:app --host 0.0.0.0 --port 8000

dev:              ## API on :8000 and Vite dev server on :5173 (hot reload)
	(cd backend && ../$(PY) -m uvicorn tatpar.api.main:app --port 8000 --reload &) ; cd frontend && npm run dev

all: setup train bench ui serve

docker:           ## offline bundle: build once with internet, then runs air-gapped
	docker compose up --build

deck:             ## rebuild the SIH idea deck (needs: npm i pptxgenjs react-icons react react-dom sharp)
	cd docs/sih-ppt && node build_deck.js

clean:
	rm -rf backend/artifacts frontend/dist
