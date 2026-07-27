from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
resp = client.post('/api/chat', json={'message':'hello','model':'gpt-4'})
print(resp.status_code)
print(resp.text)
