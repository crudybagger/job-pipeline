from fastapi import FastAPI
from src.ingestion.ingest import fetch_job_listings

app = FastAPI(title="Job Pipeline API")


@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(source_url: str):
    """Simple endpoint to trigger ingestion.

    Args:
        source_url (str): URL of the job source.

    Returns:
        dict: Number of listings retrieved.
    """
    listings = fetch_job_listings(source_url)
    return {"listings_received": len(listings)}
