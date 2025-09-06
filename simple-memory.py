#!/usr/bin/env python3
"""
Простой CLI для Persistent AI Memory - только SQLite, без зависимостей
Работает с системным Python без venv
"""

import sqlite3
import sys
import json
import uuid
from datetime import datetime

DB_PATH = "/home/dev-avk/projects/persistent-ai-memory/memory_data/ai_memories.db"

def save_memory(content, memory_type="manual", importance=5):
    """Сохранить запись в базу"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    memory_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    tags = json.dumps(["cli", "manual"])
    
    cursor.execute("""
        INSERT INTO curated_memories 
        (memory_id, timestamp_created, timestamp_updated, memory_type, content, importance_level, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (memory_id, timestamp, timestamp, memory_type, content, importance, tags))
    
    conn.commit()
    conn.close()
    print(f"Сохранено: {memory_id}")

def search_memory(query):
    """Поиск в базе"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT memory_id, memory_type, importance_level, content, tags 
        FROM curated_memories 
        WHERE content LIKE ? OR tags LIKE ?
        ORDER BY importance_level DESC
    """, (f"%{query}%", f"%{query}%"))
    
    results = cursor.fetchall()
    conn.close()
    
    if results:
        for row in results:
            print(f"ID: {row[0][:8]}... | Тип: {row[1]} | Важность: {row[2]}")
            print(f"Содержание: {row[3]}")
            print(f"Теги: {row[4]}")
            print("-" * 50)
    else:
        print("Записи не найдены")

def list_memory():
    """Показать все записи"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT memory_id, memory_type, importance_level, content 
        FROM curated_memories 
        ORDER BY timestamp_created DESC 
        LIMIT 10
    """)
    
    results = cursor.fetchall()
    conn.close()
    
    if results:
        print(f"Найдено {len(results)} записей:")
        for i, row in enumerate(results, 1):
            print(f"{i}. [{row[1]}] (важность: {row[2]}) {row[3][:60]}...")
    else:
        print("База данных пуста")

def save_from_file(filepath):
    """Читает контент из файла и сохраняет его в базу."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        save_memory(content)
    except FileNotFoundError:
        print(f"Ошибка: Файл не найден по пути {filepath}")
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}")

def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 simple-memory.py save 'текст записи'")
        print("  python3 simple-memory.py save_from_file '/путь/к/файлу.txt'")
        print("  python3 simple-memory.py search 'запрос'") 
        print("  python3 simple-memory.py list")
        sys.exit(1)
    
    action = sys.argv[1]
    
    try:
        if action == "save" and len(sys.argv) > 2:
            save_memory(sys.argv[2])
        elif action == "save_from_file" and len(sys.argv) > 2:
            save_from_file(sys.argv[2])
        elif action == "search" and len(sys.argv) > 2:
            search_memory(sys.argv[2])
        elif action == "list":
            list_memory()
        else:
            print("Неверная команда или недостающие аргументы")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
