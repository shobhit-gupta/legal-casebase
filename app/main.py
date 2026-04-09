from fastapi import FastAPI

app = FastAPI(title="Legal Casebase")

@app.get("/health")
async def health():
    return {"status": "ok"}