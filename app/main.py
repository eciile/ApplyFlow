from fastapi import FastAPI

app = FastAPI(
    title="ApplyFlow API",
    description=(
        "A personal job-search assistant that imports job postings "
        "from URLs and evaluates their relevance and risk."
        ),
        version="0.1.0",
)

@app.get("/health", tags=["System"])
def health_check() -> dict[str,str]:
    """return the current API status."""
    return {"status": "healthy"}