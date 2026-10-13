"""React용 API. 실행: uvicorn fire_risk_project.api:app --reload"""
from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

from . import risk_engine as engine
from . import storage as evaluation_storage

ROOT = Path(__file__).resolve().parent


def frame_rows(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    task_id: Literal["H05"] = "H05"
    answers: dict[str, StrictStr | StrictInt | StrictFloat | None] = Field(default_factory=dict, max_length=100)


class EvaluationInput(Answers):
    site_name: str = Field(min_length=1, max_length=200)
    watcher_answers: dict[str, Literal["예", "아니오", "확인불가"]] = Field(default_factory=dict, max_length=4)


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_id: str = Field(min_length=1, max_length=100)
    after_id: str = Field(min_length=1, max_length=100)


def create_app(storage_path=None, access_key=None, origins=None):
    storage = evaluation_storage.configured_storage(storage_path)
    key = access_key if access_key is not None else os.environ.get("APP_ACCESS_KEY", "")
    allowed_origins = origins if origins is not None else [
        s.strip().rstrip("/") for s in os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if s.strip()
    ]

    @asynccontextmanager
    async def lifespan(app):
        if os.environ.get("RENDER") and not key:
            raise RuntimeError("Render 배포에는 APP_ACCESS_KEY 설정이 필요합니다.")
        engine.load_databases(ROOT / "data")
        evaluation_storage.initialize(storage)
        yield

    app = FastAPI(title="화재 위험도 평가 API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Access-Key"])

    def authorize(x_access_key: Annotated[str | None, Header()] = None):
        if key and not hmac.compare_digest((x_access_key or "").encode(), key.encode()):
            raise HTTPException(401, "접속 키를 확인하세요.")

    secured = [Depends(authorize)]

    @app.exception_handler(ValueError)
    async def invalid(request: Request, error: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(KeyError)
    @app.exception_handler(FileNotFoundError)
    async def missing(request: Request, error: Exception):
        return JSONResponse(status_code=404, content={"detail": "평가 기록을 찾을 수 없습니다."})

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    @app.exception_handler(evaluation_storage.StorageError)
    async def storage_error(request: Request, error: Exception):
        logging.exception("평가 저장소 오류", exc_info=error)
        return JSONResponse(status_code=503, content={"detail": "저장소에 연결하지 못했습니다. 잠시 후 다시 시도하세요."})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/session", dependencies=secured)
    def session():
        return {"authenticated": True}

    @app.post("/api/questions", dependencies=secured)
    def questions(body: Answers):
        return {"questions": frame_rows(engine.get_prework_questions(body.task_id, body.answers)),
                "watcher_questions": frame_rows(engine.watcher_questions[~engine.watcher_questions['추가질문ID'].isin(['W002', 'W003'])])}

    @app.post("/api/evaluate", dependencies=secured)
    def evaluate(body: EvaluationInput):
        table = engine.get_prework_questions(body.task_id, body.answers)
        active = set(table.loc[table["적용상태"].eq("적용"), "항목ID"])
        answers = {qid: value for qid, value in body.answers.items() if qid in active}
        if any(answers.get(qid) == "해당없음" for qid in ("Q003", "Q004")):
            raise ValueError("Q003·Q004의 해당없음 근거는 아직 자동 검증하지 않습니다. 계산을 보류합니다. 실제 상태와 다르게 응답을 바꾸지 마세요.")
        if set(body.watcher_answers) - set(engine.watcher_questions["추가질문ID"]):
            raise ValueError("알 수 없는 화재감시자 추가질문입니다.")
        watcher_answers = dict(body.watcher_answers)
        # Q019/Q020 cover the same conditions. Always prefer the current Q response,
        # including unknown, over potentially stale values from older clients.
        for wid, qid in (("W002", "Q019"), ("W003", "Q020")):
            watcher_answers[wid] = {"있음": "예", "없음": "아니오", "확인불가": "확인불가"}.get(answers.get(qid), "확인불가")
        record = engine.build_evaluation(body.site_name, body.task_id, answers, watcher_answers)
        evaluation_storage.save_draft(storage, record)
        return record

    @app.post("/api/evaluations/{evaluation_id}/save", dependencies=secured)
    def save(evaluation_id: str):
        # 요청 본문의 점수를 신뢰하지 않고 서버가 계산한 초안만 저장합니다.
        if evaluation_storage.saved_exists(storage, evaluation_id):
            return {"평가ID": evaluation_id, "저장상태": "이미 저장됨"}
        draft = evaluation_storage.load_fresh_draft(storage, evaluation_id)
        if not draft:
            raise HTTPException(404, "평가 초안이 없거나 24시간이 지났습니다. 다시 평가하세요.")
        result = engine.save_evaluation(draft, storage)
        return {k: result[k] for k in ("평가ID", "저장상태")}

    @app.get("/api/evaluations", dependencies=secured)
    def history(site_keyword: str = Query(default="", max_length=200)):
        return frame_rows(engine.search_evaluations(storage, site_keyword=site_keyword, task_id="H05"))

    @app.get("/api/evaluations/{evaluation_id}", dependencies=secured)
    def detail(evaluation_id: str):
        return engine.load_evaluation(evaluation_id, storage)

    @app.post("/api/compare", dependencies=secured)
    def compare(body: Comparison):
        result = engine.compare_evaluations(body.before_id, body.after_id, storage)
        return {name: value if isinstance(value, dict) else frame_rows(value) for name, value in result.items()}

    @app.get("/api/dashboard", dependencies=secured)
    def dashboard(site: str = Query(default="", max_length=200)):
        history = engine.search_evaluations(storage, task_id="H05")
        sites = sorted(history["현장명"].unique().tolist())
        if site:
            history = history.loc[history["현장명"].eq(site)]
        records = [engine.load_evaluation(identifier, storage) for identifier in history["평가ID"]]
        grades = {}
        trends = []
        for record in records:
            summary = record["요약"]
            grade = summary["기본위험등급(잠정)"]
            grades[grade] = grades.get(grade, 0) + 1
            trends.append({"id": record["평가ID"], "date": record["평가일시"], "score": summary["위험지수"],
                           "group": [record.get("계산데이터SHA256"), record.get("엔진SHA256"), summary["최대가중점수"]]})
        return {"sites": sites, "count": len(records), "site_count": history["현장명"].nunique(),
                "held_count": sum(r["요약"]["최종판정"].startswith("보류") for r in records),
                "grades": grades, "trends": trends}

    return app


app = create_app()
