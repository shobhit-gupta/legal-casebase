from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db


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
