#!/usr/bin/env python3
"""
CLI интерфейс для Persistent AI Memory
Позволяет CLI Gemini сохранять данные через командную строку
"""

import sys
import asyncio
import json
from ai_memory_core import PersistentAIMemorySystem

async def main():
    if len(sys.argv) < 2:
        print("Использование: python memory-cli.py <action> [data]")
        print("Действия: save <text>, search <query>, list")
        sys.exit(1)
    
    action = sys.argv[1]
    data = sys.argv[2] if len(sys.argv) > 2 else ""
    
    memory = PersistentAIMemorySystem()
    
    if action == "save":
        result = await memory.create_memory(
            content=data,
            memory_type="gemini-conversation",
            importance_level=5,
            tags=["gemini-cli", "external"]
        )
        print(f"Сохранено: {result}")
    
    elif action == "search":
        results = await memory.search_memories(query=data, limit=5)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    
    elif action == "list":
        # Простой поиск всех записей - НЕ используем data параметр
        results = await memory.search_memories(query="", limit=10)
        if 'results' in results and results['results']:
            for r in results['results']:
                print(f"- {r.get('content', '')}")
        else:
            print("Записи не найдены или поиск недоступен")

if __name__ == "__main__":
    asyncio.run(main())
