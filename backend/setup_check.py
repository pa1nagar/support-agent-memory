"""
Pre-flight check before seeding database
Verifies all connections and configurations
"""

import sys
import logging
from typing import Tuple, List

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_imports() -> Tuple[bool, str]:
    """Check if all required packages are installed"""
    try:
        import psycopg2
        import boto3
        import fastapi
        import pydantic
        from config import settings
        return True, "✅ All Python packages installed"
    except ImportError as e:
        return False, f"❌ Missing package: {str(e)}"

def check_environment() -> Tuple[bool, str]:
    """Check if environment variables are set"""
    try:
        from config import settings
        
        if not settings.DATABASE_URL:
            return False, "❌ COCKROACHDB_URL not set in .env"
        
        if "cockroachlabs.cloud" not in settings.DATABASE_URL and "localhost" not in settings.DATABASE_URL:
            return False, "❌ COCKROACHDB_URL doesn't look like a valid CockroachDB URL"
        
        return True, f"✅ Environment configured (region: {settings.AWS_REGION})"
    except Exception as e:
        return False, f"❌ Environment error: {str(e)}"

def check_database() -> Tuple[bool, str]:
    """Check database connectivity"""
    try:
        from database import get_db_manager
        
        db = get_db_manager()
        
        # Test connection
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()
                
                # Check if tables exist
                cur.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row['table_name'] for row in cur.fetchall()]
                
                required_tables = ['users', 'conversations', 'messages', 'user_context', 'memory_audit']
                missing_tables = [t for t in required_tables if t not in tables]
                
                if missing_tables:
                    return False, f"❌ Missing tables: {', '.join(missing_tables)}\n   Run: cockroach sql --url=\"YOUR_URL\" < database/schema.sql"
                
                return True, f"✅ Database connected (CockroachDB)\n   Tables found: {len(tables)}"
    except Exception as e:
        return False, f"❌ Database connection failed: {str(e)}\n   Check your COCKROACHDB_URL in .env"

def check_bedrock() -> Tuple[bool, str]:
    """Check AWS Bedrock access"""
    try:
        from bedrock_client import get_bedrock_client
        
        bedrock = get_bedrock_client()
        
        # Try to generate a test embedding
        embedding = bedrock.generate_embedding("test connection")
        
        if len(embedding) != 1024:
            return False, f"❌ Unexpected embedding dimension: {len(embedding)}"
        
        return True, f"✅ Bedrock connected (Titan embeddings working)\n   Embedding dimension: {len(embedding)}"
    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg:
            return False, (
                "❌ Bedrock access denied\n"
                "   Go to: https://console.aws.amazon.com/bedrock\n"
                "   Enable: Claude 3.5 Sonnet + Titan Embeddings V2\n"
                "   Region: us-east-1"
            )
        elif "credentials" in error_msg.lower():
            return False, (
                "❌ AWS credentials not configured\n"
                "   Run: aws configure\n"
                "   Or set: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
            )
        else:
            return False, f"❌ Bedrock error: {error_msg}"

def check_message_count() -> Tuple[bool, str]:
    """Check how many messages are already in database"""
    try:
        from database import get_db_manager
        
        db = get_db_manager()
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as count FROM messages")
                count = cur.fetchone()['count']
                
                cur.execute("SELECT COUNT(*) as count FROM messages WHERE embedding IS NOT NULL")
                with_embeddings = cur.fetchone()['count']
                
                if count == 0:
                    return True, "✅ Database empty (ready for seeding)"
                else:
                    return True, f"ℹ️  Database has {count} messages ({with_embeddings} with embeddings)"
    except Exception as e:
        return False, f"❌ Error checking messages: {str(e)}"

def main():
    """Run all checks"""
    print("=" * 60)
    print("🔍 PRE-FLIGHT CHECK - Database Seeding")
    print("=" * 60)
    print()
    
    checks = [
        ("Python Packages", check_imports),
        ("Environment Variables", check_environment),
        ("Database Connection", check_database),
        ("AWS Bedrock", check_bedrock),
        ("Current Data", check_message_count),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"Checking {name}...")
        success, message = check_func()
        results.append(success)
        print(f"  {message}")
        print()
    
    print("=" * 60)
    
    if all(results):
        print("✅ ALL CHECKS PASSED!")
        print()
        print("Ready to seed database!")
        print()
        print("Run: python seed_data.py")
        print("Or:  python seed_data.py 20 3  # 20 users, 3 conversations each")
        print()
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        print()
        print("Please fix the issues above before seeding.")
        print()
        print("Need help? Check:")
        print("  - SETUP_GUIDE.md (step-by-step instructions)")
        print("  - .env.example (required environment variables)")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
