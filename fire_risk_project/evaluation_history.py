"""Read-only snapshot comparison; no recalculation or changes to scoring rules."""
from datetime import datetime
import math
import json

from . import risk_engine as engine
from . import materials


def site_key(record):
    return ("id", record["현장ID"]) if record.get("현장ID") else ("name", " ".join(record.get("현장명", "").split()))


def order(record):
    return datetime.fromisoformat(record["평가일시"]), record["평가ID"]


def history(storage, keyword=""):
    # Pandas promotes missing numeric scores to NaN in mixed scored/held history.
    # JSON conversion preserves them as null, which strict HTTP JSON requires.
    rows = json.loads(engine.search_evaluations(storage, site_keyword=keyword).to_json(orient="records", force_ascii=False))
    for row in rows:
        record = engine.load_evaluation(row["평가ID"], storage)
        row["작업명"] = record.get("작업명") or record.get("요약", {}).get("작업명") or "작업명 자료 없음"
    return rows


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compare(before, after):
    if before["평가ID"] == after["평가ID"]:
        raise ValueError("서로 다른 평가ID 두 개를 선택하세요.")
    if site_key(before) != site_key(after) or before["작업ID"] != after["작업ID"]:
        raise ValueError("같은 현장·작업의 평가만 비교할 수 있습니다.")
    if order(before)[0] > order(after)[0]:
        raise ValueError("이전 평가가 이후 평가보다 늦습니다.")
    a, b = before.get("요약", {}), after.get("요약", {})
    reasons = []
    for key in ("계산데이터SHA256", "엔진SHA256"):
        if not before.get(key) or before.get(key) != after.get(key):
            reasons.append(key + " 불일치 또는 누락")
    for key in ("평가시점", "최대가중점수"):
        if a.get(key) is None or b.get(key) is None or a[key] != b[key]:
            reasons.append(key + " 불일치 또는 누락")
    if not all(numeric(s.get("위험지수")) for s in (a, b)):
        reasons.append("위험지수 미산정")
    left = {r["항목ID"]: r for r in before.get("응답상세", [])}
    right = {r["항목ID"]: r for r in after.get("응답상세", [])}
    if not left or left.keys() != right.keys():
        reasons.append("질문 구성 불일치 또는 상세자료 누락")
    comparable = not reasons
    fields = ("사용자응답", "가중점수", "최대가중점수", "적용상태", "집계대표여부")
    rows, changes = [], []
    for qid in sorted(left.keys() | right.keys()):
        old, new = left.get(qid, {}), right.get(qid, {})
        row = {"항목ID": qid, "확인항목": new.get("확인항목", old.get("확인항목", qid))}
        for prefix, detail in (("이전_", old), ("이후_", new)):
            row.update({prefix + key: detail.get(key) for key in fields})
            if detail.get("적용상태") != "적용":
                row[prefix + "가중점수"] = None
        def measured(detail):
            return (detail.get("적용상태") == "적용" and detail.get("집계대표여부") is True
                    and detail.get("사용자응답") not in (None, "", "확인불가", "해당없음")
                    and numeric(detail.get("가중점수")))
        delta = None
        state = "비교 불가·확인 필요"
        if comparable and measured(old) and measured(new):
            delta = new["가중점수"] - old["가중점수"]
            state = "개선" if delta < 0 else "변화 없음" if delta == 0 else "새롭게 발생" if old["가중점수"] == 0 else "악화"
        elif comparable and old.get("적용상태") in ("조건제외", "시점제외") and old.get("적용상태") == new.get("적용상태"):
            state = "평가 제외 유지"
        row.update({"변화분류": state, "기여도차이": delta,
                    "추가개선필요": measured(new) and new["가중점수"] > 0})
        rows.append(row)
        if not old or not new or any(old.get(k) != new.get(k) for k in fields):
            changes.append(row)
    delta = round(b["위험지수"] - a["위험지수"], 10) if comparable else None
    extras_a = {r["추가질문ID"]: r.get("응답") for r in before.get("화재감시자응답") or []}
    extras_b = {r["추가질문ID"]: r.get("응답") for r in after.get("화재감시자응답") or []}
    return {
        "가연물변화": materials.comparison(before, after),
        "비교안내": {"점수차이표시가능": comparable, "위험지수차이(이후-이전)": delta,
                 "변화상태": "판정 보류" if delta is None else "개선" if delta < 0 else "악화" if delta > 0 else "변화 없음",
                 "비교제한사유": "; ".join(reasons) or "없음",
                 "해석": "저장 당시 점수규칙에 따른 위험지수 변화입니다. 화재 발생확률이나 안전·조치 완료를 뜻하지 않습니다."},
        "평가요약": [{**{k: r.get(k) for k in ("평가ID", "평가일시", "현장명", "작업ID", "작업명")},
                   **r.get("요약", {}), "구분": label} for label, r in (("이전", before), ("이후", after))],
        "전체항목": rows, "변경항목": changes,
        "추가응답변경": [{"추가질문ID": k, "이전응답": extras_a.get(k), "이후응답": extras_b.get(k)}
                     for k in sorted(extras_a.keys() | extras_b.keys()) if extras_a.get(k) != extras_b.get(k)],
        "화재감시자검토": [{"구분": label, **(r.get("화재감시자검토") or {})} for label, r in (("이전", before), ("이후", after))],
    }


def previous_comparison(record, storage):
    candidates = []
    for row in engine.search_evaluations(storage, task_id=record["작업ID"]).to_dict("records"):
        if row["평가ID"] == record["평가ID"]:
            continue
        candidate = engine.load_evaluation(row["평가ID"], storage)
        if site_key(candidate) == site_key(record) and order(candidate) < order(record):
            candidates.append(candidate)
    if not candidates:
        return None
    return compare(max(candidates, key=order), record)
