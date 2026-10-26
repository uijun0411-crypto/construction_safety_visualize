"""React용 API. 실행: uvicorn fire_risk_project.api:app --reload"""
from contextlib import asynccontextmanager
import base64
import binascii
import hmac
import json
import logging
import os
import sqlite3
import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, StrictBool, model_validator

from . import risk_engine as engine
from . import storage as evaluation_storage
from . import evaluation_history
from . import watcher_input
from . import materials
from . import weather
from . import weather_risk

ROOT = Path(__file__).resolve().parent
MAX_BLUEPRINT_BYTES = 3_000_000


def inspect_blueprint(data, media_type):
    """Validate image signatures and read dimensions without trusting browser metadata."""
    width = height = None
    if media_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    elif media_type == "image/jpeg" and data.startswith(b"\xff\xd8"):
        index = 2
        while index + 4 <= len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            while index < len(data) and data[index] == 0xFF:
                index += 1
            if index >= len(data):
                break
            marker = data[index]
            index += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
                continue
            if index + 2 > len(data):
                break
            length = int.from_bytes(data[index:index + 2], "big")
            if length < 2 or index + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and length >= 7:
                height = int.from_bytes(data[index + 3:index + 5], "big")
                width = int.from_bytes(data[index + 5:index + 7], "big")
                break
            index += length
    elif media_type == "image/webp" and len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
        elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            b1, b2, b3, b4 = data[21:25]
            width = 1 + b1 + ((b2 & 0x3F) << 8)
            height = 1 + (b2 >> 6) + (b3 << 2) + ((b4 & 0x0F) << 10)
    if not width or not height:
        raise ValueError("이미지 형식이 올바르지 않거나 크기 정보를 읽을 수 없습니다.")
    if width > 30000 or height > 30000 or width * height > 80_000_000:
        raise ValueError("이미지 해상도가 너무 큽니다. 8천만 픽셀 이하의 이미지로 등록하세요.")
    return width, height


