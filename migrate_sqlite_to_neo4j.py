#!/usr/bin/env python3
"""
Миграция данных из Persistent AI Memory SQLite в Neo4j граф
Этап 4: Прямая миграция без использования Graphiti API
"""

import sqlite3
import json
import sys
import os
import uuid
from datetime import datetime
from neo4j import GraphDatabase

# Конфигурация путей
SQLITE_PATH = "/home/dev-avk/projects/persistent-ai-memory/memory_data/ai_memories.db"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"  
NEO4J_PASSWORD = "neo4j7777"

def check_prerequisites():
    """Проверка всех компонентов перед миграцией"""
    print("🔍 Проверка предварительных условий...")
    checks = []
    
    # Проверка SQLite базы
    if os.path.exists(SQLITE_PATH):
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM curated_memories")
        count = cursor.fetchone()[0]
        conn.close()
        checks.append(f"✅ SQLite база: {count} записей найдено")
        print(f"   SQLite база: {count} записей")
    else:
        checks.append(f"❌ SQLite база не найдена: {SQLITE_PATH}")
        print(f"   ❌ SQLite база не найдена")
        return False
    
    # Проверка Neo4j подключения
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            test_val = result.single()["test"]
        driver.close()
        checks.append("✅ Neo4j подключение работает")
        print("   ✅ Neo4j подключение установлено")
    except Exception as e:
        checks.append(f"❌ Neo4j недоступен: {e}")
        print(f"   ❌ Neo4j ошибка: {e}")
        return False
    
    return True

