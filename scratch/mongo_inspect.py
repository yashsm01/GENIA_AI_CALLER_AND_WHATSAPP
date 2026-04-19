import asyncio
import os
import traceback
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import sys
sys.path.append(os.getcwd())

from database.models import User, ProductDocument, CallLog

async def test():
    uri = "mongodb://localhost:27017"
    db_name = "ai_auto_caller"
    
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    print(f"DB type: {type(db)}")
    print(f"Has 'client' attribute: {hasattr(db, 'client')}")
    try:
        print(f"db.client type: {type(db.client)}")
    except Exception as e:
        print(f"Error accessing db.client: {e}")
        
    try:
        print(f"db.delegate.client type: {type(db.delegate.client)}")
    except Exception as e:
        print(f"Error accessing db.delegate.client: {e}")

if __name__ == "__main__":
    asyncio.run(test())
