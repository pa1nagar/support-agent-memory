"""
Database operations for Support Agent Memory
CockroachDB with pgvector distributed HNSW indexing
"""

import logging
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import time

from config import settings

logger = logging.getLogger(__name__)


def normalize_user_id(user_id: str) -> str:
    """
    Normalize any user_id string to a valid UUID string.
    If it's already a valid UUID, return it as-is.
    Otherwise generate a deterministic UUID v5 from the string.
    """
    try:
        return str(uuid.UUID(user_id))
    except ValueError:
        generated = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_id))
        logger.debug(f"Converted user_id '{user_id}' to UUID: {generated}")
        return generated


class DatabaseManager:
    """Manages CockroachDB connections with pooling and vector search operations"""

    def __init__(self):
        self.connection_string = settings.COCKROACHDB_URL
        self._pool: Optional[SimpleConnectionPool] = None

    def _get_pool(self) -> SimpleConnectionPool:
        """Lazy-initialize connection pool"""
        if self._pool is None:
            self._pool = SimpleConnectionPool(
                minconn=1,
                maxconn=settings.DB_POOL_SIZE,
                dsn=self.connection_string,
                cursor_factory=RealDictCursor
            )
            logger.info("Database connection pool initialized")
        return self._pool

    @contextmanager
    def get_connection(self):
        """Context manager — borrows a connection from the pool and returns it after use"""
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {str(e)}", exc_info=True)
            raise
        finally:
            pool.putconn(conn)

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    def get_or_create_user(self, user_id: str, email: str = None, name: str = None) -> Dict[str, Any]:
        uid = normalize_user_id(user_id)
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE user_id = %s::uuid", (uid,))
                user = cur.fetchone()
                if user:
                    return dict(user)
                email = email or f"{uid}@example.com"
                name = name or f"User {uid[:8]}"
                cur.execute(
                    """
                    INSERT INTO users (user_id, email, name)
                    VALUES (%s::uuid, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET updated_at = now()
                    RETURNING *
                    """,
                    (uid, email, name)
                )
                user = cur.fetchone()
                logger.info(f"Created new user: {uid}")
                return dict(user)

    # ------------------------------------------------------------------
    # Conversation operations
    # ------------------------------------------------------------------

    def get_or_create_conversation(self, user_id: str, conv_id: Optional[str] = None) -> Dict[str, Any]:
        uid = normalize_user_id(user_id)
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if conv_id:
                    cur.execute(
                        "SELECT * FROM conversations WHERE conv_id = %s::uuid AND user_id = %s::uuid",
                        (conv_id, uid)
                    )
                    conv = cur.fetchone()
                    if conv:
                        return dict(conv)
                cur.execute(
                    """
                    INSERT INTO conversations (user_id, title, status)
                    VALUES (%s::uuid, %s, %s)
                    RETURNING *
                    """,
                    (uid, "New conversation", "active")
                )
                conv = cur.fetchone()
                logger.info(f"Created new conversation: {conv['conv_id']}")
                return dict(conv)

    # ------------------------------------------------------------------
    # Message operations
    # ------------------------------------------------------------------

    def store_message(
        self,
        conv_id: str,
        user_id: str,
        role: str,
        content: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        uid = normalize_user_id(user_id)
        embedding_str = f"[{','.join(map(str, embedding))}]" if embedding else None
        metadata_str = json.dumps(metadata or {})

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO messages (conv_id, user_id, role, content, embedding, metadata)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s::vector, %s::jsonb)
                    RETURNING msg_id
                    """,
                    (conv_id, uid, role, content, embedding_str, metadata_str)
                )
                msg_id = cur.fetchone()['msg_id']
                logger.info(f"Stored message: {msg_id} (role: {role})")
                return str(msg_id)

    def get_recent_messages(self, conv_id: str, limit: int = 3) -> List[Dict[str, Any]]:
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
                return [dict(row) for row in reversed(results)]

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def search_similar_messages(
        self,
        user_id: str,
        query_embedding: List[float],
        limit: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Semantic search using CockroachDB distributed HNSW vector index"""
        uid = normalize_user_id(user_id)
        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        start = time.time()

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        msg_id,
                        content,
                        role,
                        created_at,
                        (1 - (embedding <=> %s::vector))::float AS similarity
                    FROM messages
                    WHERE user_id = %s::uuid
                      AND embedding IS NOT NULL
                      AND (1 - (embedding <=> %s::vector)) > %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding_str, uid, embedding_str, similarity_threshold, embedding_str, limit)
                )
                results = cur.fetchall()

        elapsed = int((time.time() - start) * 1000)
        logger.info(f"Vector search found {len(results)} messages in {elapsed}ms for user {user_id}")
        return [dict(row) for row in results]

    # ------------------------------------------------------------------
    # User context
    # ------------------------------------------------------------------

    def get_user_context(self, user_id: str) -> Dict[str, Any]:
        uid = normalize_user_id(user_id)
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT context_key, context_value, confidence, updated_at
                    FROM user_context
                    WHERE user_id = %s::uuid
                    ORDER BY confidence DESC
                    """,
                    (uid,)
                )
                return {
                    row['context_key']: {
                        'value': row['context_value'],
                        'confidence': float(row['confidence']),
                        'updated_at': row['updated_at'].isoformat()
                    }
                    for row in cur.fetchall()
                }

    def upsert_user_context(self, user_id: str, key: str, value: str, confidence: float = 1.0):
        """Insert or update a structured user fact"""
        uid = normalize_user_id(user_id)
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_context (user_id, context_key, context_value, confidence)
                    VALUES (%s::uuid, %s, %s, %s)
                    ON CONFLICT (user_id, context_key)
                    DO UPDATE SET
                        context_value = EXCLUDED.context_value,
                        confidence = EXCLUDED.confidence,
                        updated_at = now()
                    """,
                    (uid, key, value, confidence)
                )
                logger.info(f"Upserted user context: {key}={value} for {uid}")

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

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
        uid = normalize_user_id(user_id)
        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_audit (
                        user_id, query_embedding, retrieved_msg_ids,
                        retrieval_scores, query_text, response_text, retrieval_time_ms
                    )
                    VALUES (%s::uuid, %s::vector, %s, %s, %s, %s, %s)
                    """,
                    (uid, embedding_str, retrieved_msg_ids, retrieval_scores,
                     query_text, response_text, retrieval_time_ms)
                )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False


# Singleton
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
