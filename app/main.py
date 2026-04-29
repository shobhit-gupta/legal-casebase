import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.db import init_db
from app.retrieval import search_casebase

logger = logging.getLogger(__name__)


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
