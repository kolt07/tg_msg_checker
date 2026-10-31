from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import AnalyzeIn, DictionaryIn
from tg_msg_checker.config import Settings
from tg_msg_checker.dictionaries import DictionaryError, DictionaryNotFound
from tg_msg_checker.models import Message
from tg_msg_checker.pipeline import AnalysisEngine


def create_app(data_dir: Path | None = None) -> FastAPI:
    settings = Settings.from_env()
    directory = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parent.parent / "data"
    engine = AnalysisEngine(directory, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine.start_pool()
        try:
            yield
        finally:
            app.state.engine.shutdown()

    app = FastAPI(title="Аналіз повідомлень", lifespan=lifespan)
    app.state.engine = engine
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Elapsed-Ms"],
    )

    @app.get("/api/dictionaries")
    def list_dictionaries() -> list[dict]:
        return app.state.engine.list_dictionaries()

    @app.post("/api/dictionaries", status_code=201)
    def create_dictionary(body: DictionaryIn) -> dict:
        return _call(app.state.engine.create_dictionary, body.name, body.language, body.tag, body.words)

    @app.put("/api/dictionaries/{dictionary_id}")
    def update_dictionary(dictionary_id: str, body: DictionaryIn) -> dict:
        return _call(
            app.state.engine.update_dictionary,
            dictionary_id,
            body.name,
            body.language,
            body.tag,
            body.words,
        )

    @app.delete("/api/dictionaries/{dictionary_id}", status_code=204)
    def delete_dictionary(dictionary_id: str) -> Response:
        _call(app.state.engine.delete_dictionary, dictionary_id)
        return Response(status_code=204)

    @app.post("/api/analyze")
    async def analyze(body: AnalyzeIn, response: Response) -> list[dict]:
        started = time.perf_counter()
        messages = [Message(item.id, item.text) for item in body.messages]
        result = await asyncio.to_thread(app.state.engine.analyze, messages)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Elapsed-Ms"] = f"{elapsed_ms:.2f}"
        return result

    return app


def _call(func, *args):
    try:
        return func(*args)
    except DictionaryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DictionaryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app = create_app()
