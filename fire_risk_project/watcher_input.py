"""Integrated Q004/W004 input adapter. Existing scoring engine/CSV rules stay intact."""
from . import risk_engine as engine

VERSION = "integrated-v1"


def context(task_id, answers, extras):
    """Only determine whether exception review is relevant, never approve an exemption."""
    supported = task_id == "H05" and "R002" in engine.get_question("Q004")["연결기준ID"].split(";")
    nearby = answers.get("Q001")
    distance = answers.get("Q002")
    if nearby == "없음":
        proximity = False
    elif nearby == "있음" and isinstance(distance, (int, float)) and not isinstance(distance, bool) and distance >= 0:
        proximity = distance <= 11
    else:
        proximity = None
    checks = {"Q002": proximity, "W001": {"예": True, "아니오": False}.get(extras.get("W001"))}
    checks.update({qid: {"있음": True, "없음": False}.get(answers.get(qid)) for qid in ("Q019", "Q020")})
    flags = list(checks.values())
    state = "해당 응답 있음" if True in flags else "확인 필요" if None in flags else "입력상 비해당"
    return {"supported": supported, "exception_required": supported and state != "입력상 비해당",
            "place_status": state, "standard_id": "R002",
            "matched_ids": [key for key, value in checks.items() if value is True],
            "unknown_ids": [key for key, value in checks.items() if value is None]}


def build(site, task_id, answers, extras, **kwargs):
    deployment = answers.get("Q004")
    if deployment not in ("배치", "미배치", "해당없음", "확인불가"):
        raise ValueError("화재감시자 배치 상태를 선택하세요.")
    conditions = context(task_id, answers, extras)
    if not conditions["supported"]:
        raise ValueError("이 작업에는 통합 화재감시자 입력이 연결되지 않았습니다.")
    if extras.get("W001") not in ("예", "아니오", "확인불가"):
        raise ValueError("화재감시자 장소조건을 선택하세요.")
    exception = extras.get("W004") if conditions["exception_required"] else None
    if conditions["exception_required"] and exception not in ("예", "아니오", "확인불가"):
        raise ValueError("화재감시자 예외조건 적용 여부를 선택하세요.")
    hold = deployment in ("해당없음", "확인불가")
    scoring_answers = {**answers, "Q004": "해당없음" if hold else deployment}
    # Validate and calculate all other items using the unchanged engine. Its N/A
    # placeholder is never exposed: unsupported deployment scores/totals are
    # explicitly cleared below before any save or response.
    record = engine.build_evaluation(site, task_id, scoring_answers,
                                     {**extras, "W004": exception or "확인불가"}, **kwargs)
    record["응답"]["Q004"] = deployment
    record["화재감시자입력"] = {"버전": VERSION, "배치상태": deployment,
                              "예외조건응답": exception, "예외질문표시": conditions["exception_required"]}
    if hold:
        reason = "화재감시자 배치 대상 여부의 근거 미검증" if deployment == "해당없음" else "화재감시자 실제 배치 상태 미확인"
        row = next(r for r in record["응답상세"] if r["항목ID"] == "Q004")
        row.update({"사용자응답": deployment, "점수": None, "가중치": None, "가중점수": None,
                    "최대가중점수": None, "조건순번": "", "점수합산대상": False, "집계대표여부": False,
                    "확정상태": "점수미산정", "응답상태": "확인필요", "계산보류사유": reason})
        record["요약"].update({"총가중위험점수": None, "최대가중점수": None, "위험지수": None,
                            "기본위험등급(잠정)": "확인필요", "계산상태": "계산 보류: " + reason})
    for row in record["화재감시자응답"]:
        if row["추가질문ID"] == "W004":
            row["응답"] = exception
            row["적용상태"] = "적용" if conditions["exception_required"] else "질문대상아님"
    if not conditions["exception_required"]:
        exception_status = "예외 검토 대상 아님: 입력상 장소조건 비해당"
    elif exception == "예":
        exception_status = "예외조건 충족 응답 · 근거 확인 필요"
    elif exception == "아니오":
        exception_status = "예외조건 미충족 응답"
    else:
        exception_status = "예외조건 확인 필요"
    if deployment == "해당없음":
        status = "배치 대상 아님 응답 · 근거 확인 필요"
        if conditions["place_status"] == "해당 응답 있음":
            status = "배치 대상 아님 응답과 장소조건 충돌 · 확인 필요"
    elif deployment == "확인불가":
        status = "실제 배치 상태 확인 필요"
    elif conditions["place_status"] == "입력상 비해당":
        status = "배치 대상 비해당 후보 · 현장 근거 확인 필요"
    elif exception != "아니오":
        status = "예외 적용 근거 확인 필요"
    elif conditions["place_status"] == "확인 필요":
        status = "배치 의무 적용 여부 확인 필요"
    else:
        status = "배치 대상 조건 해당 · 미배치" if deployment == "미배치" else "배치 대상 조건 해당 · 배치 응답 확인"
    message = f"{status}. {exception_status}. "
    if exception == "예":
        message += "상시·반복 작업 및 필요한 설비의 구비 여부를 현재 입력만으로 검증할 수 없어 예외를 승인하거나 감점하지 않습니다. "
    if hold:
        message += "해당 항목을 안전한 0점으로 처리하지 않고 위험지수 산정을 보류합니다. "
    message += "현장 근거와 나머지 법령 적용요건 확인 전에는 최종판정을 보류합니다."
    record["화재감시자검토"].update({"Q004응답": deployment, "장소조건검토": conditions["place_status"],
                                  "해당조건ID": ", ".join(conditions["matched_ids"]) or "-",
                                  "미확인조건ID": ", ".join(conditions["unknown_ids"]) or "-",
                                  "응답비교결과": status, "검토결과": exception_status,
                                  "확인메시지": message, "해당없음자동승인": False,
                                  "예외조건검증완료": False})
    return record
