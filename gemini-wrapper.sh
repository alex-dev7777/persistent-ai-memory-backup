#!/bin/bash
# Gemini CLI Memory Wrapper
# Сохраняет вопросы и ответы через Persistent AI Memory

MEMORY_API="http://localhost:8000"  # Persistent AI Memory API
GEMINI_CMD="gemini"

# Функция сохранения в память
save_to_memory() {
    local query="$1"
    local response="$2"
    
    cd /home/dev-avk/projects/persistent-ai-memory
    source venv/bin/activate
    python -c "
from ai_memory_core import PersistentAIMemorySystem
import json

memory = PersistentAIMemorySystem()
memory.create_memory(
    content='Q: $query\nA: $response',
    memory_type='conversation',
    importance_level=5,
    tags=['gemini-cli', 'conversation']
)
print('✅ Сохранено в память')
"
}

echo "🤖 Gemini CLI с памятью"
echo "Введите вопрос (или 'exit' для выхода):"

while true; do
    read -p "> " query
    
    if [[ "$query" == "exit" ]]; then
        break
    fi
    
    echo "Обрабатываю запрос..."
    response=$(echo "$query" | $GEMINI_CMD 2>/dev/null || echo "Ошибка CLI Gemini")
    
    echo "Ответ: $response"
    save_to_memory "$query" "$response"
    echo ""
done
