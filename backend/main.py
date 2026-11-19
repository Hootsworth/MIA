# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.documents import router as documents_router
from backend.api.detectors import router as detectors_router
from backend.api.experiments import router as experiments_router
from backend.api.analysis import router as analysis_router
from backend.api.turnitin import router as turnitin_router
from backend.api.reports import router as reports_router
from backend.api.detector_suite import router as detector_suite_router
from backend.core.database import init_db
from backend.services.experiment_runner import recover_interrupted_experiments, schedule_queued_experiments


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    recover_interrupted_experiments()
    schedule_queued_experiments()
    yield


app = FastAPI(title="MIA Lab API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(documents_router, prefix="/api")
app.include_router(detectors_router, prefix="/api")
app.include_router(experiments_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(turnitin_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(detector_suite_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "mia-lab-api"}
