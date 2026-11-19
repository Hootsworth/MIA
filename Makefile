.PHONY: test backend frontend detector-app detector-models detector-models-all

test:
	.venv/bin/python -m pytest backend/tests packages/mia-detect/tests

backend:
	.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

detector-app:
	cd detector-app && npm run dev -- --port 3001

detector-models:
	HF_HUB_DISABLE_XET=1 .venv/bin/python scripts/download_detector_models.py

detector-models-all:
	HF_HUB_DISABLE_XET=1 .venv/bin/python scripts/download_detector_models.py --include-modernbert
