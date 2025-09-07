#!/usr/bin/env python3
"""
Persistent AI Memory System Core
SQLite-based memory system for AI conversations and knowledge storage
"""

import sqlite3
import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import os

class PersistentAIMemorySystem:
    """Core memory system for persistent AI knowledge storage"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "memory_data", "ai_memories.db")
        
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure database and tables exist"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create memories table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS curated_memories (
                memory_id TEXT PRIMARY KEY,
                timestamp_created TEXT NOT NULL,
                timestamp_updated TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                importance_level INTEGER DEFAULT 5,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            )
        """)
        
        conn.commit()
        conn.close()
    
    async def create_memory(self, content: str, memory_type: str = "general", 
                          importance_level: int = 5, tags: List[str] = None, 
                          metadata: Dict[str, Any] = None) -> str:
        """Create a new memory entry"""
        if tags is None:
            tags = []
        if metadata is None:
            metadata = {}
            
        memory_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO curated_memories 
            (memory_id, timestamp_created, timestamp_updated, memory_type, 
             content, importance_level, tags, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory_id, timestamp, timestamp, memory_type,
            content, importance_level, json.dumps(tags), json.dumps(metadata)
        ))
        
        conn.commit()
        conn.close()
        
        return memory_id
    
    async def search_memories(self, query: str, memory_type: str = None, 
                            limit: int = 10) -> List[Dict[str, Any]]:
        """Search memories by content"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        sql = """
            SELECT memory_id, timestamp_created, memory_type, content, 
                   importance_level, tags, metadata
            FROM curated_memories 
            WHERE content LIKE ?
        """
        params = [f"%{query}%"]
        
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)
            
        sql += " ORDER BY importance_level DESC, timestamp_created DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.close()
        
        memories = []
        for row in results:
            memories.append({
                "memory_id": row[0],
                "timestamp_created": row[1],
                "memory_type": row[2],
                "content": row[3],
                "importance_level": row[4],
                "tags": json.loads(row[5]),
                "metadata": json.loads(row[6])
            })
        
        return memories
    
    async def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get specific memory by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT memory_id, timestamp_created, timestamp_updated, memory_type,
                   content, importance_level, tags, metadata
            FROM curated_memories WHERE memory_id = ?
        """, (memory_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "memory_id": result[0],
                "timestamp_created": result[1],
                "timestamp_updated": result[2],
                "memory_type": result[3],
                "content": result[4],
                "importance_level": result[5],
                "tags": json.loads(result[6]),
                "metadata": json.loads(result[7])
            }
        return None
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get system health status"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count total memories
            cursor.execute("SELECT COUNT(*) FROM curated_memories")
            total_memories = cursor.fetchone()[0]
            
            # Get database size
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            db_size_mb = (page_count * page_size) / (1024 * 1024)
            
            conn.close()
            
            return {
                "status": "healthy",
                "total_memories": total_memories,
                "database_size_mb": round(db_size_mb, 2),
                "database_path": self.db_path,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def delete_memory(self, memory_id: str) -> bool:
        """Delete memory by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM curated_memories WHERE memory_id = ?", (memory_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    async def list_memories(self, memory_type: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent memories"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        sql = """
            SELECT memory_id, timestamp_created, memory_type, content,
                   importance_level, tags
            FROM curated_memories
        """
        params = []
        
        if memory_type:
            sql += " WHERE memory_type = ?"
            params.append(memory_type)
            
        sql += " ORDER BY timestamp_created DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.close()
        
        memories = []
        for row in results:
            memories.append({
                "memory_id": row[0],
                "timestamp_created": row[1],
                "memory_type": row[2],
                "content": row[3][:200] + "..." if len(row[3]) > 200 else row[3],
                "importance_level": row[4],
                "tags": json.loads(row[5])
            })
        
        return memories
