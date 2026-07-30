"""
Seed CockroachDB with realistic conversation data
Generates embeddings using Bedrock and stores in database
"""

import logging
import sys
import uuid
from datetime import datetime, timedelta
import random
from typing import List, Tuple

from database import get_db_manager
from bedrock_client import get_bedrock_client
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample support conversations (user message, agent response pairs)
SAMPLE_CONVERSATIONS = [
    # Login Issues
    [
        ("I can't log in to my dashboard", "I can help you with that. What error message are you seeing?"),
        ("It says AUTH_503 timeout error", "That's a timeout error. Let me check your account status. Can you try clearing your browser cache?"),
        ("Still not working", "I see the issue. Your session expired. I've refreshed your credentials. Please try logging in again."),
        ("It works now, thanks!", "Great! I'm glad we resolved that. Let me know if you have any other issues.")
    ],
    
    # Billing Questions  
    [
        ("I was charged twice this month", "I apologize for that. Let me look into your billing history."),
        ("Can you refund the duplicate charge?", "Absolutely. I can see the duplicate charge. I've processed a refund which should appear in 3-5 business days."),
        ("Thank you for the quick resolution", "You're welcome! Is there anything else I can help you with today?")
    ],
    
    # Feature Requests
    [
        ("Do you have an API for integrations?", "Yes! We have a REST API. Would you like documentation?"),
        ("Yes please, and are there rate limits?", "I'll send you the API docs. Standard tier allows 1000 requests/hour. Need more?"),
        ("That's perfect for now", "Great! I've emailed you the documentation with examples. Let me know if you need help integrating.")
    ],
    
    # Technical Support
    [
        ("My reports are not loading", "Sorry to hear that. When did this start happening?"),
        ("Since yesterday", "I see there was a deployment yesterday. Are you seeing any error codes?"),
        ("Just a spinning loader that never finishes", "I've identified the issue - it's a caching problem. I'll clear your cache on our end."),
        ("That fixed it! Thank you", "Excellent! The reports should load properly now.")
    ],
    
    # Account Management
    [
        ("I need to upgrade my plan", "I can help with that! What features are you looking to access?"),
        ("I need more storage and user seats", "Our Pro plan includes 500GB storage and 50 user seats. Would that work?"),
        ("Perfect, can we upgrade now?", "Absolutely. I've upgraded your account to Pro. Changes are effective immediately."),
        ("Great, I can see the new features now", "Wonderful! Enjoy the upgrade. Reach out if you need anything else.")
    ],
    
    # Password Reset
    [
        ("I forgot my password", "No problem! I can send you a password reset link. What's your email?"),
        ("demo@example.com", "Perfect. I've sent a reset link to demo@example.com. It expires in 1 hour."),
        ("Got it, thanks!", "You're welcome! Let me know if you don't receive it.")
    ],
    
    # Performance Issues
    [
        ("The app is really slow today", "I apologize for that. Let me check our system status."),
        ("Is there an outage?", "No outage, but I see higher than normal traffic in your region. Our team is scaling up capacity."),
        ("How long will it take to fix?", "It should improve within 15-20 minutes. I'll send you an update when it's resolved."),
        ("It's much faster now, thanks", "Glad to hear it! The additional capacity is now active.")
    ],
    
    # Data Export
    [
        ("I need to export all my data", "I can help with that. What format would you like? CSV or JSON?"),
        ("CSV please", "I'll generate a CSV export of all your data. This usually takes 5-10 minutes."),
        ("Great, how will I receive it?", "I'll email you a secure download link to your account email. The link expires in 24 hours."),
        ("Perfect, got the email", "Excellent! Let me know if you need anything else.")
    ],
    
    # Integration Help
    [
        ("How do I connect to Salesforce?", "We have a native Salesforce integration! Let me walk you through it."),
        ("Do I need admin access?", "Yes, you'll need Salesforce admin permissions. Go to Settings > Integrations > Salesforce."),
        ("Found it, what's next?", "Click 'Connect' and authorize with your Salesforce credentials. It syncs every 15 minutes."),
        ("Connected successfully!", "Great! Your data will start syncing shortly.")
    ],
    
    # Mobile App
    [
        ("Is there a mobile app?", "Yes! We have iOS and Android apps. Which platform do you use?"),
        ("iPhone", "Great! Search for our app in the App Store. It's free to download."),
        ("Installed it, do I use the same login?", "Yes, use your existing credentials. All your data syncs automatically."),
        ("Logged in, looks great!", "Wonderful! The mobile app has all desktop features.")
    ]
]

