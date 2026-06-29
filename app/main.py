"""FastAPI application entrypoint for JobPilot."""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI()
app.include_router(router)
