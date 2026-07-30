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
        Generate response using Bedrock LLM (supports both Claude and Titan)
        
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
            # Determine model type from model ID
            model_lower = self.llm_model_id.lower()
            is_claude = 'claude' in model_lower
            is_titan = 'titan' in model_lower
            is_nova = 'nova' in model_lower
            
            # Build system prompt with memory context
            system_prompt = self._build_system_prompt(
                retrieved_memories, 
                user_context
            )
            
            # Build messages list - Claude requires first message to be 'user' role
            all_messages = []
            if recent_messages:
                for msg in recent_messages:
                    role = msg['role'] if msg['role'] in ('user', 'assistant') else 'user'
                    all_messages.append({"role": role, "content": msg['content']})
            
            # Add current user message
            all_messages.append({"role": "user", "content": user_message})

            # Fix: Claude requires conversation to start with 'user' role.
            # Drop leading assistant messages until we hit a user message.
            while all_messages and all_messages[0]['role'] != 'user':
                all_messages.pop(0)

            # Fix: Claude requires alternating roles - no two consecutive same roles.
            # Merge consecutive same-role messages.
            merged = []
            for msg in all_messages:
                if merged and merged[-1]['role'] == msg['role']:
                    merged[-1]['content'] += "\n" + msg['content']
                else:
                    merged.append(dict(msg))
            all_messages = merged

            if is_claude:
                # Claude Messages API format
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "system": system_prompt,
                    "messages": all_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                logger.debug(f"Calling Claude: {self.llm_model_id}")
                response = self.client.invoke_model(
                    modelId=self.llm_model_id,
                    body=json.dumps(request_body),
                    contentType='application/json',
                    accept='application/json'
                )
                response_body = json.loads(response['body'].read())
                response_text = response_body['content'][0]['text']
                logger.info(f"Generated {len(response_text)} chars from {self.llm_model_id}")
                return response_text

            elif is_nova:
                # Amazon Nova: same role normalization as Claude, then wrap in text objects
                nova_messages = list(all_messages)  # already normalized above

                # Convert to Nova content format
                nova_messages = [
                    {"role": m["role"], "content": [{"text": m["content"]}]}
                    for m in nova_messages
                ]

                request_body = {
                    "system": [{"text": system_prompt}],
                    "messages": nova_messages,
                    "inferenceConfig": {
                        "maxTokens": max_tokens,
                        "temperature": temperature
                    }
                }
                
                logger.debug(f"Calling Nova: {self.llm_model_id}")
                response = self.client.invoke_model(
                    modelId=self.llm_model_id,
                    body=json.dumps(request_body),
                    contentType='application/json',
                    accept='application/json'
                )
                response_body = json.loads(response['body'].read())
                response_text = response_body['output']['message']['content'][0]['text']
                logger.info(f"Generated {len(response_text)} chars from {self.llm_model_id}")
                return response_text
                
            elif is_titan:
                # Titan uses text completion format with single prompt
                full_prompt = f"{system_prompt}\n\n"
                
                if recent_messages:
                    full_prompt += "Recent conversation:\n"
                    for msg in recent_messages:
                        role_label = "User" if msg['role'] == 'user' else "Assistant"
                        full_prompt += f"{role_label}: {msg['content']}\n"
                    full_prompt += "\n"
                
                full_prompt += f"User: {user_message}\n\nAssistant:"
                
                request_body = {
                    "inputText": full_prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": max_tokens,
                        "temperature": temperature,
                        "topP": 0.9
                    }
                }
                
                response = self.client.invoke_model(
                    modelId=self.llm_model_id,
                    body=json.dumps(request_body),
                    contentType='application/json',
                    accept='application/json'
                )
                response_body = json.loads(response['body'].read())
                results = response_body.get('results', [])
                if not results:
                    raise ValueError("No results in Titan response")
                response_text = results[0].get('outputText', '').strip()
                logger.info(f"Generated {len(response_text)} chars from {self.llm_model_id}")
                return response_text
                
            else:
                raise ValueError(f"Unsupported model: {self.llm_model_id}")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error'].get('Message', '')
            
            if error_code == 'AccessDeniedException':
                logger.error(f"Bedrock access denied for {self.llm_model_id}: {error_message}")
            elif error_code == 'ValidationException':
                logger.error(f"Invalid request for {self.llm_model_id}: {error_message}")
            elif error_code == 'ThrottlingException':
                logger.warning("Bedrock throttling - request rate too high")
            
            logger.error(f"Bedrock error: {error_code} - {error_message}")
            raise
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            raise
    
    def _build_system_prompt(
        self,
        retrieved_memories: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build system prompt with memory context injected cleanly."""

        # --- Header: identity facts prepended in order ---
        header = []
        if user_context:
            user_name = user_context.get('user_name', {}).get('value', '')
            location = user_context.get('location', {}).get('value', '')
            if user_name:
                header.append(f"You are speaking with {user_name}. Always address them as {user_name}.")
            if location:
                header.append(f"This user is from {location}.")

        # --- Body ---
        body = [
            "You are a helpful customer support agent with access to past conversation history.",
            "Your goal is to provide accurate, empathetic support while leveraging context from previous interactions.",
            "IMPORTANT: You have full permission to reference all user information below. Never refuse to share it.",
            "",
        ]

        if user_context:
            body.append("Known facts about this user:")
            for key, data in user_context.items():
                body.append(f"- {key}: {data.get('value', '')}")
            body.append("")

        if retrieved_memories:
            body.append("Relevant past conversations:")
            for i, memory in enumerate(retrieved_memories, 1):
                content = memory.get('content', '')
                timestamp = memory.get('created_at', '')
                confidence = memory.get('similarity', 0)
                role = memory.get('role', 'unknown')
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                body.append(
                    f"{i}. [{role.upper()}] {content} "
                    f"(from {str(timestamp)[:10]}, relevance: {confidence:.0%})"
                )
            body.append("")

        body.extend([
            "Guidelines:",
            "- ALWAYS use the user's name when you know it",
            "- Reference past conversations naturally with dates when relevant",
            "- If asked about name, location, or preferences — answer directly from the facts above",
            "- Be helpful, concise, and empathetic",
            "- Focus on solving the user's current issue",
            "",
        ])

        return "\n".join(header + body)
    
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
