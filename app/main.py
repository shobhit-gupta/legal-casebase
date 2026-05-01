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


@app.get("/cases/{case_id}")
def case_detail(case_id: int):
    _OPINION_ORDER = """
        CASE opinion_type
            WHEN '010combined'  THEN 1
            WHEN '010majority'  THEN 2
            WHEN '020plurality' THEN 3
            WHEN '030concurring-in-part-and-dissenting-in-part' THEN 4
            WHEN '040concurrence' THEN 5
            WHEN '050dissent'   THEN 6
            ELSE                     7
        END, id ASC
    """
    try:
        with get_connection() as conn:
            case_row = conn.execute(
                "SELECT * FROM cases WHERE id = ?", (case_id,)
            ).fetchone()

            if case_row is None:
                raise HTTPException(status_code=404, detail="Case not found")

            opinion_rows = conn.execute(
                f"SELECT * FROM opinions WHERE case_id = ? ORDER BY {_OPINION_ORDER}",
                (case_id,),
            ).fetchall()

            opinion_ids = [r["id"] for r in opinion_rows]
            if opinion_ids:
                placeholders = ", ".join("?" * len(opinion_ids))
                citation_rows = conn.execute(
                    f"SELECT * FROM citations WHERE from_opinion_id IN ({placeholders})"
                    " ORDER BY from_opinion_id ASC, id ASC",
                    opinion_ids,
                ).fetchall()
            else:
                citation_rows = []

    except HTTPException:
        raise
    except Exception:
        logger.exception("Case detail query failed for case_id=%s", case_id)
        raise HTTPException(status_code=500, detail="Internal server error")

    return {
        "case": dict(case_row),
        "opinions": [dict(r) for r in opinion_rows],
        "citations": [dict(r) for r in citation_rows],
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
