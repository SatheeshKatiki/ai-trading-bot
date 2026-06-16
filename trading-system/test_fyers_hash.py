import os
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv(".env")
client_id = os.getenv("FYERS_CLIENT_ID", "")
secret_key = os.getenv("FYERS_SECRET_KEY", "")

# The user provided this code
auth_code = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfaWQiOiIwS0hCUTZJUUE0IiwidXVpZCI6IjFmMzgyNzRmNDhkMzQ0MGJhNTA2NWQwNzRiYzRiMjhjIiwiaXBBZGRyIjoiIiwibm9uY2UiOiIiLCJzY29wZSI6IiIsImRpc3BsYXlfbmFtZSI6IllLMTcxOTAiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI0ODRiYWZmMDNjZjA1NTdiZjVhNjE3NzZkMmMwMTczMWUzMTQyYmIzZDI4NDM5OWI1MmJmNjI2YSIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImF1ZCI6IltcImQ6MVwiLFwiZDoyXCIsXCJ4OjBcIixcIng6MVwiLFwieDoyXCJdIiwiZXhwIjoxNzgxNTgyNDE2LCJpYXQiOjE3ODE1NTI0MTYsImlzcyI6ImFwaS5sb2dpbi5meWVycy5pbiIsIm5iZiI6MTc4MTU1MjQxNiwic3ViIjoiYXV0aF9jb2RlIn0.hH4zq5-JVfq03prQDK-pFPZvhXFoVpoVtkA0cs08Qa8"

# Standard appIdHash
appIdHash = hashlib.sha256(f"{client_id}:{secret_key}".encode('utf-8')).hexdigest()

data = {
    "grant_type": "authorization_code",
    "appIdHash": appIdHash,
    "code": auth_code
}

response = requests.post("https://api-t1.fyers.in/api/v3/validate-authcode", json=data)
print("Standard hash response:", response.json())

# Try without -100
client_id_no_suffix = client_id.split("-")[0]
appIdHash2 = hashlib.sha256(f"{client_id_no_suffix}:{secret_key}".encode('utf-8')).hexdigest()
data2 = {
    "grant_type": "authorization_code",
    "appIdHash": appIdHash2,
    "code": auth_code
}
response2 = requests.post("https://api-t1.fyers.in/api/v3/validate-authcode", json=data2)
print("Hash without -100 response:", response2.json())
