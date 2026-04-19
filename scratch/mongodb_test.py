import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from database.models import User, ProductDocument, CallLog

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    print(type(client))
    
    # Motor returns a MotorDatabase object when accessing a database
    db = client["ai_auto_caller"]
    print(type(db))
    
    # Let's see if init_beanie likes it
    try:
        await init_beanie(database=db, document_models=[User, ProductDocument, CallLog])
        print("Success initializing beanie!")
    except Exception as e:
        print("Error initializing beanie:", e)

if __name__ == "__main__":
    asyncio.run(main())
