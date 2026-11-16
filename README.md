# TurnOut

TurnOut is an open research toolkit for measuring the limits of plagiarism and AI-writing detectors. It uses clean-room implementations of documented methods and real, declared research data. Turnitin is supported only through manually imported reports; this project does not automate access to commercial detectors or provide evasion tools.

## Foundation milestone

This repository currently provides the API/database foundation, a standalone importable `turnout-detect` package skeleton, and a small frontend health view. Document ingestion, detector implementations, experiments, and evaluation reports are later milestones and are not available yet.

## Requirements and setup

- Python 3.12+
- Node.js LTS (20+)

Copy `.env.example` to `.env` if you want to change defaults. Start both services with `./start.sh`; press Ctrl+C in that terminal to stop them. The database is created at `data/turnout.db`.

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API docs: http://localhost:8000/docs

For a machine with multiple Python versions, run `PYTHON=/path/to/python3.12 ./start.sh`.

## Tests

After setup, run `make test`. The backend tests cover health, schema creation, foreign keys, and uniqueness; package tests verify its standalone import.

See [SPEC.md](SPEC.md) for scope, research questions, data requirements, hard boundaries, and milestone plan. See `docs/` for project methods and dataset planning.
