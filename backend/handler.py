"""
AWS Lambda Handler for Support Agent Memory
CockroachDB × AWS Hackathon
"""

import logging
import re
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from mangum import Mangum

from config import settings
from database import get_db_manager
from bedrock_client import get_bedrock_client

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# App setup
# ============================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Support Agent with Persistent Memory - CockroachDB × AWS Hackathon"
)

# CORS — needed for local development; Lambda Function URL handles it in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static frontend files
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    logger.info(f"Mounted static files from: {FRONTEND_DIR}")

# ============================================
# Models
# ============================================

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_id: Optional[str] = Field(None)

class MemoryItem(BaseModel):
    msg_id: str
    content: str
    timestamp: str
    confidence: float = Field(..., ge=0.0, le=1.0)

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    memories_used: List[MemoryItem] = Field(default_factory=list)
    processing_time_ms: int

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    environment: str

# ============================================
# Memory helpers
# ============================================

def retrieve_memories(user_id: str, query_embedding: List[float]) -> tuple[List[MemoryItem], int]:
    """Vector search in CockroachDB using HNSW index. Returns (memories, retrieval_ms).
    Raises on hard failures so callers can surface the issue rather than silently degrading."""
    db = get_db_manager()
    similar = db.search_similar_messages(
        user_id=user_id,
        query_embedding=query_embedding,
        limit=settings.MEMORY_RETRIEVAL_LIMIT,
        similarity_threshold=settings.MEMORY_SIMILARITY_THRESHOLD
    )
    memories = [
        MemoryItem(
            msg_id=str(m['msg_id']),
            content=m['content'],
            timestamp=m['created_at'].isoformat() if hasattr(m['created_at'], 'isoformat') else str(m['created_at']),
            confidence=float(m['similarity'])
        )
        for m in similar
    ]
    return memories, 0


def generate_response(
    user_message: str,
    user_id: str,
    conv_id: str,
    memories: List[MemoryItem]
) -> str:
    """Generate Claude response with memory context. Falls back to mock on error."""
    try:
        db = get_db_manager()
        bedrock = get_bedrock_client()
        user_context = db.get_user_context(user_id)
        recent_messages = db.get_recent_messages(conv_id, limit=3)
        memory_dicts = [
            {'content': m.content, 'created_at': m.timestamp, 'similarity': m.confidence, 'role': 'user'}
            for m in memories
        ]
        return bedrock.generate_response(
            user_message=user_message,
            retrieved_memories=memory_dicts,
            user_context=user_context,
            recent_messages=recent_messages
        )
    except Exception as e:
        logger.error(f"Response generation failed: {e}", exc_info=True)
        logger.warning("Falling back to mock response")
        return _mock_response(user_message, memories)


def _mock_response(user_message: str, memories: List[MemoryItem]) -> str:
    """Graceful fallback when Bedrock is unavailable."""
    if memories:
        context = "\n".join(f"- {m.content} (on {m.timestamp[:10]})" for m in memories)
        return (
            f"I recall our previous conversations:\n{context}\n\n"
            f"How can I help you with this today?"
        )
    return "Hello! I'm your support agent. How can I help you today?"


def extract_user_facts(user_id: str, message: str):
    """Extract name/location from message and persist to user_context table."""
    db = get_db_manager()
    msg_lower = message.strip().lower()

    name_patterns = [
        r"my name is ([a-z]+)",
        r"i am ([a-z]+)",
        r"i'm ([a-z]+)",
        r"call me ([a-z]+)",
    ]
    stopwords = {"a", "an", "the", "not", "here", "back", "going", "having", "trying",
                 "from", "your", "support", "agent", "pawan", "you"}
    for pattern in name_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            candidate = m.group(1).capitalize()
            if candidate.lower() not in stopwords and len(candidate) > 1:
                try:
                    db.upsert_user_context(user_id, "user_name", candidate, confidence=0.95)
                except Exception as e:
                    logger.error(f"Failed to save name: {e}")
                break

    loc_patterns = [
        r"i(?:'m| am) from ([a-z ,]+?)(?:\.|,|$)",
        r"i live in ([a-z ,]+?)(?:\.|,|$)",
        r"based in ([a-z ,]+?)(?:\.|,|$)",
    ]
    for pattern in loc_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            location = m.group(1).strip().title()
            if len(location) > 2:
                try:
                    db.upsert_user_context(user_id, "location", location, confidence=0.95)
                except Exception as e:
                    logger.error(f"Failed to save location: {e}")
                break

# ============================================
# Routes
# ============================================