def generate_user_id(index: int) -> str:
    """Generate consistent user IDs as proper UUIDs"""
    # Create a deterministic UUID based on index
    # This ensures same users get same IDs across runs
    namespace = uuid.UUID('12345678-1234-5678-1234-567812345678')
    return str(uuid.uuid5(namespace, f'user-{index:04d}'))

def seed_database(num_users: int = 10, conversations_per_user: int = 2):
    """
    Seed database with realistic conversations
    
    Args:
        num_users: Number of users to create
        conversations_per_user: How many conversations per user
    """
    logger.info(f"Starting database seed: {num_users} users, {conversations_per_user} conversations each")
    
    db = get_db_manager()
    bedrock = get_bedrock_client()
    
    total_messages = 0
    start_time = datetime.now()
    
    for user_idx in range(num_users):
        user_id = generate_user_id(user_idx)
        email = f"user{user_idx:04d}@example.com"
        name = f"Demo User {user_idx + 1}"
        
        # Create user
        logger.info(f"Creating user {user_idx + 1}/{num_users}: {user_id}")
        db.get_or_create_user(user_id, email, name)
        
        for conv_idx in range(conversations_per_user):
            # Pick a random conversation template
            conversation = random.choice(SAMPLE_CONVERSATIONS)
            
            # Create conversation
            conv = db.get_or_create_conversation(user_id)
            conv_id = str(conv['conv_id'])
            
            logger.info(f"  Conversation {conv_idx + 1}/{conversations_per_user}: {conv_id}")
            
            # Add messages with timestamps spread over past days
            base_time = datetime.now() - timedelta(days=random.randint(1, 30))
            
            for msg_idx, (user_msg, agent_msg) in enumerate(conversation):
                # Calculate message timestamp (a few minutes apart)
                msg_time = base_time + timedelta(minutes=msg_idx * 3)
                
                try:
                    # Store user message with embedding
                    user_embedding = bedrock.generate_embedding(user_msg)
                    db.store_message(
                        conv_id=conv_id,
                        user_id=user_id,
                        role="user",
                        content=user_msg,
                        embedding=user_embedding
                    )
                    total_messages += 1
                    
                    # Store agent response with embedding
                    agent_embedding = bedrock.generate_embedding(agent_msg)
                    db.store_message(
                        conv_id=conv_id,
                        user_id=user_id,
                        role="assistant",
                        content=agent_msg,
                        embedding=agent_embedding
                    )
                    total_messages += 1
                    
                    logger.info(f"    Stored message pair {msg_idx + 1}/{len(conversation)}")
                    
                except Exception as e:
                    logger.error(f"Failed to store message: {str(e)}")
                    continue
        
        # Add some user context
        contexts = [
            ("product_tier", random.choice(["Free", "Pro", "Enterprise"])),
            ("preferred_contact", random.choice(["email", "chat", "phone"])),
            ("timezone", random.choice(["UTC", "EST", "PST", "GMT"])),
        ]
        
        for key, value in contexts:
            try:
                db_conn = db.get_connection()
                with db_conn as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO user_context (user_id, context_key, context_value, confidence)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (user_id, context_key) DO NOTHING
                            """,
                            (user_id, key, value, 1.0)
                        )
            except Exception as e:
                logger.error(f"Failed to store user context: {str(e)}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"\n✅ Seed complete!")
    logger.info(f"   Users created: {num_users}")
    logger.info(f"   Messages stored: {total_messages}")
    logger.info(f"   Time elapsed: {elapsed:.1f} seconds")
    logger.info(f"   Average: {elapsed/total_messages:.2f}s per message")


if __name__ == "__main__":
    # Parse command line arguments
    num_users = 10
    conversations_per_user = 2
    
    if len(sys.argv) > 1:
        num_users = int(sys.argv[1])
    if len(sys.argv) > 2:
        conversations_per_user = int(sys.argv[2])
    
    logger.info(f"Seeding database with {num_users} users, {conversations_per_user} conversations each")
    logger.info(f"Total messages: ~{num_users * conversations_per_user * 8}")
    
    confirm = input("Continue? (y/n): ")
    if confirm.lower() != 'y':
        logger.info("Cancelled")
        sys.exit(0)
    
    seed_database(num_users, conversations_per_user)
