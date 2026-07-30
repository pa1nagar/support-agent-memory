"""
AWS Bedrock client for embeddings and LLM inference
Handles communication with Claude and Titan models
"""

import json
import logging
from typing import List, Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)


class BedrockClient:
    """Client for AWS Bedrock models"""
    
    def __init__(self):
        self.client = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.AWS_REGION
        )
        self.embedding_model_id = settings.BEDROCK_EMBEDDING_MODEL_ID
        self.llm_model_id = settings.BEDROCK_MODEL_ID
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using Amazon Titan Embeddings V2
        Returns 1024-dimensional vector
        """
        try:
            # Titan Embeddings V2 request format
            request_body = {
                "inputText": text,
                "dimensions": 1024,
                "normalize": True  # Normalize for cosine similarity
            }
            
            response = self.client.invoke_model(
                modelId=self.embedding_model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding')
            
            if not embedding:
                raise ValueError("No embedding returned from Bedrock")
            
            logger.debug(f"Generated embedding: {len(embedding)} dimensions")
            return embedding
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDeniedException':
                logger.error(
                    "Bedrock access denied. Ensure you have enabled model access in "
                    "AWS Console: https://console.aws.amazon.com/bedrock"
                )
            raise
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def generate_response(
        self,
        user_message: str,
        retrieved_memories: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """
        Generate response using Claude 3.5 Sonnet with memory context
        
        Args:
            user_message: The current user query
            retrieved_memories: Semantically similar past messages
            user_context: Structured facts about the user
            recent_messages: Recent messages from current conversation
            max_tokens: Maximum response length
            temperature: Sampling temperature (0-1)
        
        Returns:
            Generated response text
        """
        try:
            # Build system prompt with memory context
            system_prompt = self._build_system_prompt(
                retrieved_memories, 
                user_context
            )
            
            # Build conversation history
            messages = []
            
            # Add recent conversation messages if available
            if recent_messages:
                for msg in recent_messages:
                    messages.append({
                        "role": msg['role'],
                        "content": msg['content']
                    })
            
            # Add current user message
            messages.append({
                "role": "user",
                "content": user_message
            })
            
            # Claude 3.5 request format
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": messages
            }
            
            logger.debug(f"Calling Claude with {len(messages)} messages")
            
            response = self.client.invoke_model(
                modelId=self.llm_model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            
            # Extract text from response
            content = response_body.get('content', [])
            if not content:
                raise ValueError("No content in Claude response")
            
            response_text = content[0].get('text', '')
            
            logger.info(f"Generated response: {len(response_text)} characters")
            return response_text
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDeniedException':
                logger.error(
                    "Bedrock access denied for Claude. Ensure model access is enabled."
                )
            elif error_code == 'ThrottlingException':
                logger.warning("Bedrock throttling - request rate too high")
            raise
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            raise
    
    def _build_system_prompt(
        self,
        retrieved_memories: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build system prompt with memory context"""
        
        prompt_parts = [
            "You are a helpful customer support agent with access to past conversation history.",
            "Your goal is to provide accurate, empathetic support while leveraging context from previous interactions.",
            ""
        ]
        
        # Add user context if available
        if user_context:
            prompt_parts.append("What you know about this user:")
            for key, data in user_context.items():
                confidence = data.get('confidence', 0)
                value = data.get('value', '')
                prompt_parts.append(f"- {key}: {value} (confidence: {confidence:.0%})")
            prompt_parts.append("")
        
        # Add retrieved memories
        if retrieved_memories:
            prompt_parts.append("Relevant past conversations:")
            for i, memory in enumerate(retrieved_memories, 1):
                content = memory.get('content', '')
                timestamp = memory.get('created_at', '')
                confidence = memory.get('similarity', 0)
                role = memory.get('role', 'unknown')
                
                # Format timestamp
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                
                prompt_parts.append(
                    f"{i}. [{role.upper()}] {content} "
                    f"(from {timestamp[:10]}, relevance: {confidence:.0%})"
                )
            prompt_parts.append("")
        
        prompt_parts.extend([
            "Guidelines:",
            "- Reference past conversations naturally when relevant",
            "- If you remember something specific, mention the date/context",
            "- If you're not sure, acknowledge uncertainty",
            "- Be helpful, concise, and empathetic",
            "- Focus on solving the user's current issue",
            ""
        ])
        
        return "\n".join(prompt_parts)
    
    def health_check(self) -> bool:
        """Check if Bedrock is accessible"""
        try:
            # Try a minimal embedding request
            self.generate_embedding("test")
            return True
        except Exception as e:
            logger.error(f"Bedrock health check failed: {str(e)}")
            return False


# Singleton instance
_bedrock_client: Optional[BedrockClient] = None


def get_bedrock_client() -> BedrockClient:
    """Get or create Bedrock client singleton"""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = BedrockClient()
    return _bedrock_client
