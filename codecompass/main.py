from fastapi import FastAPI

from codecompass.api import health

app = FastAPI(title="CodeCompass", version="0.1.0")
app.include_router(health.router)