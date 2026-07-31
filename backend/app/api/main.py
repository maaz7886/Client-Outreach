from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, crm, public
from app.core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="College Outreach API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins.split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(public.router)
    app.include_router(crm.router, prefix="/api")

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