@app.get("/", response_class=FileResponse)
async def root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"status": "healthy", "version": settings.APP_VERSION})


@app.get("/health", response_model=HealthResponse)
async def health_check():
    checks = {}
    status = "healthy"
    try:
        checks['database'] = get_db_manager().health_check()
    except Exception:
        checks['database'] = False
    try:
        checks['bedrock'] = get_bedrock_client().health_check()
    except Exception:
        checks['bedrock'] = False

    if not checks.get('database'):
        status = "unhealthy"
    elif not checks.get('bedrock'):
        status = "degraded"

    logger.info(f"Health: {status} {checks}")
    return HealthResponse(
        status=status,
        timestamp=datetime.utcnow().isoformat(),
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    start = datetime.utcnow()

    try:
        logger.info(f"Chat from {request.user_id}: {request.message[:60]}...")
        db = get_db_manager()
        bedrock = get_bedrock_client()

        db.get_or_create_user(request.user_id)
        conv = db.get_or_create_conversation(request.user_id, request.conversation_id)
        conv_id = str(conv['conv_id'])

        # Generate embedding ONCE — reused for search, storage, and audit
        query_embedding = bedrock.generate_embedding(request.message)

        # Retrieve memories using the embedding
        memory_warning = None
        try:
            memories, retrieval_ms = retrieve_memories(request.user_id, query_embedding)
            logger.info(f"Retrieved {len(memories)} memories")
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}", exc_info=True)
            memories, retrieval_ms = [], 0
            memory_warning = "Memory retrieval unavailable — responding without history context"

        # Extract and persist user facts from this message
        try:
            extract_user_facts(request.user_id, request.message)
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")

        # Generate Claude response
        response_text = generate_response(
            user_message=request.message,
            user_id=request.user_id,
            conv_id=conv_id,
            memories=memories
        )

        # Store user message (reuse embedding — no extra Bedrock call)
        try:
            db.store_message(conv_id, request.user_id, "user", request.message, query_embedding)
        except Exception as e:
            logger.error(f"Failed to store user message: {e}")

        # Store assistant response (generate embedding for future retrieval)
        try:
            assistant_embedding = bedrock.generate_embedding(response_text)
            db.store_message(conv_id, request.user_id, "assistant", response_text, assistant_embedding)
        except Exception as e:
            logger.error(f"Failed to store assistant message: {e}")

        # Audit log (reuse query_embedding — no extra Bedrock call)
        try:
            if memories:
                db.log_memory_retrieval(
                    user_id=request.user_id,
                    query_embedding=query_embedding,
                    retrieved_msg_ids=[m.msg_id for m in memories],
                    retrieval_scores=[m.confidence for m in memories],
                    query_text=request.message,
                    response_text=response_text,
                    retrieval_time_ms=retrieval_ms
                )
        except Exception as e:
            logger.error(f"Failed to log memory retrieval: {e}")

        processing_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        logger.info(f"Chat complete in {processing_ms}ms (retrieval: {retrieval_ms}ms)")

        return ChatResponse(
            response=response_text,
            conversation_id=conv_id,
            memories_used=memories,
            processing_time_ms=processing_ms
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to process your request. Please try again.")


@app.get("/memory-debug/{user_id}")
async def memory_debug(
    user_id: str,
    test_query: str = "I'm having login issues",
    token: Optional[str] = None
):
    """
    Debug endpoint — inspect memory for a given user.
    Protected by a simple token check (set DEBUG_TOKEN env var).
    """
    # Auth: endpoint is blocked unless DEBUG_TOKEN env var is set AND token matches
    debug_token = os.environ.get("DEBUG_TOKEN", "")
    if not debug_token or token != debug_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Validate user_id length
    if len(user_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    try:
        bedrock = get_bedrock_client()
        db = get_db_manager()
        query_embedding = bedrock.generate_embedding(test_query)
        memories, retrieval_ms = retrieve_memories(user_id, query_embedding)
        user_context = db.get_user_context(user_id)

        return {
            "user_id": user_id,
            "test_query": test_query,
            "memories_found": len(memories),
            "retrieval_time_ms": retrieval_ms,
            "memories": [
                {"msg_id": m.msg_id, "content": m.content,
                 "timestamp": m.timestamp, "confidence": m.confidence}
                for m in memories
            ],
            "user_context": user_context,
        }
    except Exception as e:
        logger.error(f"Memory debug error: {e}", exc_info=True)
        return {"user_id": user_id, "error": "Failed to retrieve memories"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    # Never expose stack traces or internal details in production
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# ============================================
# Lambda entry point
# ============================================

handler = Mangum(app, lifespan="off")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
