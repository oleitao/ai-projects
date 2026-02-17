#!/usr/bin/env sh
set -eu

PORT="${IAC_OLLAMA_PORT:-11434}"
if [ -z "${OLLAMA_BASE_URL:-}" ] && [ -z "${IAC_OLLAMA_PORT:-}" ] && command -v docker >/dev/null 2>&1; then
  MAPPED="$(
    docker port iac-ollama 11434/tcp 2>/dev/null \
      | head -n 1 \
      | sed -E 's/.*:([0-9]+)$/\1/' \
      | tr -d '\r' \
      || true
  )"
  case "${MAPPED:-}" in
    ''|*[!0-9]*)
      : ;;
    *)
    PORT="$MAPPED"
      ;;
  esac
fi
BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:${PORT}}"
BASE_URL="${BASE_URL%/}"
MODEL="${1:-${IAC_OLLAMA_MODEL:-llama3.1}}"
PROMPT="${2:-Qual a capital de Portugal?}"

if command -v python >/dev/null 2>&1; then
  TAGS_JSON="$(curl -fsS "$BASE_URL/api/tags" 2>/dev/null || true)"
  if [ -n "$TAGS_JSON" ]; then
    INSTALLED="$(
      printf '%s' "$TAGS_JSON" | python - "$MODEL" <<'PY'
import json, sys

requested = sys.argv[1]
requested_base = requested.split(":", 1)[0]

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

names = set()
for m in (data.get("models") or []):
    if isinstance(m, dict):
        n = m.get("name") or m.get("model")
        if isinstance(n, str) and n:
            names.add(n)

ok = any(n == requested or n == requested_base or n.startswith(requested_base + ":") for n in names)
sys.stdout.write("1" if ok else "0")
PY
    )"
    if [ "${INSTALLED:-}" = "0" ]; then
      {
        echo "Model '$MODEL' is not installed in Ollama at $BASE_URL."
        echo "Pull it with:"
        echo "  docker exec iac-ollama ollama pull $MODEL"
        echo "  # or"
        echo "  docker compose -f docker-compose.yml run --rm ollama-pull"
      } >&2
      exit 1
    fi
  fi
fi

PAYLOAD="$(
  python - "$MODEL" "$PROMPT" <<'PY'
import json, sys

model = sys.argv[1]
prompt = sys.argv[2]
print(
    json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
)
PY
)"

curl -sS "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
