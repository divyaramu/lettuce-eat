import time
from pathlib import Path

import re

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from .agents.extractor import Extractor, GeminiExtractor, RuleExtractor
from .agents.orchestrator import build_report
from .config import Settings, get_settings
from .models import Restriction
from .security import clean_text
from .sources.base import SourceProvider
from .store import Store, secrets_equal

WEB = Path(__file__).parent / "web"
REPORT_COOLDOWN_S = 20


class JoinBody(BaseModel):
    token: str = Field(max_length=64)
    nickname: str = Field(min_length=1, max_length=30)
    restrictions: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("restrictions")
    @classmethod
    def validate_restrictions(cls, value: list[str]) -> list[str]:
        valid = {r.value for r in Restriction}
        for item in value:
            raw = str(item).strip()
            if not raw:
                raise ValueError("restriction required")
            if raw in valid:
                continue
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{0,39}", raw) and "_" not in raw:
                continue
            raise ValueError(f"unsupported restriction: {raw}")
        return value


class CreateBody(BaseModel):
    area: str = Field(default="Seattle, WA", max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=2.0, ge=0.5, le=25)


def default_provider(settings: Settings) -> SourceProvider:
    if settings.source_mode == "live":
        from .sources.live import LiveProvider
        search = None
        if settings.gemini_api_key:
            from .agents.search import make_grounded_search
            search = make_grounded_search(settings.gemini_api_key, settings.gemini_model)
        return LiveProvider(grounded_search=search)
    from .sources.fixtures import FixtureProvider
    return FixtureProvider()


def default_extractor(settings: Settings) -> Extractor:
    if settings.gemini_api_key and settings.source_mode == "live":
        return GeminiExtractor(settings.gemini_api_key, settings.gemini_model)
    return RuleExtractor()


def create_app(settings: Settings | None = None, provider: SourceProvider | None = None,
               extractor: Extractor | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or get_settings()
    provider = provider or default_provider(settings)
    extractor = extractor or default_extractor(settings)
    store = store or Store(settings.max_members)
    last_run: dict[str, float] = {}

    app = FastAPI(title="Lettuce Eat", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.settings = store, settings

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "connect-src 'self' https://unpkg.com https://tile.openstreetmap.org https://*.tile.openstreetmap.org "
            "https://nominatim.openstreetmap.org https://overpass-api.de; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; base-uri 'none'; form-action 'self'"
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def authed_group(gid: str, t: str = Query(max_length=64)):
        g = store.get(gid)
        if not g or not secrets_equal(g.join_token, t):
            raise HTTPException(404, "not found")  # same error for bad id or bad token
        return g

    @app.post("/api/groups")
    def create(body: CreateBody):
        g = store.create_group(body.area, body.lat, body.lon, body.radius_km)
        return {"id": g.id, "token": g.join_token,
                "url": f"{settings.public_base_url}/g/{g.id}?t={g.join_token}"}

    @app.post("/api/groups/{gid}/join")
    def join(gid: str, body: JoinBody):
        m = store.join(gid, body.token, clean_text(body.nickname, 30), body.restrictions)
        if not m:
            raise HTTPException(404, "not found or group full")
        return m

    @app.get("/api/groups/{gid}")
    def get_group(g=Depends(authed_group)):
        return {"id": g.id, "area": g.area,
                "members": [{"nickname": m.nickname, "restrictions": m.restrictions} for m in g.members]}

    @app.post("/api/groups/{gid}/report")
    def make_report(g=Depends(authed_group)):
        if not g.members:
            raise HTTPException(400, "add at least one member first")
        now = time.monotonic()
        prev = last_run.get(g.id)
        if prev is not None and now - prev < REPORT_COOLDOWN_S:
            raise HTTPException(429, "please wait a few seconds before regenerating")
        last_run[g.id] = now
        rep = build_report(g, provider, extractor, settings.max_venues)
        store.save_report(rep)
        return rep

    @app.get("/api/groups/{gid}/report")
    def get_report(g=Depends(authed_group)):
        rep = store.report(g.id)
        if not rep:
            raise HTTPException(404, "no report yet")
        return rep

    @app.get("/")
    @app.get("/g/{gid}")
    def index(gid: str | None = None):
        return FileResponse(WEB / "index.html")

    @app.get("/static/{name}")
    def static(name: str):
        if name not in ("app.js", "style.css"):
            raise HTTPException(404)
        return FileResponse(WEB / name)

    @app.exception_handler(Exception)
    async def boom(_: Request, __: Exception):
        return JSONResponse({"detail": "internal error"}, status_code=500)  # never leak internals

    return app
