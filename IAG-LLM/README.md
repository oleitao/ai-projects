# iac-ollama-rag

Web application (Django) to:
- ingest PDFs and URLs
- create embeddings with Ollama
- answer questions using RAG with citations

## Quickstart (Docker)

1) Copy environment variables (optional):

`cp .env.example .env`

2) Start services:

`./docker-start.sh`

3) Open in your browser:

- `http://localhost:8000/ingest` (ingestion)
- `http://localhost:8000/chat` (questions)

## Important notes

- Embeddings: by default it uses `IAC_OLLAMA_EMBED_MODEL=nomic-embed-text`. If you change the model, make sure it exists in Ollama.
