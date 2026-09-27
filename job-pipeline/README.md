# Job Pipeline

A modular job‑search pipeline built with **Python** and **FastAPI**.

## Architecture

```
Ingestion → Parsing → Matching → Outreach
```

Each stage lives in its own package under `src/`:

- **Ingestion** – Pull raw job postings from external sources.
- **Parsing** – Normalise and enrich the raw data.
- **Matching** – Find the best candidate for each job.
- **Outreach** – Submit applications / send outreach messages.

## Quick Start

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the API
uvicorn app.main:app --reload
```

## Running Tests

```bash
pytest -q
```

## Contributing

Feel free to open issues or submit pull requests.
