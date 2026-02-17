# iac-ollama-rag

Aplicação web (Django) para:
- ingerir PDFs e URLs
- criar embeddings via Ollama
- responder a perguntas via RAG com citações

## Quickstart (Docker)

1) Copiar variáveis de ambiente (opcional):

`cp .env.example .env`

2) Subir serviços:

`./docker-start.sh`

3) Abrir no browser:

- `http://localhost:8000/ingest` (ingestão)
- `http://localhost:8000/chat` (perguntas)

## Notas importantes

- Embeddings: por omissão usa `IAC_OLLAMA_EMBED_MODEL=nomic-embed-text`. Se mudares o modelo, garante que existe no Ollama.
