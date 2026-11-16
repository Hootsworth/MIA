.PHONY: test backend frontend

test:
	.venv/bin/python -m pytest backend/tests packages/turnout-detect/tests

backend:
	.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev
