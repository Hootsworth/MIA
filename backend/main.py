from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.documents import router as documents_router
from backend.api.detectors import router as detectors_router
from backend.core.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MIA Lab API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(documents_router, prefix="/api")
app.include_router(detectors_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "mia-lab-api"}
