#!/usr/bin/env python3
"""
Инкрементальная синхронизация SQLite → Neo4j
Обновляет только новые/измененные записи с момента последней синхронизации
"""

import sqlite3
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from neo4j import GraphDatabase

# Конфигурация
SQLITE_PATH = "/home/dev-avk/projects/persistent-ai-memory/memory_data/ai_memories.db"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j7777"
SYNC_STATE_FILE = "/home/dev-avk/projects/persistent-ai-memory/.sync_state.json"
LOG_FILE = "/home/dev-avk/projects/persistent-ai-memory/logs/sync_daily.log"

class IncrementalSync:
    def __init__(self):
        self.sync_state = self.load_sync_state()
        self.ensure_log_directory()
        
    def ensure_log_directory(self):
        """Создание директории для логов"""
        log_dir = os.path.dirname(LOG_FILE)
        os.makedirs(log_dir, exist_ok=True)
    
    def log(self, message, level="INFO"):
        """Логирование с timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} [{level}] {message}"
        print(log_entry)
        
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    
    def load_sync_state(self):
        """Загрузка состояния последней синхронизации"""
        if os.path.exists(SYNC_STATE_FILE):
            try:
                with open(SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.log(f"Ошибка загрузки состояния: {e}", "WARN")
        
        return {
            'last_sync_timestamp': None,
            'last_record_count': 0,
            'synced_record_ids': [],
            'last_full_validation': None
        }
    
    def save_sync_state(self, new_records_processed=0):
        """Сохранение состояния синхронизации"""
        self.sync_state['last_sync_timestamp'] = datetime.now(timezone.utc).isoformat()
        self.sync_state['last_record_count'] += new_records_processed
        
        try:
            with open(SYNC_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.sync_state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Ошибка сохранения состояния: {e}", "ERROR")
    
    def get_new_records_from_sqlite(self):
        """Получение новых записей из SQLite с момента последней синхронизации"""
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Определение условия для новых записей
            if self.sync_state['last_sync_timestamp']:
                where_clause = "WHERE timestamp_created > ? OR timestamp_updated > ?"
                params = (self.sync_state['last_sync_timestamp'], self.sync_state['last_sync_timestamp'])
                self.log(f"Поиск записей после {self.sync_state['last_sync_timestamp']}")
            else:
                where_clause = ""
                params = ()
                self.log("Первая синхронизация - обработка всех записей")
            
            cursor.execute(f"""
                SELECT memory_id, content, memory_type, importance_level, 
                       tags, timestamp_created, timestamp_updated
                FROM curated_memories 
                {where_clause}
                ORDER BY timestamp_created ASC
            """, params)
            
            records = []
            for row in cursor.fetchall():
                # Парсинг тегов
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
            return records
            
        except Exception as e:
            self.log(f"Ошибка чтения SQLite: {e}", "ERROR")
            return []
    
    def sync_records_to_neo4j(self, records):
        """Синхронизация новых записей в Neo4j"""
        if not records:
            return 0, 0
        
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            
            with driver.session() as session:
                nodes_created = 0
                relationships_created = 0
                
                for record in records:
                    # Проверка существования записи
                    existing = session.run("""
                        MATCH (n) WHERE n.original_id = $original_id RETURN n
                    """, original_id=record['original_id']).single()
                    
                    if existing:
                        # Обновление существующей записи
                        session.run("""
                            MATCH (n {original_id: $original_id})
                            SET n.content = $content,
                                n.importance = $importance,
                                n.updated_at = $updated
                        """, **record)
                        self.log(f"Обновлена запись: {record['original_id']}")
                    else:
                        # Создание нового узла
                        session.run("""
                            CREATE (m:Memory {
                                content: $content,
                                type: $type,
                                importance: $importance,
                                source: 'incremental_sync',
                                original_id: $original_id,
                                created_at: $created,
                                updated_at: $updated
                            })
                        """, **record)
                        nodes_created += 1
                        self.log(f"Создана запись: {record['original_id']}")
                    
                    # Создание тегов и связей
                    for tag in record['tags']:
                        session.run("""
                            MERGE (t:Tag {name: $tag_name})
                            WITH t
                            MATCH (m {original_id: $memory_id})
                            MERGE (m)-[:HAS_TAG]->(t)
                        """, tag_name=tag, memory_id=record['original_id'])
                        relationships_created += 1
                    
                    # Связь с типом памяти
                    session.run("""
                        MERGE (type_node:MemoryType {name: $type_name})
                        WITH type_node
                        MATCH (m {original_id: $memory_id})
                        MERGE (m)-[:IS_TYPE]->(type_node)
                    """, type_name=record['type'], memory_id=record['original_id'])
                    relationships_created += 1
                
                # Создание семантических связей для новых записей
                if nodes_created > 0:
                    # Связи по общим тегам
                    result = session.run("""
                        MATCH (m1:Memory)-[:HAS_TAG]->(t:Tag)<-[:HAS_TAG]-(m2:Memory)
                        WHERE m1.original_id <> m2.original_id
                        AND NOT EXISTS((m1)-[:RELATED_BY_TAG]-(m2))
                        AND m1.source = 'incremental_sync'
                        CREATE (m1)-[:RELATED_BY_TAG {tag: t.name}]->(m2)
                        RETURN count(*) as created
                    """)
                    semantic_rels = result.single()['created']
                    relationships_created += semantic_rels
                
            driver.close()
            return nodes_created, relationships_created
            
        except Exception as e:
            self.log(f"Ошибка синхронизации с Neo4j: {e}", "ERROR")
            return 0, 0
    
    def check_prerequisites(self):
        """Проверка доступности компонентов"""
        # Проверка SQLite
        if not os.path.exists(SQLITE_PATH):
            self.log(f"SQLite база не найдена: {SQLITE_PATH}", "ERROR")
            return False
        
        # Проверка Neo4j
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                session.run("RETURN 1").single()
            driver.close()
        except Exception as e:
            self.log(f"Neo4j недоступен: {e}", "ERROR")
            return False
        
        return True
    
    def run_incremental_sync(self):
        """Основная функция инкрементальной синхронизации"""
        start_time = datetime.now()
        self.log("Запуск инкрементальной синхронизации")
        
        # Проверка предварительных условий
        if not self.check_prerequisites():
            self.log("Синхронизация прервана из-за ошибок", "ERROR")
            return False
        
        # Получение новых записей
        new_records = self.get_new_records_from_sqlite()
        
        if not new_records:
            self.log("Новых записей не обнаружено")
            return True
        
        self.log(f"Найдено новых записей: {len(new_records)}")
        
        # Синхронизация с Neo4j
        nodes_created, rels_created = self.sync_records_to_neo4j(new_records)
        
        # Сохранение состояния
        self.save_sync_state(len(new_records))
        
        # Финальная статистика
        duration = (datetime.now() - start_time).total_seconds()
        self.log(f"Синхронизация завершена за {duration:.1f}с")
        self.log(f"Создано узлов: {nodes_created}, связей: {rels_created}")
        
        return True

def main():
    sync = IncrementalSync()
    success = sync.run_incremental_sync()
    
    if success:
        print("Инкрементальная синхронизация выполнена успешно")
        sys.exit(0)
    else:
        print("Ошибка инкрементальной синхронизации")
        sys.exit(1)

if __name__ == "__main__":
    main()
