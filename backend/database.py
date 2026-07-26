"""
Database operations for Support Agent Memory
Handles CockroachDB connections and vector search
"""

import logging
import json
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import time

from config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages CockroachDB connections and operations"""
    
    def __init__(self):
        self.connection_string = settings.COCKROACHDB_URL
        self._connection = None
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = psycopg2.connect(
                self.connection_string,
                cursor_factory=RealDictCursor
            )
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {str(e)}", exc_info=True)
            raise
        finally:
            if conn:
                conn.close()
    
    def get_or_create_user(self, user_id: str, email: str = None, name: str = None) -> Dict[str, Any]:
        """Get existing user or create new one"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Try to get existing user
                cur.execute(
                    "SELECT * FROM users WHERE user_id = %s",
                    (user_id,)
                )
                user = cur.fetchone()
                
                if user:
                    return dict(user)
                
                # Create new user
                email = email or f"{user_id}@example.com"
                name = name or f"User {user_id[:8]}"
                
                cur.execute(
                    """
                    INSERT INTO users (user_id, email, name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET updated_at = now()
                    RETURNING *
                    """,
                    (user_id, email, name)
                )
                user = cur.fetchone()
                logger.info(f"Created new user: {user_id}")
                return dict(user)
    
    def get_or_create_conversation(
        self, 
        user_id: str, 
        conv_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing conversation or create new one"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if conv_id:
                    # Try to get existing conversation
                    cur.execute(
                        "SELECT * FROM conversations WHERE conv_id = %s AND user_id = %s",
                        (conv_id, user_id)
                    )
                    conv = cur.fetchone()
                    if conv:
                        return dict(conv)
                
                # Create new conversation
                cur.execute(
                    """
                    INSERT INTO conversations (user_id, title, status)
                    VALUES (%s, %s, %s)
                    RETURNING *
                    """,
                    (user_id, "New conversation", "active")
                )
                conv = cur.fetchone()
                logger.info(f"Created new conversation: {conv['conv_id']}")
                return dict(conv)
    
    def store_message(
        self,
        conv_id: str,
        user_id: str,
        role: str,
        content: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Store a message in the database"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Convert embedding to pgvector format
                embedding_str = None
                if embedding:
                    embedding_str = f"[{','.join(map(str, embedding))}]"
                
                # Convert metadata dict to JSON string - psycopg2 needs string for JSONB cast
                metadata_str = json.dumps(metadata if metadata is not None else {})
                
                cur.execute(
                    """
                    INSERT INTO messages (conv_id, user_id, role, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)
                    RETURNING msg_id
                    """,
                    (conv_id, user_id, role, content, embedding_str, metadata_str)
                )
                msg_id = cur.fetchone()['msg_id']
                logger.info(f"Stored message: {msg_id} (role: {role})")
                return str(msg_id)
    
    def search_similar_messages(
        self,
        user_id: str,
        query_embedding: List[float],
        limit: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar messages using vector similarity
        Uses CockroachDB's HNSW index for fast semantic search
        """
        start_time = time.time()
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Convert embedding to pgvector format
                embedding_str = f"[{','.join(map(str, query_embedding))}]"
                
                # Vector similarity search with cosine distance
                # <=> is the cosine distance operator in pgvector
                # (1 - distance) gives similarity score
                cur.execute(
                    """
                    SELECT 
                        msg_id,
                        content,
                        role,
                        created_at,
                        (1 - (embedding <=> %s::vector))::float AS similarity
                    FROM messages
                    WHERE user_id = %s
                      AND embedding IS NOT NULL
                      AND (1 - (embedding <=> %s::vector)) > %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding_str, user_id, embedding_str, similarity_threshold, embedding_str, limit)
                )
                
                results = cur.fetchall()
                
                retrieval_time = int((time.time() - start_time) * 1000)
                logger.info(
                    f"Vector search found {len(results)} similar messages "
                    f"in {retrieval_time}ms for user {user_id}"
                )
                
                return [dict(row) for row in results]
    
    def get_recent_messages(
        self,
        conv_id: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Get most recent messages from a conversation"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT msg_id, role, content, created_at, metadata
                    FROM messages
                    WHERE conv_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (conv_id, limit)
                )
                results = cur.fetchall()
                # Reverse to chronological order
                return [dict(row) for row in reversed(results)]
    
    def get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Get consolidated context about a user"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT context_key, context_value, confidence, updated_at
                    FROM user_context
                    WHERE user_id = %s
                    ORDER BY confidence DESC
                    """,
                    (user_id,)
                )
                results = cur.fetchall()
                
                # Convert to dict
                context = {}
                for row in results:
                    context[row['context_key']] = {
                        'value': row['context_value'],
                        'confidence': float(row['confidence']),
                        'updated_at': row['updated_at'].isoformat()
                    }
                
                return context
    
    def log_memory_retrieval(
        self,
        user_id: str,
        query_embedding: List[float],
        retrieved_msg_ids: List[str],
        retrieval_scores: List[float],
        query_text: str,
        response_text: str,
        retrieval_time_ms: int
    ):
        """Log memory retrieval for audit and observability"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                embedding_str = f"[{','.join(map(str, query_embedding))}]"
                
                cur.execute(
                    """
                    INSERT INTO memory_audit (
                        user_id, query_embedding, retrieved_msg_ids, 
                        retrieval_scores, query_text, response_text, retrieval_time_ms
                    )
                    VALUES (%s, %s::vector, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        embedding_str,
                        retrieved_msg_ids,
                        retrieval_scores,
                        query_text,
                        response_text,
                        retrieval_time_ms
                    )
                )
                logger.debug(f"Logged memory retrieval for user {user_id}")
    
    def health_check(self) -> bool:
        """Check if database is accessible"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False


# Singleton instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or create database manager singleton"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