def export_sqlite_data():
    """Экспорт данных из SQLite с полной структурой"""
    print("📤 Экспорт данных из SQLite...")
    
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT memory_id, content, memory_type, importance_level, 
               tags, timestamp_created, timestamp_updated
        FROM curated_memories 
        ORDER BY importance_level DESC, timestamp_created ASC
    """)
    
    records = []
    for row in cursor.fetchall():
        # Парсинг тегов с обработкой ошибок
        try:
            tags = json.loads(row['tags']) if row['tags'] else []
            if isinstance(tags, str):
                tags = [tags]
        except:
            tags = [row['tags']] if row['tags'] else []
        
        record = {
            'original_id': row['memory_id'],
            'content': row['content'], 
            'type': row['memory_type'] or 'general',
            'importance': row['importance_level'] or 5,
            'tags': tags,
            'created': row['timestamp_created'],
            'updated': row['timestamp_updated']
        }
        records.append(record)
    
    conn.close()
    print(f"   📊 Экспортировано {len(records)} записей")
    return records

def add_project_data():
    """Добавление данных о трех этапах проекта"""
    print("📝 Добавление данных о завершенных этапах проекта...")
    
    project_data = [
        {
            'original_id': str(uuid.uuid4()),
            'content': 'Этап 1 завершен: Установлена Neo4j версия 2025.08.0, настроена конфигурация под 16GB RAM (heap 1g, pagecache 512m), установлен пароль neo4j7777, сервис запущен на портах 7474/7687',
            'type': 'project_milestone',
            'importance': 10,
            'tags': ['neo4j', 'installation', 'stage-1', 'database'],
            'created': datetime.now().isoformat(),
            'updated': datetime.now().isoformat()
        },
        {
            'original_id': str(uuid.uuid4()),
            'content': 'Этап 2 завершен: Установлен Graphiti MCP сервер, склонирован репозиторий getzep/graphiti, установлены зависимости (graphiti-core-0.19.0, mcp-1.13.1, neo4j-5.28.2), создана конфигурация .env для интеграции с Ollama',
            'type': 'project_milestone',
            'importance': 10,
            'tags': ['graphiti', 'mcp-server', 'stage-2', 'ollama-integration'],
            'created': datetime.now().isoformat(),
            'updated': datetime.now().isoformat()
        },
        {
            'original_id': str(uuid.uuid4()),
            'content': 'Этап 3 завершен: Интеграция с Claude Desktop, настроена dual MCP architecture (persistent-ai-memory + graphiti), оба сервера получили статус running, система готова к использованию',
            'type': 'project_milestone',
            'importance': 10,
            'tags': ['claude-desktop', 'dual-mcp', 'stage-3', 'integration'],
            'created': datetime.now().isoformat(),
            'updated': datetime.now().isoformat()
        },
        {
            'original_id': str(uuid.uuid4()),
            'content': 'Техническая архитектура: Ubuntu 24.04.3, Python 3.12.3, Node.js v22.18.0, Ollama 0.3.6 с моделями qwen2.5:1.5b-instruct + nomic-embed-text, Neo4j оптимизированный под 16GB RAM, SQLite для быстрого доступа + Neo4j для семантического графа',
            'type': 'technical_architecture',
            'importance': 9,
            'tags': ['system-architecture', 'ubuntu', 'python', 'nodejs', 'ollama', 'technical-specs'],
            'created': datetime.now().isoformat(),
            'updated': datetime.now().isoformat()
        }
    ]
    
    print(f"   📊 Добавлено {len(project_data)} записей о проекте")
    return project_data

def create_graph_structure(driver, records):
    """Создание узлов и связей в Neo4j"""
    print("🔗 Создание структуры графа в Neo4j...")
    
    def create_nodes_and_relationships(tx, records):
        # Очистка существующих узлов миграции (если есть)
        print("   🧹 Очистка старых данных миграции...")
        tx.run("MATCH (n:Memory {source: 'sqlite_migration'}) DETACH DELETE n")
        tx.run("MATCH (n:ProjectData) DETACH DELETE n")
        
        nodes_created = 0
        relationships_created = 0
        
        # Создание узлов памяти
        for record in records:
            node_type = "ProjectData" if record['type'] in ['project_milestone', 'technical_architecture'] else "Memory"
            
            # Создание основного узла
            tx.run(f"""
                CREATE (m:{node_type} {{
                    content: $content,
                    type: $type,
                    importance: $importance,
                    source: 'sqlite_migration',
                    original_id: $original_id,
                    created_at: $created,
                    updated_at: $updated
                }})
            """, 
            content=record['content'],
            type=record['type'], 
            importance=record['importance'],
            original_id=record['original_id'],
            created=record['created'],
            updated=record['updated']
            )
            nodes_created += 1
            
            # Создание тегов и связей
            for tag in record['tags']:
                # Создание/обновление тега
                tx.run("""
                    MERGE (t:Tag {name: $tag_name})
                    WITH t
                    MATCH (m {original_id: $memory_id})
                    MERGE (m)-[:HAS_TAG]->(t)
                """, tag_name=tag, memory_id=record['original_id'])
                relationships_created += 1
            
            # Создание связей по типу памяти
            tx.run("""
                MERGE (type_node:MemoryType {name: $type_name})
                WITH type_node
                MATCH (m {original_id: $memory_id}) 
                MERGE (m)-[:IS_TYPE]->(type_node)
            """, type_name=record['type'], memory_id=record['original_id'])
            relationships_created += 1
        
        print(f"   📦 Создано узлов: {nodes_created}")
        print(f"   🔗 Создано связей: {relationships_created}")
        return nodes_created, relationships_created
    
    # Выполнение транзакции
    with driver.session() as session:
        nodes_count, rels_count = session.execute_write(create_nodes_and_relationships, records)
        
        # Создание индексов для производительности
        print("   📇 Создание индексов...")
        session.run("CREATE INDEX memory_content IF NOT EXISTS FOR (m:Memory) ON (m.content)")
        session.run("CREATE INDEX memory_importance IF NOT EXISTS FOR (m:Memory) ON (m.importance)")
        session.run("CREATE INDEX project_importance IF NOT EXISTS FOR (p:ProjectData) ON (p.importance)")
        session.run("CREATE INDEX tag_name IF NOT EXISTS FOR (t:Tag) ON (t.name)")
        
        return nodes_count, rels_count

def create_semantic_relationships(driver):
    """Создание семантических связей между узлами"""
    print("🧠 Создание семантических связей...")
    
    def create_relationships(tx):
        relationships = {}
        
        # Связи между записями с одинаковыми тегами
        result = tx.run("""
            MATCH (m1)-[:HAS_TAG]->(t:Tag)<-[:HAS_TAG]-(m2)
            WHERE m1.original_id <> m2.original_id
            AND NOT EXISTS((m1)-[:RELATED_BY_TAG]-(m2))
            CREATE (m1)-[:RELATED_BY_TAG {tag: t.name, type: 'shared_tag'}]->(m2)
            RETURN count(*) as created
        """)
        relationships['shared_tags'] = result.single()['created']
        
        # Связи между записями одного типа
        result = tx.run("""
            MATCH (m1)-[:IS_TYPE]->(mt:MemoryType)<-[:IS_TYPE]-(m2)
            WHERE m1.original_id <> m2.original_id
            AND NOT EXISTS((m1)-[:SAME_TYPE]-(m2))
            CREATE (m1)-[:SAME_TYPE {type: mt.name}]->(m2)
            RETURN count(*) as created
        """)
        relationships['same_types'] = result.single()['created']
        
        # Связи между важными записями
        result = tx.run("""
            MATCH (m1), (m2)
            WHERE m1.importance >= 8 AND m2.importance >= 8
            AND m1.original_id <> m2.original_id
            AND NOT EXISTS((m1)-[:HIGH_IMPORTANCE]-(m2))
            CREATE (m1)-[:HIGH_IMPORTANCE]->(m2)
            RETURN count(*) as created
        """)
        relationships['high_importance'] = result.single()['created']
        
        # Связи между этапами проекта
        result = tx.run("""
            MATCH (p1:ProjectData), (p2:ProjectData)
            WHERE p1.type = 'project_milestone' AND p2.type = 'project_milestone'
            AND p1.original_id <> p2.original_id
            AND NOT EXISTS((p1)-[:PROJECT_SEQUENCE]-(p2))
            CREATE (p1)-[:PROJECT_SEQUENCE]->(p2)
            RETURN count(*) as created
        """)
        relationships['project_sequence'] = result.single()['created']
        
        return relationships
    
    with driver.session() as session:
        relationships = session.execute_write(create_relationships)
        
        total_relationships = sum(relationships.values())
        print(f"   🔗 Всего семантических связей создано: {total_relationships}")
        for rel_type, count in relationships.items():
            if count > 0:
                print(f"      • {rel_type}: {count}")
        
        return total_relationships

def generate_final_statistics(driver):
    """Финальная статистика графа"""
    print("📊 Генерация финальной статистики...")
    
    with driver.session() as session:
        # Общее количество узлов по типам
        result = session.run("""
            MATCH (n) 
            RETURN labels(n) as labels, count(n) as count
            ORDER BY count DESC
        """)
        
        print("\n📈 СТАТИСТИКА ГРАФА:")
        total_nodes = 0
        for record in result:
            label = record['labels'][0] if record['labels'] else 'Unknown'
            count = record['count']
            total_nodes += count
            print(f"   • {label}: {count} узлов")
        
        # Общее количество связей по типам
        result = session.run("""
            MATCH ()-[r]->() 
            RETURN type(r) as rel_type, count(r) as count
            ORDER BY count DESC
        """)
        
        print("\n🔗 ТИПЫ СВЯЗЕЙ:")
        total_relationships = 0
        for record in result:
            rel_type = record['rel_type']
            count = record['count']
            total_relationships += count
            print(f"   • {rel_type}: {count}")
        
        # Топ записей по важности (только узлы с содержимым)
        result = session.run("""
            MATCH (n) 
            WHERE n.importance IS NOT NULL 
            AND n.content IS NOT NULL 
            AND n.content <> ""
            RETURN n.content as content, n.importance as importance, labels(n) as type
            ORDER BY n.importance DESC 
            LIMIT 5
        """)
        
        print("\n⭐ САМЫЕ ВАЖНЫЕ ЗАПИСИ:")
        records = list(result)
        if records:
            for i, record in enumerate(records, 1):
                content = record.get('content', 'Содержимое недоступно')
                if content and len(str(content)) > 80:
                    content = str(content)[:80] + "..."
                importance = record.get('importance', 0)
                node_type = record.get('type', ['Unknown'])[0] if record.get('type') else 'Unknown'
                print(f"   {i}. [{node_type}] Важность {importance}: {content}")
        else:
            print("   Нет записей с содержимым и важностью")
        
        return total_nodes, total_relationships

def migrate_data():
    """Основная функция миграции"""
    print("🚀 МИГРАЦИЯ SQLite → Neo4j")
    print("=" * 60)
    
    # Проверка предварительных условий
    if not check_prerequisites():
        print("\n❌ Не все предварительные условия выполнены")
        return False
    
    # Экспорт из SQLite
    sqlite_records = export_sqlite_data()
    if not sqlite_records:
        print("⚠️ Нет данных в SQLite для миграции")
        return False
    
    # Добавление данных о проекте
    project_records = add_project_data()
    
    # Объединение всех данных
    all_records = sqlite_records + project_records
    print(f"📊 Всего записей для миграции: {len(all_records)}")
    
    # Подключение к Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        # Создание структуры графа
        nodes_count, base_rels_count = create_graph_structure(driver, all_records)
        
        # Создание семантических связей
        semantic_rels_count = create_semantic_relationships(driver)
        
        # Финальная статистика
        total_nodes, total_rels = generate_final_statistics(driver)
        
        print(f"\n🎉 МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("=" * 60)
        print(f"📦 Всего узлов создано: {total_nodes}")
        print(f"🔗 Всего связей создано: {total_rels}")
        print(f"⏱️ Время выполнения: завершено")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка миграции: {e}")
        return False
    finally:
        driver.close()

def main():
    """Главная функция"""
    success = migrate_data()
    
    if success:
        print("\n🌟 СЛЕДУЮЩИЕ ШАГИ:")
        print("1. Откройте веб-интерфейс Neo4j: http://localhost:7474")
        print("2. Выполните запрос: MATCH (n) RETURN n LIMIT 20")
        print("3. Проверьте созданные связи: MATCH ()-[r]->() RETURN type(r), count(r)")
        print("4. Исследуйте граф: MATCH p=()-[]->() RETURN p LIMIT 10")
        print("\n🎯 Этап 4 завершен - граф знаний готов к использованию!")
    else:
        print("\n💡 Проверьте:")
        print("- Запущен ли Neo4j: sudo systemctl status neo4j")
        print("- Доступна ли SQLite база: ls -la /home/dev-avk/projects/persistent-ai-memory/memory_data/")
        print("- Корректный ли пароль Neo4j: neo4j7777")
        sys.exit(1)

if __name__ == "__main__":
    main()
