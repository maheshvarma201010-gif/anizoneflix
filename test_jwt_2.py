import jwt
from config.config import Config
import os
from dotenv import load_dotenv

load_dotenv()

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo4NjQ2NDE2OTczLCJpc19hZG1pbiI6dHJ1ZSwiZXhwIjoxNzc5MDk0MDg1fQ.tkDg9Y2mt0vRVXOs4DvItOPCmMuXtlw4cMjBEYVXc9I"
secret = os.getenv("SECRET_KEY")
print(f"Secret: {secret}")
try:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    print(f"Payload: {payload}")
except Exception as e:
    print(f"Error: {e}")
