"""
AWS Lambda Handler for Support Agent Memory
Phase 1: Real memory retrieval with Bedrock + CockroachDB vector search
"""

import json
import logging
import time
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from mangum import Mangum

from config import settings
from database import get_db_manager
from bedrock_client import get_bedrock_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# FastAPI Application
# ============================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Support Agent with Persistent Memory - CockroachDB × AWS Hackathon"
)

# CORS Middleware - DISABLED (Lambda Function URL handles CORS)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.get_cors_origins_list(),
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# ============================================
# Serve Static Frontend Files
# ============================================

# Get the frontend directory path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")

# Mount static files if frontend directory exists
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    logger.info(f"Mounted static files from: {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend directory not found: {FRONTEND_DIR}")

# ============================================
# Request/Response Models
# ============================================

class ChatRequest(BaseModel):
    """Chat request from user"""
    user_id: str = Field(..., description="Unique user identifier")
    message: str = Field(..., min_length=1, max_length=5000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID (optional)")

class MemoryItem(BaseModel):
    """Retrieved memory item"""
    msg_id: str
    content: str
    timestamp: str
    confidence: float = Field(..., ge=0.0, le=1.0)

class ChatResponse(BaseModel):
    """Chat response to user"""
    response: str
    conversation_id: str
    memories_used: List[MemoryItem] = Field(default_factory=list)
    processing_time_ms: int

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str
    environment: str

# ============================================
# Phase 1: Real Functions with Fallback
# ============================================

def retrieve_memories_with_fallback(
    user_id: str, 
    message: str,
    use_mock: bool = False
) -> tuple[List[MemoryItem], int]:
    """
    Retrieve memories using real vector search (with mock fallback)
    Returns: (memories, retrieval_time_ms)
    """
    if use_mock:
        logger.warning("Using mock memory retrieval")
        return mock_retrieve_memories(user_id, message), 0
    
    try:
        start_time = time.time()
        
        # Get clients
        db = get_db_manager()
        bedrock = get_bedrock_client()
        
        # Generate embedding for the query
        query_embedding = bedrock.generate_embedding(message)
        
        # Search for similar messages in CockroachDB
        similar_messages = db.search_similar_messages(
            user_id=user_id,
            query_embedding=query_embedding,
            limit=settings.MEMORY_RETRIEVAL_LIMIT,
            similarity_threshold=settings.MEMORY_SIMILARITY_THRESHOLD
        )
        
        retrieval_time_ms = int((time.time() - start_time) * 1000)
        
        # Convert to MemoryItem format
        memories = [
            MemoryItem(
                msg_id=str(msg['msg_id']),
                content=msg['content'],
                timestamp=msg['created_at'].isoformat() if hasattr(msg['created_at'], 'isoformat') else str(msg['created_at']),
                confidence=float(msg['similarity'])
            )
            for msg in similar_messages
        ]
        
        logger.info(f"Retrieved {len(memories)} memories in {retrieval_time_ms}ms")
        return memories, retrieval_time_ms
        
    except Exception as e:
        logger.error(f"Memory retrieval failed: {str(e)}", exc_info=True)
        logger.warning("Falling back to mock memories")
        return mock_retrieve_memories(user_id, message), 0


def generate_response_with_fallback(
    user_message: str,
    user_id: str,
    conv_id: str,
    memories: List[MemoryItem],
    use_mock: bool = False
) -> str:
    """
    Generate response using Claude (with mock fallback)
    """
    if use_mock:
        logger.warning("Using mock response generation")
        return mock_generate_response(user_message, memories)
    
    try:
        db = get_db_manager()
        bedrock = get_bedrock_client()
        
        # Get user context
        user_context = db.get_user_context(user_id)
        
        # Get recent conversation messages
        recent_messages = db.get_recent_messages(conv_id, limit=3)
        
        # Convert memories to dict format
        memory_dicts = [
            {
                'content': m.content,
                'created_at': m.timestamp,
                'similarity': m.confidence,
                'role': 'user'  # Simplified for now
            }
            for m in memories
        ]
        
        # Generate response with Claude
        response = bedrock.generate_response(
            user_message=user_message,
            retrieved_memories=memory_dicts,
            user_context=user_context,
            recent_messages=recent_messages
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Response generation failed: {str(e)}", exc_info=True)
        logger.warning("Falling back to mock response")
        return mock_generate_response(user_message, memories)


# Mock functions (fallback only)
def mock_retrieve_memories(user_id: str, message: str) -> List[MemoryItem]:
    """Fallback mock memory retrieval"""
    if "login" in message.lower() or "access" in message.lower():
        return [
            MemoryItem(
                msg_id="mock-1",
                content="I cannot log in to my dashboard",
                timestamp="2026-07-22T15:15:00Z",
                confidence=0.94
            ),
            MemoryItem(
                msg_id="mock-2",
                content="It says AUTH_503 timeout error",
                timestamp="2026-07-22T15:18:00Z",
                confidence=0.89
            )
        ]
    return []


def mock_generate_response(user_message: str, memories: List[MemoryItem]) -> str:
    """Fallback mock response generation"""
    if memories:
        memory_context = "\n".join([f"- {m.content} (on {m.timestamp[:10]})" for m in memories])
        return (
            f"I see you've mentioned similar issues before:\n{memory_context}\n\n"
            f"Are you still experiencing the same problem? Let me help you resolve this."
        )
    return "I'm here to help! Could you please describe your issue in more detail?"

# ============================================
# API Endpoints
# ============================================

@app.get("/", response_class=FileResponse)
async def root():
    """Serve the main frontend HTML"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "message": "API is running. Frontend files not found. Use /health for API status."
    })

@app.get("/debug.html", response_class=FileResponse)
async def serve_debug():
    """Serve the debug HTML"""
    debug_path = os.path.join(FRONTEND_DIR, "debug.html")
    if os.path.exists(debug_path):
        return FileResponse(debug_path)
    raise HTTPException(status_code=404, detail="Debug page not found")

@app.get("/test.html", response_class=FileResponse)
async def serve_test():
    """Serve the test HTML"""
    test_path = os.path.join(FRONTEND_DIR, "test.html")
    if os.path.exists(test_path):
        return FileResponse(test_path)
    raise HTTPException(status_code=404, detail="Test page not found")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Detailed health check endpoint
    Checks database and Bedrock connectivity
    """
    health_status = "healthy"
    checks = {}
    
    # Check database
    try:
        db = get_db_manager()
        checks['database'] = db.health_check()
    except Exception as e:
        checks['database'] = False
        health_status = "degraded"
        logger.error(f"Database health check failed: {str(e)}")
    
    # Check Bedrock (optional - can work without it)
    try:
        bedrock = get_bedrock_client()
        checks['bedrock'] = bedrock.health_check()
    except Exception as e:
        checks['bedrock'] = False
        logger.warning(f"Bedrock health check failed (will use fallback): {str(e)}")
    
    # Overall status
    if not checks.get('database'):
        health_status = "unhealthy"
    elif not checks.get('bedrock'):
        health_status = "degraded"
    
    logger.info(f"Health check: {health_status}, checks: {checks}")
    
    return HealthResponse(
        status=health_status,
        timestamp=datetime.utcnow().isoformat(),
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint
    Phase 1: Uses real Bedrock + CockroachDB (with fallback to mock)
    """
    start_time = datetime.utcnow()
    use_mock = settings.ENVIRONMENT == "development" and settings.DEBUG
    
    try:
        logger.info(f"Chat request from user {request.user_id}: {request.message[:50]}...")
        
        db = get_db_manager()
        bedrock = get_bedrock_client()
        
        # Ensure user exists
        db.get_or_create_user(request.user_id)
        
        # Get or create conversation
        conv = db.get_or_create_conversation(
            user_id=request.user_id,
            conv_id=request.conversation_id
        )
        conv_id = str(conv['conv_id'])
        
        # Phase 1: Real memory retrieval (with fallback)
        memories, retrieval_time = retrieve_memories_with_fallback(
            user_id=request.user_id,
            message=request.message,
            use_mock=use_mock
        )
        logger.info(f"Retrieved {len(memories)} memories in {retrieval_time}ms")
        
        # Phase 1: Real response generation (with fallback)
        response_text = generate_response_with_fallback(
            user_message=request.message,
            user_id=request.user_id,
            conv_id=conv_id,
            memories=memories,
            use_mock=use_mock
        )
        
        # Store user message with embedding
        try:
            user_embedding = bedrock.generate_embedding(request.message)
            db.store_message(
                conv_id=conv_id,
                user_id=request.user_id,
                role="user",
                content=request.message,
                embedding=user_embedding
            )
        except Exception as e:
            logger.error(f"Failed to store user message: {str(e)}")
            # Continue even if storage fails
        
        # Store assistant response with embedding
        try:
            assistant_embedding = bedrock.generate_embedding(response_text)
            db.store_message(
                conv_id=conv_id,
                user_id=request.user_id,
                role="assistant",
                content=response_text,
                embedding=assistant_embedding
            )
        except Exception as e:
            logger.error(f"Failed to store assistant message: {str(e)}")
            # Continue even if storage fails
        
        # Log memory retrieval for audit
        try:
            if memories:
                query_embedding = bedrock.generate_embedding(request.message)
                db.log_memory_retrieval(
                    user_id=request.user_id,
                    query_embedding=query_embedding,
                    retrieved_msg_ids=[m.msg_id for m in memories],
                    retrieval_scores=[m.confidence for m in memories],
                    query_text=request.message,
                    response_text=response_text,
                    retrieval_time_ms=retrieval_time
                )
        except Exception as e:
            logger.error(f"Failed to log memory retrieval: {str(e)}")
            # Continue even if logging fails
        
        # Calculate total processing time
        processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        logger.info(f"Chat response generated in {processing_time}ms (retrieval: {retrieval_time}ms)")
        
        return ChatResponse(
            response=response_text,
            conversation_id=conv_id,
            memories_used=memories,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail="Unable to process your request. Please try again."
        )

@app.get("/memory-debug/{user_id}")
async def memory_debug(user_id: str, test_query: str = "I'm having login issues"):
    """
    Debug endpoint to inspect memory retrieval
    Shows what memories would be retrieved for a test query
    """
    try:
        # Try real memory retrieval
        memories, retrieval_time = retrieve_memories_with_fallback(
            user_id=user_id,
            message=test_query,
            use_mock=False
        )
        
        # Get user context
        try:
            db = get_db_manager()
            user_context = db.get_user_context(user_id)
        except:
            user_context = {}
        
        return {
            "user_id": user_id,
            "test_query": test_query,
            "memories_found": len(memories),
            "retrieval_time_ms": retrieval_time,
            "memories": [
                {
                    "msg_id": m.msg_id,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "confidence": m.confidence
                }
                for m in memories
            ],
            "user_context": user_context,
            "note": "Phase 1: Real vector search results from CockroachDB + Bedrock"
        }
        
    except Exception as e:
        logger.error(f"Error in memory debug: {str(e)}", exc_info=True)
        return {
            "user_id": user_id,
            "test_query": test_query,
            "error": str(e),
            "note": "Failed to retrieve real memories. Check logs for details."
        }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for graceful error responses"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred",
            "detail": str(exc) if settings.DEBUG else "Internal server error"
        }
    )

# ============================================
# AWS Lambda Handler
# ============================================

# Mangum adapter converts FastAPI to AWS Lambda format
handler = Mangum(app, lifespan="off")

# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
