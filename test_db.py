
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.getenv("MONGO_URI")

try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    print("SUCCESS: Connected to MongoDB Atlas!")
    print("Database:", client["vehicle_rental_db"].name)
except Exception as e:
    print("CONNECTION FAILED:", e)
finally:
    if "client" in locals():
        client.close()
