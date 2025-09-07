#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$HOME/projects/persistent-ai-memory"
DB_FILE="memory_data/ai_memories.db"
DUMP_FILE="backup.sql"
LOG_FILE="$PROJECT_DIR/backup.log"

cd "$PROJECT_DIR"

# Переключаемся на ветку бэкапов
git checkout backup

echo "[$(date -Is)] Starting backup..." | tee -a "$LOG_FILE"

# 1) Создаём дамп (полный)
sqlite3 "$DB_FILE" .dump > "$DUMP_FILE".tmp
mv "$DUMP_FILE".tmp "$DUMP_FILE"

# 2) Коммитим изменения, если есть
git add "$DUMP_FILE" || true
if ! git diff --cached --quiet; then
  git commit -m "backup: $(date -Is)"
  # 3) Пушим (если есть origin)
  if git remote | grep -q .; then
    git push
  fi
  echo "[$(date -Is)] Commit & push done." | tee -a "$LOG_FILE"
else
  echo "[$(date -Is)] No changes to backup." | tee -a "$LOG_FILE"
fi

echo "[$(date -Is)] Backup finished." | tee -a "$LOG_FILE"
