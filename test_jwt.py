import jwt
from config.config import Config

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo4NjQ2NDE2OTczLCJpc19hZG1pbiI6dHJ1ZSwiZXhwIjoxNzc5MDk0MDg1fQ.tkDg9Y2mt0vRVXOs4DvItOPCmMuXtlw4cMjBEYVXc9I"
try:
    payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    print(payload)
except Exception as e:
    print(f"Error: {e}")
