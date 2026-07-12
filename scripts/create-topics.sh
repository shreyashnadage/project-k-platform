#!/usr/bin/env bash
# Create Redpanda topics for the OCEN platform
# Usage: make topics (or ./scripts/create-topics.sh)

set -euo pipefail

REDPANDA_BROKER="localhost:19092"

echo "Creating Redpanda topics..."

# Trade events — the main event-sourced stream
# Partitioned by entity key for ordering guarantees
docker exec ocen-redpanda rpk topic create \
  ocen.trade-events.v1 \
  --brokers "$REDPANDA_BROKER" \
  --partitions 6 \
  --config retention.ms=-1 \
  --config cleanup.policy=delete \
  --config compression.type=zstd \
  2>/dev/null || echo "  ocen.trade-events.v1 already exists"

# Dead letter queue for failed event processing
docker exec ocen-redpanda rpk topic create \
  ocen.trade-events.v1.dlq \
  --brokers "$REDPANDA_BROKER" \
  --partitions 1 \
  --config retention.ms=604800000 \
  2>/dev/null || echo "  ocen.trade-events.v1.dlq already exists"

# Outbox relay topic (for CDC from Postgres outbox table)
docker exec ocen-redpanda rpk topic create \
  ocen.outbox-relay.v1 \
  --brokers "$REDPANDA_BROKER" \
  --partitions 3 \
  2>/dev/null || echo "  ocen.outbox-relay.v1 already exists"

echo "Done. Topics:"
docker exec ocen-redpanda rpk topic list --brokers "$REDPANDA_BROKER"
