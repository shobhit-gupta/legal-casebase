import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from app.db import get_connection, init_db
from app.retrieval import EMBEDDING_MODEL, search_casebase

logger = logging.getLogger(__name__)

_FAISS_META_PATH = (
    Path(__file__).resolve().parents[1] / "storage" / "faiss" / "chunks_meta.json"
)


def _read_faiss_meta() -> tuple[str, int | None]:
    """
    Read embedding_model and embedding_dimension from the FAISS metadata artifact.
    Returns (embedding_model, vector_dimension).
    Falls back to (EMBEDDING_MODEL, None) if the file is missing or unreadable.
    """
    try:
        meta = json.loads(_FAISS_META_PATH.read_text(encoding="utf-8"))
        model = meta.get("embedding_model") or EMBEDDING_MODEL
        dim = meta.get("embedding_dimension")  # None if absent
        return model, dim
    except Exception:
        return EMBEDDING_MODEL, None


_STATS_CONSTANTS = {
    "court": "U.S. Supreme Court",
    "source": "CourtListener",
    "retrieval_modes": ["fts", "vector", "hybrid"],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Legal Casebase", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "Legal Casebase is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def stats():
    try:
        with get_connection() as conn:
            cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            opinions = conn.execute("SELECT COUNT(*) FROM opinions").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    except Exception:
        logger.exception("Stats query failed")
        raise HTTPException(status_code=500, detail="Internal server error")

    embedding_model, vector_dimension = _read_faiss_meta()

    return {
        "cases": cases,
        "opinions": opinions,
        "chunks_indexed": chunks,
        "embedding_model": embedding_model,
        "vector_dimension": vector_dimension,
        **_STATS_CONSTANTS,
    }


@app.get("/search")
def search(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, description="Maximum number of results"),
    mode: str = Query("hybrid", description="Retrieval mode: fts, vector, or hybrid"),
):
    try:
        results = search_casebase(query=query, limit=limit, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        if "invalid fts query syntax" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        logger.exception("Search error")
        raise HTTPException(status_code=500, detail="Internal search error")

    return {
        "query": query,
        "limit": limit,
        "mode": mode,
        "count": len(results),
        "results": results,
    }
