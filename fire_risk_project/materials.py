"""Read existing MSDS rows and persist evidence snapshots, without scoring materials."""
import csv
from datetime import datetime, timedelta
import hashlib
import io
from pathlib import Path

MSDS_PATH = Path(__file__).resolve().parent / "data/05_MSDS_물질DB.csv"
REQUIRED = {"물질ID", "제품명", "제조사", "용도", "GHS인화성구분", "인화점_기준값℃", "LEL%", "UEL%",
            "자연발화온도℃", "증기압", "증기압단위", "CAS_No", "점화원주의", "물성근거URL", "확인일자", "비고",
            "적용작업ID", "인화점_연산자", "인화점_원문", "근거유형"}


class MaterialDataError(ValueError):
    pass


def classify(row):
    classification = row["GHS인화성구분"].replace(" ", "")
    if "비인화성" in classification:
        return "선택 제외"
    if classification in {"가연성가스", "가연성고체", "인화성고체", "인화성액체", "인화성액체구분1", "인화성액체구분2", "인화성액체구분3", "인화성액체구분4"}:
        return "분류 확인"
    return "분류 확인 필요"


def catalogue(path=None):
    try:
        raw = Path(path or MSDS_PATH).read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames or REQUIRED - set(reader.fieldnames):
            raise ValueError("필수 컬럼 누락")
        rows, ids = [], set()
        for source in reader:
            if None in source or any(value is None for value in source.values()):
                raise ValueError("행 컬럼 수 불일치")
            row = {key: value.strip() for key, value in source.items()}
            if not row["물질ID"] or not row["제품명"] or row["물질ID"] in ids:
                raise ValueError("물질 ID/이름 누락 또는 중복")
            ids.add(row["물질ID"])
            row["선택분류"] = classify(row)
            reasons = []
            if row["선택분류"] == "분류 확인 필요":
                reasons.append("등록된 분류만으로 가연성을 확정할 수 없음")
            if not row["물성근거URL"]:
                reasons.append("출처 미등록")
            if row["근거유형"] != "제조사 SDS":
                reasons.append("실제 현장제품의 공급사 SDS 확인 필요")
            row["확인필요사유"] = reasons
            row["확인일자_표시"] = row["확인일자"]
            if row["확인일자"].isdigit():
                row["확인일자_표시"] = (datetime(1899, 12, 30) + timedelta(days=int(row["확인일자"]))).date().isoformat()
            rows.append(row)
        if not rows:
            raise ValueError("자료 없음")
        return {"rows": rows, "source": MSDS_PATH.name, "sha256": hashlib.sha256(raw).hexdigest()}
    except (OSError, UnicodeError, csv.Error, ValueError, OverflowError) as error:
        raise MaterialDataError("MSDS DB를 읽을 수 없습니다. 자료 파일과 필수 컬럼을 확인하세요.") from error


def snapshot(answers, selection):
    presence = answers.get("Q001")
    result = {"버전": 1, "존재여부": presence, "거리m": answers.get("Q002") if presence == "있음" else None,
              "선택물질": [], "직접입력": [], "종류확인필요": False, "확인필요수": 0,
              "DB출처": MSDS_PATH.name, "DB_SHA256": None, "DB상태": "조회 대상 아님", "점수반영": False}
    if presence != "있음":
        return result  # Never save or score stale hidden material inputs.
    identifiers = selection["ids"]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("같은 물질을 중복 선택할 수 없습니다.")
    names = [" ".join(name.split()) for name in selection["custom_names"]]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("직접 입력 물질명이 비었거나 중복되었습니다.")
    if not identifiers and not names and not selection["unknown"]:
        raise ValueError("주변 가연물 종류를 선택하거나 직접 입력 또는 '가연물 종류 확인 필요'를 선택하세요.")
    try:
        data = catalogue()
    except MaterialDataError:
        if identifiers:
            raise
        data = None
        result["DB상태"] = "조회 실패 · MSDS 확인 필요"
    if data:
        result.update({"DB_SHA256": data["sha256"], "DB상태": "조회 완료"})
        lookup = {r["물질ID"]: r for r in data["rows"]}
        for identifier in identifiers:
            if identifier not in lookup:
                raise ValueError("MSDS DB에 없는 물질 ID입니다: " + identifier)
            row = lookup[identifier]
            if row["선택분류"] == "선택 제외":
                raise ValueError(row["제품명"] + ": DB상 비인화성 물질은 가연물로 선택할 수 없습니다.")
            result["선택물질"].append(row)
    result["직접입력"] = [{"물질명": name, "MSDS확인": "미확인"} for name in names]
    result["종류확인필요"] = selection["unknown"]
    result["확인필요수"] = sum(bool(r["확인필요사유"]) for r in result["선택물질"]) + len(names) + int(selection["unknown"])
    return result


def comparison(before, after):
    """Describe material changes independently of the numeric risk comparison."""
    a, b = before.get("가연물정보"), after.get("가연물정보")
    def describe(info):
        if info is None:
            return {"기록상태": "당시 물질 종류 정보 미기록"}
        return {"기록상태": "기록됨", "존재여부": info["존재여부"], "거리m": info["거리m"],
                "물질명": [r["제품명"] for r in info["선택물질"]] + [r["물질명"] for r in info["직접입력"]],
                "종류확인필요": info["종류확인필요"], "확인필요수": info["확인필요수"]}
    def identity(info):
        return (sorted(r["물질ID"] for r in info["선택물질"]), sorted(r["물질명"] for r in info["직접입력"]), info["종류확인필요"])
    return {"이전": describe(a), "현재": describe(b),
            "종류변경": identity(a) != identity(b) if a is not None and b is not None else None,
            "확인완료변경": bool(a and b and a["확인필요수"] and b["존재여부"] == "있음" and not b["확인필요수"]),
            "안내": "물질 선택·확인 상태의 변화이며 물질명 변경만으로 위험 개선·악화를 판정하지 않습니다."}
