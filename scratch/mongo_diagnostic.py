import asyncio
import os
import traceback
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
# Set up PYTHONPATH for debug script
import sys
sys.path.append(os.getcwd())

from database.models import User, ProductDocument, CallLog

async def test():
    uri = "mongodb://localhost:27017"
    db_name = "ai_auto_caller"
    print(f"Testing MongoDB connection to {db_name}...")
    
    try:
        client = AsyncIOMotorClient(uri)
        db = client[db_name]
        print(f"Client type: {type(client)}")
        print(f"DB type: {type(db)}")
        
        await init_beanie(
            database=db,
            document_models=[User, ProductDocument, CallLog],
        )
        print("MongoDB connection and Beanie initialization SUCCESSFUL!")
    except Exception:
        print("MongoDB connection FAILED with traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
