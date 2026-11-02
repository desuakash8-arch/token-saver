from contextlib import asynccontextmanager
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .analyzer import analyze, compare, resolve_model
from .catalog import catalog
from .healer import heal
from .optimizer import OptimizerError, optimize, optimizer_status
from .providers import ProviderError, provider_status
from .schemas import AnalysisRequest, HealRequest, OptimizeRequest, SaveRequest, WordRequest
from .storage import HistoryStore
from .tokenizer import TokenizerUnavailable, word_breakdown

STATIC = Path(__file__).parent / "static"


def create_app(db_path: Path | None = None) -> FastAPI:
    load_dotenv(override=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        location = db_path or Path(os.getenv("TOKEN_SAVER_DB", "data/token_saver.sqlite3"))
        app.state.history = HistoryStore(location)
        yield

    app = FastAPI(title="Token Saver API", version=__version__, description="Local-first token analysis. Saving is explicit. Provider counting and Groq AI optimization are separate, opt-in cloud actions.", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv("TOKEN_SAVER_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver").split(","))

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        # No cross-origin browser writes to a local service with optional provider keys.
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin and origin != expected:
                return JSONResponse({"detail": "Cross-origin writes are not allowed."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site writes are not allowed."}, status_code=403)
            size = request.headers.get("content-length", "0")
            if not size.isdigit() or int(size) > 2000000:
                return JSONResponse({"detail": "Request is too large (2 MB maximum)."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def bad_request(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def invalid_payload(request: Request, exc: RequestValidationError):
        # Do not echo supplied prompts, invalid Unicode, or validator exception objects.
        errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(ProviderError)
    async def provider_failure(request: Request, exc: ProviderError):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(TokenizerUnavailable)
    async def tokenizer_failure(request: Request, exc: TokenizerUnavailable):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(OptimizerError)
    async def optimizer_failure(request: Request, exc: OptimizerError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/models")
    def models():
        return {**catalog(), "provider_counting": provider_status()}

    @app.post("/api/analyze")
    def run_analysis(payload: AnalysisRequest):
        return analyze(payload)

    @app.post("/api/compare")
    def run_comparison(payload: AnalysisRequest):
        return {"models": compare(payload), "mode": "local"}

    @app.post("/api/heal")
    def run_healing(payload: HealRequest):
        return heal(payload)

    @app.get("/api/optimizer")
    def optimizer_configuration():
        return optimizer_status()

    @app.post("/api/optimize")
    def run_optimizer(payload: OptimizeRequest):
        return optimize(payload)

    @app.post("/api/words")
    def analyze_words(payload: WordRequest):
        request = AnalysisRequest(prompt=payload.prompt, model_id=payload.model_id, custom_model=payload.custom_model)
        model = resolve_model(request)
        return word_breakdown(payload.prompt, model["encoding"], offset=payload.offset,
                              limit=payload.limit, query=payload.query, min_tokens=payload.min_tokens)

    @app.post("/api/history", status_code=201)
    def save_analysis(payload: SaveRequest):
        # Recompute on the server so clients cannot persist fabricated prices.
        result = analyze(payload.request, preview=False)
        analysis_id = app.state.history.save(payload.title, payload.request.model_dump(mode="json"), result)
        return {"id": analysis_id, "title": payload.title}

    @app.get("/api/history")
    def list_history(q: str = Query("", max_length=120), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return {"items": app.state.history.list(q, limit, offset)}

    @app.get("/api/history/{analysis_id}")
    def get_history(analysis_id: str):
        record = app.state.history.get(analysis_id)
        if record is None:
            raise HTTPException(404, "Saved analysis not found.")
        return record

    @app.delete("/api/history/{analysis_id}", status_code=204)
    def delete_history(analysis_id: str):
        if not app.state.history.delete(analysis_id):
            raise HTTPException(404, "Saved analysis not found.")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
