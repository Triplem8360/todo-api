from __future__ import annotations

from fastapi import APIRouter

from todo_api.api.v1.routes import api_key, auth, health, oauth, todos, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(oauth.router)
api_router.include_router(api_key.router)
api_router.include_router(todos.router)
api_router.include_router(users.router)