def frame_rows(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    task_id: Literal["H05"] = "H05"
    answers: dict[str, StrictStr | StrictInt | StrictFloat | None] = Field(default_factory=dict, max_length=100)


class MaterialSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[StrictStr, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=50)
    custom_names: list[Annotated[StrictStr, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=20)
    unknown: StrictBool = False


class EvaluationInput(Answers):
    site_id: UUID | None = None
    blueprint_image_id: UUID | None = None
    region_id: str | None = Field(default=None, max_length=20)
    weather_token: str | None = Field(default=None, max_length=12000)
    weather_exposure: Literal["실외", "실내", "확인불가"] = "확인불가"
    materials: MaterialSelection | None = None
    watcher_ui_version: Literal["integrated-v1"] | None = None
    request_id: UUID | None = None
    site_name: str = Field(min_length=1, max_length=200)
    watcher_answers: dict[str, Literal["예", "아니오", "확인불가"]] = Field(default_factory=dict, max_length=4)


class BlueprintUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: StrictStr = Field(min_length=1, max_length=240)
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    data_base64: StrictStr = Field(min_length=1, max_length=4_100_000)


class RectangleCoordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_image(self):
        if self.x + self.width > 1.0000001 or self.y + self.height > 1.0000001:
            raise ValueError("작업구역은 조감도 이미지 안에 있어야 합니다.")
        return self


class WorkZoneInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr = Field(min_length=1, max_length=80)
    coordinates: RectangleCoordinates

    @model_validator(mode="after")
    def normalize_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("작업구역 이름을 입력하세요.")
        return self


class QuestionInput(Answers):
    watcher_answers: dict[str, Literal["예", "아니오", "확인불가"]] = Field(default_factory=dict, max_length=4)


class ZoneQuestionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    task_id: StrictStr = Field(min_length=1, max_length=20)
    answers: dict[str, StrictStr | StrictInt | StrictFloat | None] = Field(default_factory=dict, max_length=100)
    watcher_answers: dict[str, Literal["예", "아니오", "확인불가"]] = Field(default_factory=dict, max_length=4)


class ZoneAssessmentInput(ZoneQuestionsInput):
    site_name: StrictStr = Field(min_length=1, max_length=200)
    materials: MaterialSelection = Field(default_factory=MaterialSelection)
    weather_region_id: str | None = Field(default=None, max_length=20)
    weather_token: str | None = Field(default=None, max_length=12000)
    weather_exposure: Literal["실외", "실내", "확인불가"] = "확인불가"


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
        if (os.environ.get("RENDER") or os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")) and not key:
            raise RuntimeError("배포 환경에서는 APP_ACCESS_KEY 설정이 필요합니다.")
        engine.load_databases(ROOT / "data")
        evaluation_storage.initialize(storage)
        yield

    app = FastAPI(title="화재 위험도 평가 API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "X-Access-Key"])

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

    @app.get("/api/materials", dependencies=secured)
    def material_catalogue():
        try:
            return materials.catalogue()
        except materials.MaterialDataError as error:
            raise HTTPException(503, str(error)) from error

    @app.get("/api/weather/regions", dependencies=secured)
    def weather_regions():
        return weather.CATALOGUE

    @app.get("/api/weather", dependencies=secured)
    def weather_lookup(region_id: str = Query(max_length=20)):
        try:
            return weather.fetch(region_id)
        except weather.WeatherError as error:
            raise HTTPException(503, str(error)) from None

    def blueprint_result(image, include_data=False):
        if image is None:
            return None
        result = {"현장ID": image["site_id"], "이미지ID": image["image_id"], "버전": image["version"],
                  "파일명": image["filename"], "MIME형식": image["media_type"],
                  "원본너비": image["width"], "원본높이": image["height"],
                  "원본크기바이트": image["byte_size"], "등록시각": image["created_at"],
                  "저장위치": "Postgres site_blueprint_images" if evaluation_storage.is_postgres_storage(storage)
                  else "SQLite site_blueprint_images"}
        if include_data:
            result["이미지Base64"] = base64.b64encode(image["image_data"]).decode("ascii")
        return result

    @app.get("/api/sites/{site_id}/blueprint", dependencies=secured)
    def get_site_blueprint(site_id: UUID):
        return {"조감도": blueprint_result(evaluation_storage.current_site_blueprint(storage, str(site_id)), True)}

    @app.get("/api/sites/{site_id}/blueprints/{image_id}", dependencies=secured)
    def get_site_blueprint_version(site_id: UUID, image_id: UUID):
        image = evaluation_storage.site_blueprint(storage, str(site_id), str(image_id))
        if image is None:
            raise HTTPException(404, "현장 조감도를 찾을 수 없습니다.")
        return {"조감도": blueprint_result(image, True)}

    @app.post("/api/sites/{site_id}/blueprints", dependencies=secured)
    def upload_site_blueprint(site_id: UUID, body: BlueprintUpload):
        try:
            image_data = base64.b64decode(body.data_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "이미지 데이터 인코딩이 올바르지 않습니다.") from None
        if not image_data or len(image_data) > MAX_BLUEPRINT_BYTES:
            raise HTTPException(413, "이미지 원본은 3MB 이하만 등록할 수 있습니다.")
        width, height = inspect_blueprint(image_data, body.media_type)
        filename = body.filename.replace("\\", "/").split("/")[-1].strip()
        if not filename:
            raise HTTPException(422, "이미지 파일명을 확인하세요.")
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        expected_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(extension)
        if expected_type != body.media_type:
            raise HTTPException(422, "파일 확장자와 이미지 형식이 일치하지 않습니다.")
        image = evaluation_storage.save_site_blueprint(
            storage, image_id=str(uuid4()), site_id=str(site_id), filename=filename,
            media_type=body.media_type, width=width, height=height,
            image_data=image_data, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        return {"조감도": blueprint_result(image)}

    @app.delete("/api/sites/{site_id}/blueprint", dependencies=secured)
    def delete_site_blueprint(site_id: UUID):
        return {"삭제됨": evaluation_storage.clear_current_site_blueprint(storage, str(site_id))}

    def work_zone_result(zone):
        return {"작업구역ID": zone["zone_id"], "현장ID": zone["site_id"], "이미지ID": zone["image_id"],
                "이름": zone["name"], "영역유형": "사각형", "좌표": zone["coordinates"],
                "생성시각": zone["created_at"], "수정시각": zone["updated_at"]}

    def require_site_image(site_id, image_id):
        image = evaluation_storage.site_blueprint_metadata(storage, str(site_id), str(image_id))
        if image is None:
            raise HTTPException(404, "해당 현장의 조감도 버전을 찾을 수 없습니다.")

    @app.get("/api/sites/{site_id}/blueprints/{image_id}/zones", dependencies=secured)
    def get_work_zones(site_id: UUID, image_id: UUID):
        require_site_image(site_id, image_id)
        zones = evaluation_storage.list_site_work_zones(storage, str(site_id), str(image_id))
        return {"작업구역": [work_zone_result(zone) for zone in zones]}

    @app.post("/api/sites/{site_id}/blueprints/{image_id}/zones", dependencies=secured)
    def add_work_zone(site_id: UUID, image_id: UUID, body: WorkZoneInput):
        require_site_image(site_id, image_id)
        existing = evaluation_storage.list_site_work_zones(storage, str(site_id), str(image_id))
        if any(zone["name"].casefold() == body.name.casefold() for zone in existing):
            raise HTTPException(409, "같은 이름의 작업구역이 이미 있습니다.")
        timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        zone = evaluation_storage.create_site_work_zone(
            storage, zone_id=str(uuid4()), site_id=str(site_id), image_id=str(image_id),
            name=body.name, geometry_type="rectangle", coordinates=body.coordinates.model_dump(), timestamp=timestamp,
        )
        return {"작업구역": work_zone_result(zone)}

    @app.put("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}", dependencies=secured)
    def edit_work_zone(site_id: UUID, image_id: UUID, zone_id: UUID, body: WorkZoneInput):
        require_site_image(site_id, image_id)
        existing = evaluation_storage.list_site_work_zones(storage, str(site_id), str(image_id))
        if any(zone["zone_id"] != str(zone_id) and zone["name"].casefold() == body.name.casefold() for zone in existing):
            raise HTTPException(409, "같은 이름의 작업구역이 이미 있습니다.")
        timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        updated = evaluation_storage.update_site_work_zone(
            storage, zone_id=str(zone_id), site_id=str(site_id), image_id=str(image_id),
            name=body.name, coordinates=body.coordinates.model_dump(), timestamp=timestamp,
        )
        if not updated:
            raise HTTPException(404, "작업구역을 찾을 수 없습니다.")
        return {"작업구역": {"작업구역ID": str(zone_id), "현장ID": str(site_id), "이미지ID": str(image_id),
                              "이름": body.name, "영역유형": "사각형", "좌표": body.coordinates.model_dump(),
                              "수정시각": timestamp}}

    @app.delete("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}", dependencies=secured)
    def remove_work_zone(site_id: UUID, image_id: UUID, zone_id: UUID):
        deleted = evaluation_storage.delete_site_work_zone(storage, str(zone_id), str(site_id), str(image_id))
        return {"삭제됨": deleted}

    def zone_task(task_id):
        rows = engine.tasks.loc[(engine.tasks["작업ID"] == task_id) & (engine.tasks["화재위험여부"] == "1")]
        if rows.empty or engine.get_questions_for_task(task_id).empty:
            raise ValueError("화재위험성평가 질문이 연결된 공정 DB 작업을 선택하세요.")
        return rows.iloc[0]

    def zone_schema(body):
        zone_task(body.task_id)
        table = engine.get_prework_questions(body.task_id, body.answers)
        if body.task_id != "H05":
            if body.watcher_answers:
                raise ValueError("화재감시자 추가질문은 이 작업에 연결되지 않았습니다.")
            return {"questions": frame_rows(table), "watcher_context": None, "watcher_questions": []}
        if set(body.watcher_answers) - set(engine.watcher_questions["추가질문ID"]):
            raise ValueError("알 수 없는 화재감시자 추가질문입니다.")
        return {"questions": frame_rows(table),
                "watcher_context": watcher_input.context(body.task_id, body.answers, body.watcher_answers),
                "watcher_questions": frame_rows(engine.watcher_questions[~engine.watcher_questions['추가질문ID'].isin(['W002', 'W003'])])}

    def require_zone(site_id, image_id, zone_id):
        zone = evaluation_storage.site_work_zone(storage, str(site_id), str(image_id), str(zone_id))
        if zone is None:
            raise HTTPException(404, "해당 조감도 버전의 작업구역을 찾을 수 없습니다.")
        return zone

    def zone_fingerprint(body):
        value = body.model_dump(mode="json", exclude={"site_name", "weather_region_id", "weather_token", "weather_exposure"})
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @app.get("/api/zone-tasks", dependencies=secured)
    def zone_tasks():
        return {"tasks": [{"task_id": row["작업ID"], "process": row["대공정"], "subprocess": row["세부공정"], "name": row["세부작업"]}
                          for _, row in engine.tasks.iterrows()
                          if row["화재위험여부"] == "1" and not engine.get_questions_for_task(row["작업ID"]).empty]}

    @app.post("/api/zone-questions", dependencies=secured)
    def zone_questions(body: ZoneQuestionsInput):
        return zone_schema(body)

    @app.get("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}/assessment", dependencies=secured)
    def get_zone_assessment(site_id: UUID, image_id: UUID, zone_id: UUID):
        require_zone(site_id, image_id, zone_id)
        draft = evaluation_storage.load_zone_draft(storage, str(site_id), str(image_id), str(zone_id))
        latest = evaluation_storage.latest_zone_assessment(storage, str(site_id), str(image_id), str(zone_id))
        status = "미작성" if draft is None and latest is None else "완료" if latest and (draft is None or draft.get("입력SHA256") == latest.get("입력SHA256")) else "재계산 필요" if latest else "작성 중"
        return {"초안": draft, "최근평가": latest, "입력상태": status}

    @app.get("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}/assessments", dependencies=secured)
    def zone_assessment_versions(site_id: UUID, image_id: UUID, zone_id: UUID):
        require_zone(site_id, image_id, zone_id)
        records = evaluation_storage.list_zone_assessments(storage, str(site_id), str(image_id), str(zone_id))
        return {"평가버전": [{"평가ID": record["평가ID"], "평가일시": record["평가일시"],
                           "작업ID": record["작업ID"], "위험지수": record["요약"]["위험지수"],
                           "위험수준": record["요약"]["기본위험등급(잠정)"]} for record in records]}

    def zone_reassessment_input(record):
        saved = record.get("입력조건")
        if saved:
            return saved
        watcher_answers = {}
        for row in record.get("화재감시자응답") or []:
            answer = row.get("응답")
            if row.get("추가질문ID") and answer in ("예", "아니오", "확인불가"):
                watcher_answers[row["추가질문ID"]] = answer
        material = record.get("가연물정보") or {}
        return {"site_name": record.get("현장명", ""), "task_id": record.get("작업ID", "H05"),
                "answers": record.get("응답", {}), "watcher_answers": watcher_answers,
                "materials": {"ids": [row.get("물질ID") for row in material.get("선택물질", []) if row.get("물질ID")],
                              "custom_names": [row.get("물질명") for row in material.get("직접입력", []) if row.get("물질명")],
                              "unknown": bool(material.get("종류확인필요"))},
                "weather_region_id": (record.get("현장위치") or {}).get("id"),
                "weather_exposure": record.get("기상노출", "확인불가")}

    def zone_comparison(before, after):
        if before.get("작업구역ID") != after.get("작업구역ID"):
            raise ValueError("같은 작업구역의 평가만 비교할 수 있습니다.")
        if before.get("작업ID") != after.get("작업ID"):
            from . import materials as material_module
            reason = "작업 종류가 달라 위험지수와 항목별 기여도를 직접 비교할 수 없습니다."
            return {"가연물변화": material_module.comparison(before, after),
                    "비교안내": {"점수차이표시가능": False, "위험지수차이(이후-이전)": None,
                                "변화상태": "판정 보류", "비교제한사유": reason,
                                "해석": "작업 종류가 다릅니다. 각 평가의 위험지수와 조건을 따로 확인하세요."},
                    "평가요약": [{**{k: r.get(k) for k in ("평가ID", "평가일시", "현장명", "작업ID", "작업명")},
                                  **r.get("요약", {}), "구분": label} for label, r in (("이전", before), ("이후", after))],
                    "전체항목": [], "변경항목": [], "추가응답변경": [], "화재감시자검토": []}
        return evaluation_history.compare(before, after)

    def previous_zone_record(record):
        history = evaluation_storage.list_all_zone_assessments(storage, record["현장ID"])
        candidates = [item for item in history
                      if item.get("현장ID") == record.get("현장ID")
                      and item.get("작업구역ID") == record.get("작업구역ID")
                      and item["평가ID"] != record["평가ID"]
                      and evaluation_history.order(item) < evaluation_history.order(record)]
        if not candidates:
            return None
        previous_id = record.get("이전구역평가ID")
        previous = next((item for item in candidates if item["평가ID"] == previous_id), None)
        if previous is None:
            previous = max(candidates, key=evaluation_history.order)
        return previous

    @app.get("/api/zone-assessments", dependencies=secured)
    def zone_assessment_history(site_id: UUID | None = None, site_keyword: str = Query(default="", max_length=200)):
        records = evaluation_storage.list_all_zone_assessments(storage, str(site_id) if site_id else None)
        keyword = " ".join(site_keyword.casefold().split())
        rows = []
        for record in records:
            if keyword and keyword not in " ".join(record.get("현장명", "").casefold().split()):
                continue
            summary = record.get("요약", {})
            image = record.get("현장조감도") or {}
            rows.append({"평가ID": record["평가ID"], "현장ID": record.get("현장ID"), "현장명": record.get("현장명"),
                         "이미지ID": image.get("이미지ID"), "이미지버전": image.get("버전"),
                         "작업구역ID": record.get("작업구역ID"), "작업구역명": record.get("작업구역명"),
                         "작업구역좌표": record.get("작업구역좌표"), "평가일시": record.get("평가일시"),
                         "작업ID": record.get("작업ID"), "작업명": record.get("작업명"),
                         "위험지수": summary.get("위험지수"), "위험수준": summary.get("기본위험등급(잠정)"),
                         "계산기준": [record.get("계산데이터SHA256"), record.get("엔진SHA256"), summary.get("최대가중점수")],
                         "이전구역평가ID": record.get("이전구역평가ID")})
        return {"평가이력": rows}

    @app.get("/api/zone-assessments/{evaluation_id}/previous", dependencies=secured)
    def zone_assessment_previous(evaluation_id: UUID):
        record = evaluation_storage.zone_assessment_by_id(storage, str(evaluation_id))
        if record is None:
            raise HTTPException(404, "구역 평가기록을 찾을 수 없습니다.")
        previous = previous_zone_record(record)
        return {"이전평가ID": previous["평가ID"] if previous else None,
                "comparison": zone_comparison(previous, record) if previous else None}

    @app.get("/api/zone-assessments/{evaluation_id}", dependencies=secured)
    def zone_assessment_history_detail(evaluation_id: UUID):
        record = evaluation_storage.zone_assessment_by_id(storage, str(evaluation_id))
        if record is None:
            raise HTTPException(404, "구역 평가기록을 찾을 수 없습니다.")
        return {"평가": record, "재평가입력": zone_reassessment_input(record)}

    @app.get("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}/assessments/{evaluation_id}", dependencies=secured)
    def zone_assessment_version(site_id: UUID, image_id: UUID, zone_id: UUID, evaluation_id: UUID):
        require_zone(site_id, image_id, zone_id)
        record = next((item for item in evaluation_storage.list_zone_assessments(storage, str(site_id), str(image_id), str(zone_id))
                       if item["평가ID"] == str(evaluation_id)), None)
        if record is None:
            raise HTTPException(404, "작업구역 평가기록을 찾을 수 없습니다.")
        return {"평가": record, "재평가입력": zone_reassessment_input(record)}

    @app.put("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}/assessment", dependencies=secured)
    def save_zone_assessment_draft(site_id: UUID, image_id: UUID, zone_id: UUID, body: ZoneAssessmentInput):
        require_zone(site_id, image_id, zone_id)
        zone_schema(body)
        draft = {**body.model_dump(mode="json"), "현장ID": str(site_id), "이미지ID": str(image_id),
                 "작업구역ID": str(zone_id), "입력SHA256": zone_fingerprint(body),
                 "수정시각": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
        evaluation_storage.save_zone_draft(storage, str(site_id), str(image_id), str(zone_id), draft, draft["수정시각"])
        latest = evaluation_storage.latest_zone_assessment(storage, str(site_id), str(image_id), str(zone_id))
        return {"초안": draft, "입력상태": "완료" if latest and latest.get("입력SHA256") == draft["입력SHA256"] else "재계산 필요" if latest else "작성 중"}

    @app.post("/api/sites/{site_id}/blueprints/{image_id}/zones/{zone_id}/evaluate", dependencies=secured)
    def evaluate_zone(site_id: UUID, image_id: UUID, zone_id: UUID, body: ZoneAssessmentInput):
        zone = require_zone(site_id, image_id, zone_id)
        task = zone_task(body.task_id)
        table = engine.get_prework_questions(body.task_id, body.answers)
        active = set(table.loc[table["적용상태"].eq("적용"), "항목ID"])
        answers = {qid: value for qid, value in body.answers.items() if qid in active}
        if answers.get("Q003") == "해당없음" or (body.task_id != "H05" and answers.get("Q004") == "해당없음"):
            raise ValueError("Q003·Q004의 해당없음 근거는 아직 자동 검증하지 않습니다. 계산을 보류합니다.")
        watcher_answers = None
        if body.task_id == "H05":
            zone_schema(body)
            watcher_answers = dict(body.watcher_answers)
            for wid, qid in (("W002", "Q019"), ("W003", "Q020")):
                watcher_answers[wid] = {"있음": "예", "없음": "아니오", "확인불가": "확인불가"}.get(answers.get(qid), "확인불가")
        elif body.watcher_answers:
            raise ValueError("화재감시자 추가질문은 이 작업에 연결되지 않았습니다.")
        previous = evaluation_storage.latest_zone_assessment(storage, str(site_id), str(image_id), str(zone_id))
        identifier = str(uuid4())
        builder = watcher_input.build if body.task_id == "H05" else engine.build_evaluation
        record = builder(body.site_name, body.task_id, answers, watcher_answers,
                         evaluation_id=identifier, evaluated_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"))
        image = evaluation_storage.site_blueprint_metadata(storage, str(site_id), str(image_id))
        record.update({"현장ID": str(site_id), "작업구역ID": str(zone_id), "작업구역명": zone["name"],
                       "작업구역좌표": zone["coordinates"],
                       "현장조감도": blueprint_result(image), "작업명": task["세부작업"],
                       "대공정": task["대공정"], "세부공정": task["세부공정"],
                       "화재위험지수": record["요약"]["위험지수"],
                       "위험수준": record["요약"]["기본위험등급(잠정)"],
                       "점수계산기준": {"계산데이터SHA256": record["계산데이터SHA256"], "엔진SHA256": record["엔진SHA256"]},
                       "입력SHA256": zone_fingerprint(body),
                       "입력조건": {"site_name": body.site_name, "task_id": body.task_id,
                                   "answers": body.answers, "watcher_answers": body.watcher_answers,
                                   "materials": body.materials.model_dump(),
                                   "weather_region_id": body.weather_region_id,
                                   "weather_exposure": body.weather_exposure},
                       "이전구역평가ID": previous["평가ID"] if previous else None,
                       "근거스냅샷": {"standards": frame_rows(engine.standards), "accidents": frame_rows(engine.accidents)}})
        if body.weather_region_id:
            record["현장위치"] = weather.region(body.weather_region_id)
            record["기상정보"] = weather.restore(body.weather_token, body.weather_region_id)
            record["기상조건검토"] = weather_risk.assess(record["기상정보"], str(task["위험작업군"]), answers, body.weather_exposure)
        try:
            record["가연물정보"] = materials.snapshot(answers, body.materials.model_dump())
        except materials.MaterialDataError as error:
            raise HTTPException(503, str(error)) from error
        save_zone_assessment_draft(site_id, image_id, zone_id, body)
        evaluation_storage.save_zone_assessment(storage, str(site_id), str(image_id), str(zone_id), record)
        return {"평가": record, "입력상태": "완료"}

    @app.post("/api/questions", dependencies=secured)
    def questions(body: QuestionInput):
        return {"questions": frame_rows(engine.get_prework_questions(body.task_id, body.answers)),
                "watcher_context": watcher_input.context(body.task_id, body.answers, body.watcher_answers),
                "watcher_questions": frame_rows(engine.watcher_questions[~engine.watcher_questions['추가질문ID'].isin(['W002', 'W003'])])}

    @app.post("/api/evaluate", dependencies=secured)
    def evaluate(body: EvaluationInput):
        fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode="json", exclude={"request_id"}), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        identifier = str(body.request_id) if body.request_id else None
        if identifier and evaluation_storage.saved_exists(storage, identifier):
            existing = engine.load_evaluation(identifier, storage)
            if existing.get("평가요청SHA256") != fingerprint:
                raise HTTPException(409, "동일 요청 ID의 입력이 다릅니다. 새 평가를 진행하세요.")
            return existing
        table = engine.get_prework_questions(body.task_id, body.answers)
        active = set(table.loc[table["적용상태"].eq("적용"), "항목ID"])
        answers = {qid: value for qid, value in body.answers.items() if qid in active}
        if answers.get("Q003") == "해당없음" or (not body.watcher_ui_version and answers.get("Q004") == "해당없음"):
            raise ValueError("Q003·Q004의 해당없음 근거는 아직 자동 검증하지 않습니다. 계산을 보류합니다. 실제 상태와 다르게 응답을 바꾸지 마세요.")
        if set(body.watcher_answers) - set(engine.watcher_questions["추가질문ID"]):
            raise ValueError("알 수 없는 화재감시자 추가질문입니다.")
        watcher_answers = dict(body.watcher_answers)
        # Q019/Q020 cover the same conditions. Always prefer the current Q response,
        # including unknown, over potentially stale values from older clients.
        for wid, qid in (("W002", "Q019"), ("W003", "Q020")):
            watcher_answers[wid] = {"있음": "예", "없음": "아니오", "확인불가": "확인불가"}.get(answers.get(qid), "확인불가")
        builder = watcher_input.build if body.watcher_ui_version else engine.build_evaluation
        record = builder(body.site_name, body.task_id, answers, watcher_answers,
                                         evaluation_id=identifier, evaluated_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"))
        record["평가요청SHA256"] = fingerprint
        if body.site_id:
            record["현장ID"] = str(body.site_id)
        if body.blueprint_image_id:
            if not body.site_id:
                raise ValueError("조감도를 평가기록에 연결하려면 현장 ID가 필요합니다.")
            image = evaluation_storage.site_blueprint_metadata(storage, str(body.site_id), str(body.blueprint_image_id))
            if image is None:
                raise ValueError("선택한 조감도가 해당 현장에 등록되어 있지 않습니다.")
            record["현장조감도"] = blueprint_result(image)
        record["작업명"] = record["요약"].get("작업명") or next((r.get("세부작업") for r in frame_rows(engine.tasks) if r["작업ID"] == body.task_id), body.task_id)
        record["근거스냅샷"] = {"standards": frame_rows(engine.standards), "accidents": frame_rows(engine.accidents)}
        if body.region_id:
            record["현장위치"] = weather.region(body.region_id)
            record["기상정보"] = weather.restore(body.weather_token, body.region_id)
            task_rows = engine.tasks.loc[engine.tasks["작업ID"] == body.task_id]
            task_group = str(task_rows.iloc[0]["위험작업군"]) if not task_rows.empty else ""
            record["기상조건검토"] = weather_risk.assess(
                record["기상정보"], task_group, answers, body.weather_exposure
            )
            if record["기상정보"] is None:
                record["기상정보안내"] = "평가 당시 저장된 기상정보가 없습니다."
        if body.materials is not None:
            try:
                record["가연물정보"] = materials.snapshot(answers, body.materials.model_dump())
            except materials.MaterialDataError as error:
                raise HTTPException(503, str(error)) from error
        engine.save_evaluation(record, storage)
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
        return evaluation_history.history(storage, site_keyword)

    @app.get("/api/evaluations/{evaluation_id}/previous", dependencies=secured)
    def previous(evaluation_id: str):
        return {"comparison": evaluation_history.previous_comparison(engine.load_evaluation(evaluation_id, storage), storage)}

    @app.get("/api/evaluations/{evaluation_id}", dependencies=secured)
    def detail(evaluation_id: str):
        return engine.load_evaluation(evaluation_id, storage)

    @app.post("/api/compare", dependencies=secured)
    def compare(body: Comparison):
        return evaluation_history.compare(engine.load_evaluation(body.before_id, storage), engine.load_evaluation(body.after_id, storage))

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
                           "grade": grade,
                           "group": [record.get("계산데이터SHA256"), record.get("엔진SHA256"), summary["최대가중점수"]]})
        return {"sites": sites, "count": len(records), "site_count": history["현장명"].nunique(),
                "held_count": sum(r["요약"]["최종판정"].startswith("보류") for r in records),
                "grades": grades, "trends": trends}

    return app


app = create_app()
