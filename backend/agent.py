"""
AI Agent logic with memory integration
Phase 0: Fake responses to test skeleton
Phase 1+: Real Bedrock integration
"""

import time
from typing import List, Dict, Any, Optional, Tuple
import structlog
from config import settings
from database import (
    search_similar_memories,
    get_recent_messages,
    get_user_context,
    save_memory_audit
)

logger = structlog.get_logger()


class SupportAgent:
    """Customer support agent with persistent memory"""
    
    def __init__(self):
        self.use_real_embeddings = settings.ENABLE_REAL_EMBEDDINGS
        self.use_real_llm = settings.ENABLE_REAL_LLM
        self.memory_retrieval_limit = settings.MEMORY_RETRIEVAL_LIMIT
        self.similarity_threshold = settings.MEMORY_SIMILARITY_THRESHOLD
        self.recent_limit = settings.RECENT_MESSAGES_LIMIT
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using Bedrock Titan
        Phase 0: Returns fake embedding
        Phase 1+: Real Bedrock API call
        """
        if not self.use_real_embeddings:
            # Phase 0: Return fake 1024-dimensional embedding
            logger.info("Using fake embedding (Phase 0)", text_length=len(text))
            return [0.0] * 1024
        
        # Phase 1+: Real implementation
        try:
            # TODO: Implement real Bedrock Titan embedding call
            # import boto3
            # bedrock = boto3.client('bedrock-runtime', region_name=settings.AWS_REGION)
            # response = bedrock.invoke_model(...)
            pass
        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e))
            raise
    
    async def retrieve_memories(
        self,
        user_id: str,
        query_text: str,
        conv_id: str
    ) -> Tuple[List[Dict], List[Dict], Dict, int]:
        """
        Retrieve relevant memories for the query
        Returns: (semantic_memories, recent_messages, user_context, retrieval_time_ms)
        """
        start_time = time.time()
        
        # Get query embedding
        query_embedding = await self.generate_embedding(query_text)
        
        # Phase 0: Skip vector search (no real embeddings yet)
        semantic_memories = []
        if self.use_real_embeddings and query_embedding:
            semantic_memories = search_similar_memories(
                user_id=user_id,
                query_embedding=query_embedding,
                limit=self.memory_retrieval_limit,
                similarity_threshold=self.similarity_threshold
            )
        
        # Get recent messages from current conversation
        recent_messages = get_recent_messages(
            conv_id=conv_id,
            limit=self.recent_limit
        )
        
        # Get user context (facts about the user)
        user_context = get_user_context(user_id)
        
        retrieval_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "Retrieved memories",
            user_id=user_id,
            semantic_count=len(semantic_memories),
            recent_count=len(recent_messages),
            context_keys=list(user_context.keys()),
            retrieval_time_ms=retrieval_time_ms
        )
        
        return semantic_memories, recent_messages, user_context, retrieval_time_ms
    
    def build_prompt(
        self,
        query: str,
        semantic_memories: List[Dict],
        recent_messages: List[Dict],
        user_context: Dict
    ) -> str:
        """
        Build prompt with memory context for LLM
        This is where the magic happens - injecting retrieved memories
        """
        prompt_parts = [
            "You are a helpful customer support agent with access to conversation history.",
            ""
        ]
        
        # Add user context (facts we know about the user)
        if user_context:
            prompt_parts.append("What you know about this user:")
            for key, data in user_context.items():
                confidence_pct = int(data['confidence'] * 100)
                prompt_parts.append(f"- {key}: {data['value']} (confidence: {confidence_pct}%)")
            prompt_parts.append("")
        
        # Add semantic memories (from past conversations)
        if semantic_memories:
            prompt_parts.append("Relevant memories from past conversations:")
            for i, memory in enumerate(semantic_memories, 1):
                similarity_pct = int(memory.get('similarity', 0) * 100)
                date = memory['created_at'].strftime('%B %d, %Y at %I:%M %p')
                prompt_parts.append(
                    f"{i}. [{date}] {memory['role']}: {memory['content']} "
                    f"(relevance: {similarity_pct}%)"
                )
            prompt_parts.append("")
        
        # Add recent messages from current conversation
        if recent_messages:
            prompt_parts.append("Recent conversation:")
            for msg in recent_messages:
                prompt_parts.append(f"{msg['role']}: {msg['content']}")
            prompt_parts.append("")
        
        # Add current query
        prompt_parts.append(f"User: {query}")
        prompt_parts.append("")
        prompt_parts.append(
            "Assistant: Provide a helpful response. "
            "If you recognize this issue from past conversations, mention it naturally."
        )
        
        return "\n".join(prompt_parts)
    
    async def generate_response(
        self,
        user_id: str,
        query: str,
        conv_id: str
    ) -> Dict[str, Any]:
        """
        Generate agent response with memory awareness
        
        Returns:
            {
                "response": str,
                "memories_used": List[Dict],
                "retrieval_time_ms": int,
                "confidence_scores": List[float]
            }
        """
        # Retrieve relevant memories
        semantic_memories, recent_messages, user_context, retrieval_time_ms = \
            await self.retrieve_memories(user_id, query, conv_id)
        
        # Build prompt with memory context
        prompt = self.build_prompt(query, semantic_memories, recent_messages, user_context)
        
        # Phase 0: Fake response to test skeleton
        if not self.use_real_llm:
            response_text = self._generate_fake_response(
                query, semantic_memories, recent_messages, user_context
            )
        else:
            # Phase 2+: Real LLM call
            response_text = await self._call_bedrock_claude(prompt)
        
        # Extract confidence scores
        confidence_scores = [
            mem.get('similarity', 0.0) for mem in semantic_memories
        ]
        
        # Save audit trail
        retrieved_msg_ids = [mem['msg_id'] for mem in semantic_memories]
        save_memory_audit(
            user_id=user_id,
            query_text=query,
            query_embedding=await self.generate_embedding(query) if self.use_real_embeddings else None,
            retrieved_msg_ids=retrieved_msg_ids,
            retrieval_scores=confidence_scores,
            response_text=response_text,
            retrieval_time_ms=retrieval_time_ms
        )
        
        return {
            "response": response_text,
            "memories_used": semantic_memories,
            "recent_context": recent_messages,
            "user_facts": user_context,
            "retrieval_time_ms": retrieval_time_ms,
            "confidence_scores": confidence_scores
        }
    
    def _generate_fake_response(
        self,
        query: str,
        semantic_memories: List[Dict],
        recent_messages: List[Dict],
        user_context: Dict
    ) -> str:
        """Phase 0: Generate fake response to test skeleton"""
        
        # If we have past memories, acknowledge them
        if semantic_memories:
            past_issue = semantic_memories[0]['content'][:100]
            date = semantic_memories[0]['created_at'].strftime('%B %d')
            return (
                f"I can see from our conversation on {date} that you mentioned: \"{past_issue}...\"\n\n"
                f"Is this related to the same issue? I'm here to help!"
            )
        
        # If we have user context, use it
        if user_context:
            return (
                f"Thanks for reaching out! I have some context about you from our previous conversations. "
                f"How can I help you today?"
            )
        
        # Generic response
        return (
            "Hello! I'm your support agent with memory. "
            "I'll remember our conversation for future reference. How can I help you today?"
        )
    
    async def _call_bedrock_claude(self, prompt: str) -> str:
        """
        Phase 2+: Real Bedrock Claude API call
        """
        # TODO: Implement real Bedrock call
        # import boto3
        # bedrock = boto3.client('bedrock-runtime', region_name=settings.AWS_REGION)
        # response = bedrock.invoke_model(
        #     modelId=settings.BEDROCK_CLAUDE_MODEL_ID,
        #     body=json.dumps({
        #         "anthropic_version": "bedrock-2023-05-31",
        #         "max_tokens": 1024,
        #         "messages": [{"role": "user", "content": prompt}]
        #     })
        # )
        pass


# Global agent instance
agent = SupportAgent()
