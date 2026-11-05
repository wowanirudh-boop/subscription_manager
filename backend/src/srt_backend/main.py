"""ASGI entry point: uvicorn srt_backend.main:app"""

from .api.app import create_app

app = create_app()
