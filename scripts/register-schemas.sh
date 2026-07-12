#!/usr/bin/env bash
# Register JSON schemas with Redpanda Schema Registry
set -euo pipefail

REGISTRY_URL="${SCHEMA_REGISTRY_URL:-http://localhost:18081}"

echo "Registering TradeEvent schema..."
SCHEMA=$(cat schemas/trade-event.schema.json | python -c "import sys,json; print(json.dumps(json.dumps(json.load(sys.stdin))))")

curl -s -X POST "${REGISTRY_URL}/subjects/ocen.trade-events.v1-value/versions" \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d "{\"schemaType\": \"JSON\", \"schema\": ${SCHEMA}}" | python -m json.tool

echo ""
echo "Schema registration complete."
echo "Listing subjects:"
curl -s "${REGISTRY_URL}/subjects" | python -m json.tool
