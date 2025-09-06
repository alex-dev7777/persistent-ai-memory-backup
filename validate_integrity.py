#!/usr/bin/env python3
"""
Валидация целостности данных между SQLite и Neo4j
Еженедельная проверка консистентности и автовосстановление
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from neo4j import GraphDatabase
import hashlib

# Конфигурация
SQLITE_PATH = "/home/dev-avk/projects/persistent-ai-memory/memory_data/ai_memories.db"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j7777"
SYNC_STATE_FILE = "/home/dev-avk/projects/persistent-ai-memory/.sync_state.json"
LOG_FILE = "/home/dev-avk/projects/persistent-ai-memory/logs/validation_weekly.log"
MIGRATION_SCRIPT = "/home/dev-avk/projects/persistent-ai-memory/migrate_sqlite_to_neo4j.py"

class IntegrityValidator:
    def __init__(self):
        self.ensure_log_directory()
        self.discrepancies = []
        
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
    
    def get_sqlite_stats(self):
        """Получение статистики из SQLite"""
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Общее количество записей
            cursor.execute("SELECT COUNT(*) as count FROM curated_memories")
            total_records = cursor.fetchone()['count']
            
            # Записи по типам важности
            cursor.execute("""
                SELECT importance_level, COUNT(*) as count 
                FROM curated_memories 
                WHERE importance_level IS NOT NULL
                GROUP BY importance_level 
                ORDER BY importance_level DESC
            """)
            importance_stats = dict(cursor.fetchall())
            
            # Последние записи для контрольной суммы
            cursor.execute("""
                SELECT memory_id, content, importance_level, timestamp_created
                FROM curated_memories 
                ORDER BY timestamp_created DESC 
                LIMIT 10
            """)
            recent_records = [dict(row) for row in cursor.fetchall()]
            
            # Создание контрольной суммы
            content_hash = self.calculate_content_hash(recent_records)
            
            conn.close()
            
            return {
                'total_records': total_records,
                'importance_stats': importance_stats,
                'content_hash': content_hash,
                'recent_records': recent_records
            }
            
        except Exception as e:
            self.log(f"Ошибка получения статистики SQLite: {e}", "ERROR")
            return None
    
    def get_neo4j_stats(self):
        """Получение статистики из Neo4j"""
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            
            with driver.session() as session:
                # Общее количество узлов Memory
                result = session.run("MATCH (m:Memory) RETURN count(m) as count")
                memory_nodes = result.single()['count']
                
                # Статистика узлов по типам
                result = session.run("""
                    MATCH (n) 
                    RETURN labels(n) as node_type, count(n) as count
                    ORDER BY count DESC
                """)
                node_stats = {}
                for record in result:
                    if record['node_type']:
                        node_stats[record['node_type'][0]] = record['count']
                
                # Статистика связей
                result = session.run("""
                    MATCH ()-[r]->() 
                    RETURN type(r) as rel_type, count(r) as count
                    ORDER BY count DESC
                """)
                relationship_stats = {}
                for record in result:
                    relationship_stats[record['rel_type']] = record['count']
                
                # Проверка целостности связей
                result = session.run("""
                    MATCH (m:Memory) 
                    OPTIONAL MATCH (m)-[:HAS_TAG]->(t:Tag)
                    OPTIONAL MATCH (m)-[:IS_TYPE]->(mt:MemoryType)
                    WITH m, count(DISTINCT t) as tag_count, count(DISTINCT mt) as type_count
                    RETURN m.original_id as id,
                           tag_count,
                           type_count,
                           m.importance as importance
                    ORDER BY importance DESC
                    LIMIT 10
                """)
                integrity_sample = [dict(record) for record in result]
                
                # Поиск orphaned узлов
                result = session.run("""
                    MATCH (n) 
                    WHERE NOT (n)--() 
                    RETURN labels(n) as type, count(n) as count
                """)
                orphaned_nodes = {}
                for record in result:
                    if record['type']:
                        orphaned_nodes[record['type'][0]] = record['count']
                
            driver.close()
            
            return {
                'memory_nodes': memory_nodes,
                'node_stats': node_stats,
                'relationship_stats': relationship_stats,
                'integrity_sample': integrity_sample,
                'orphaned_nodes': orphaned_nodes
            }
            
        except Exception as e:
            self.log(f"Ошибка получения статистики Neo4j: {e}", "ERROR")
            return None
    
    def calculate_content_hash(self, records):
        """Вычисление контрольной суммы содержимого"""
        content_string = ""
        for record in sorted(records, key=lambda x: x.get('memory_id', '')):
            content_string += f"{record.get('memory_id', '')}{record.get('content', '')}"
        
        return hashlib.md5(content_string.encode('utf-8')).hexdigest()[:16]
    
    def validate_record_counts(self, sqlite_stats, neo4j_stats):
        """Проверка соответствия количества записей"""
        sqlite_count = sqlite_stats['total_records']
        neo4j_count = neo4j_stats['memory_nodes']
        
        if sqlite_count != neo4j_count:
            discrepancy = f"Несоответствие количества записей: SQLite={sqlite_count}, Neo4j={neo4j_count}"
            self.discrepancies.append({
                'type': 'COUNT_MISMATCH',
                'severity': 'HIGH',
                'description': discrepancy,
                'sqlite_count': sqlite_count,
                'neo4j_count': neo4j_count
            })
            self.log(discrepancy, "WARN")
            return False
        
        self.log(f"Количество записей корректно: {sqlite_count}")
        return True
    
    def validate_graph_integrity(self, neo4j_stats):
        """Проверка целостности графа"""
        issues_found = False
        
        # Проверка orphaned узлов
        if neo4j_stats['orphaned_nodes']:
            for node_type, count in neo4j_stats['orphaned_nodes'].items():
                if count > 0:
                    discrepancy = f"Найдены изолированные узлы: {node_type} = {count}"
                    self.discrepancies.append({
                        'type': 'ORPHANED_NODES',
                        'severity': 'MEDIUM',
                        'description': discrepancy,
                        'node_type': node_type,
                        'count': count
                    })
                    self.log(discrepancy, "WARN")
                    issues_found = True
        
        # Проверка соотношения узлов и связей
        memory_nodes = neo4j_stats.get('memory_nodes', 0)
        total_relationships = sum(neo4j_stats.get('relationship_stats', {}).values())
        
        if memory_nodes > 0:
            avg_rels_per_node = total_relationships / memory_nodes
            if avg_rels_per_node < 2:  # Каждый узел должен иметь минимум 2 связи
                discrepancy = f"Низкая связность графа: {avg_rels_per_node:.1f} связей на узел"
                self.discrepancies.append({
                    'type': 'LOW_CONNECTIVITY',
                    'severity': 'LOW',
                    'description': discrepancy,
                    'avg_relationships': avg_rels_per_node
                })
                self.log(discrepancy, "WARN")
                issues_found = True
        
        if not issues_found:
            self.log("Целостность графа в норме")
        
        return not issues_found
    
    def validate_recent_changes(self, sqlite_stats):
        """Проверка последних изменений"""
        state_file_exists = os.path.exists(SYNC_STATE_FILE)
        
        if not state_file_exists:
            self.log("Файл состояния синхронизации не найден", "WARN")
            return False
        
        try:
            with open(SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
                sync_state = json.load(f)
            
            last_sync = sync_state.get('last_sync_timestamp')
            if last_sync:
                last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                hours_since_sync = (datetime.now(timezone.utc) - last_sync_dt).total_seconds() / 3600
                
                if hours_since_sync > 48:  # 2 дня без синхронизации
                    discrepancy = f"Синхронизация не выполнялась {hours_since_sync:.1f} часов"
                    self.discrepancies.append({
                        'type': 'STALE_SYNC',
                        'severity': 'MEDIUM',
                        'description': discrepancy,
                        'hours_since_sync': hours_since_sync
                    })
                    self.log(discrepancy, "WARN")
                    return False
            
            self.log(f"Последняя синхронизация: {last_sync}")
            return True
            
        except Exception as e:
            self.log(f"Ошибка проверки состояния синхронизации: {e}", "ERROR")
            return False
    
    def run_full_migration_recovery(self):
        """Запуск полной миграции для восстановления"""
        self.log("Запуск полной миграции для восстановления данных", "INFO")
        
        try:
            import subprocess
            result = subprocess.run([
                'bash', '-c', 
                f'cd /home/dev-avk/projects/persistent-ai-memory && source venv/bin/activate && python {MIGRATION_SCRIPT}'
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                self.log("Полная миграция завершена успешно", "INFO")
                return True
            else:
                self.log(f"Ошибка полной миграции: {result.stderr}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Критическая ошибка при восстановлении: {e}", "ERROR")
            return False
    
    def update_sync_state_validation(self):
        """Обновление времени последней валидации"""
        try:
            if os.path.exists(SYNC_STATE_FILE):
                with open(SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
                    sync_state = json.load(f)
            else:
                sync_state = {}
            
            sync_state['last_full_validation'] = datetime.now(timezone.utc).isoformat()
            sync_state['validation_discrepancies'] = len(self.discrepancies)
            
            with open(SYNC_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(sync_state, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.log(f"Ошибка обновления состояния валидации: {e}", "ERROR")
    
    def run_validation(self):
        """Основная функция валидации"""
        start_time = datetime.now()
        self.log("Запуск еженедельной валидации целостности")
        
        # Получение статистики из обеих систем
        sqlite_stats = self.get_sqlite_stats()
        neo4j_stats = self.get_neo4j_stats()
        
        if not sqlite_stats or not neo4j_stats:
            self.log("Не удалось получить статистику из систем", "ERROR")
            return False
        
        # Проверки целостности
        count_valid = self.validate_record_counts(sqlite_stats, neo4j_stats)
        graph_valid = self.validate_graph_integrity(neo4j_stats)
        sync_valid = self.validate_recent_changes(sqlite_stats)
        
        # Логирование статистики
        self.log(f"SQLite записей: {sqlite_stats['total_records']}")
        self.log(f"Neo4j узлов: {neo4j_stats['memory_nodes']}")
        self.log(f"Связей в графе: {sum(neo4j_stats['relationship_stats'].values())}")
        
        # Определение необходимости восстановления
        critical_issues = len([d for d in self.discrepancies if d['severity'] == 'HIGH'])
        
        recovery_needed = critical_issues > 0 or not count_valid
        
        if recovery_needed:
            self.log(f"Обнаружено критических проблем: {critical_issues}", "WARN")
            self.log("Запуск автоматического восстановления", "INFO")
            recovery_success = self.run_full_migration_recovery()
            
            if recovery_success:
                self.log("Система восстановлена успешно", "INFO")
            else:
                self.log("Восстановление не удалось - требуется ручное вмешательство", "ERROR")
                return False
        
        # Обновление состояния валидации
        self.update_sync_state_validation()
        
        # Финальная статистика
        duration = (datetime.now() - start_time).total_seconds()
        self.log(f"Валидация завершена за {duration:.1f}с")
        self.log(f"Найдено проблем: {len(self.discrepancies)} (критических: {critical_issues})")
        
        return True

def main():
    validator = IntegrityValidator()
    success = validator.run_validation()
    
    if success:
        print("Валидация целостности завершена успешно")
        sys.exit(0)
    else:
        print("Критические ошибки при валидации")
        sys.exit(1)

if __name__ == "__main__":
    main()
