from fastapi import FastAPI
from codecompass.api import health, repositories

app = FastAPI()

app.include_router(health.router)
app.include_router(repositories.router)