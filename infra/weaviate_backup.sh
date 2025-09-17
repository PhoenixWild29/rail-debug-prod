#!/bin/bash
# Backup Weaviate data
# Assumes Weaviate is running in Docker or accessible

WEAVIATE_URL=${WEAVIATE_URL:-http://localhost:8080}
BACKUP_DIR=${BACKUP_DIR:-./backups}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Use Weaviate's backup API if available (v1.19+)
curl -X POST "$WEAVIATE_URL/v1/backups" \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"backup_$TIMESTAMP\", \"include\": [\"RailDoc\"]}" \
  -o $BACKUP_DIR/backup_$TIMESTAMP.json

echo "Backup created: $BACKUP_DIR/backup_$TIMESTAMP.json"