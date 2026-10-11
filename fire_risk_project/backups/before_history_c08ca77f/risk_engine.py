"""03번 노트북에서 분리한 계산 함수. 점수 계산 전 load_databases() 호출 필요.
화재감시자 추가 응답 검토는 CSV 없이 사용 가능. 최종 안전판정은 미구현.
"""
import json
import math
from pathlib import Path
from collections.abc import Mapping
import pandas as pd
from pandas.api.types import is_scalar, is_bool
data_dir = None
def find_data_dir():
    return Path(__file__).resolve().parent / "data"

def read_database(filename):
    table = pd.read_csv(
        data_dir / filename, encoding="utf-8-sig",
        dtype=str, keep_default_na=False,
    )
    # ID와 선택지 양끝의 불필요한 공백만 정리합니다.
    return table.apply(lambda column: column.str.strip())

def split_ids(value):
    return [item.strip() for item in value.split(";") if item.strip()]

def is_missing(value):
    if not is_scalar(value):
        raise ValueError("응답은 목록이나 사전이 아닌 단일 값이어야 합니다.")
    return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())

def to_number(value, label):
    if is_bool(value) or is_missing(value):
        raise ValueError(f"{label}: 숫자가 필요합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}: 숫자로 변환할 수 없습니다.") from None
    if not math.isfinite(number):
        raise ValueError(f"{label}: 유한한 숫자가 필요합니다.")
    return number

def read_flag(value, label):
    number = to_number(value, label)
    if number not in (0, 1):
        raise ValueError(f"{label}: 0 또는 1이어야 합니다.")
    return number == 1

def get_single_row(table, label):
    if len(table) != 1:
        raise ValueError(f"{label}: 해당 행이 없거나 중복됩니다.")
    return table.iloc[0]

def get_question(question_id):
    question_id = str(question_id).strip()
    return get_single_row(
        questions.loc[questions["항목ID"] == question_id],
        f"질문 {question_id}",
    )

def get_rules(rule_id):
    result = score_rules.loc[score_rules["점수규칙ID"] == rule_id]
    if result.empty:
        raise ValueError(f"존재하지 않는 점수규칙: {rule_id}")
    return result

def matches_numeric_rule(number, rule):
    operator = rule["비교연산자"]
    lower = to_number(rule["기준값1"], "기준값1")

    if operator == "<":
        return number < lower
    if operator == "<=":
        return number <= lower
    if operator == ">":
        return number > lower
    if operator == ">=":
        return number >= lower
    if operator == "EQ":
        return number == lower
    if operator == "구간":
        upper = to_number(rule["기준값2"], "기준값2")
        if lower > upper:
            raise ValueError("구간의 하한이 상한보다 큽니다.")
        lower_included = read_flag(rule["하한포함"], "하한포함")
        upper_included = read_flag(rule["상한포함"], "상한포함")
        lower_ok = number >= lower if lower_included else number > lower
        upper_ok = number <= upper if upper_included else number < upper
        return lower_ok and upper_ok
    raise NotImplementedError(f"지원하지 않는 비교연산자: {operator}")

def build_score_result(question, answer, rule):
    score = to_number(rule["점수"], "점수")
    weight = to_number(rule["가중치"], "가중치")
    maximum = to_number(rule["정규화최대점수"], "정규화최대점수")
    if maximum <= 0 or weight < 0 or not 0 <= score <= maximum:
        raise ValueError("점수·가중치·정규화 기준의 범위를 확인하세요.")

    included = weight > 0
    evidence = list(dict.fromkeys(
        split_ids(question["연결기준ID"]) + split_ids(rule["근거ID"])
    ))
    return {
        "항목ID": question["항목ID"],
        "확인항목": question["확인항목"],
        "사용자응답": answer,
        "단위": question["단위"],
        "점수규칙ID": rule["점수규칙ID"],
        "조건순번": rule["조건순번"],
        "점수": score,
        "가중치": weight,
        "가중점수": score * weight if included else 0.0,
        "최대가중점수": maximum * weight if included else 0.0,
        "점수합산대상": included,
        "중복집계그룹": question["중복집계그룹"],
        "그룹집계방식": question["그룹집계방식"],
        "관련기준ID": ";".join(evidence),
        "적용조건": rule["적용조건"],
        "확정상태": rule["확정상태"],
    }

def validate_databases():
    requirements = [
        (tasks, ["작업ID"]),
        (questions, ["항목ID", "적용작업ID", "확인항목", "입력형식",
                     "선택지·허용값", "단위", "필수여부", "점수규칙ID",
                     "연결기준ID", "중복집계그룹", "그룹집계방식"]),
        (score_rules, ["점수규칙ID", "조건순번", "규칙유형", "입력값·조건",
                       "비교연산자", "기준값1", "기준값2", "점수", "가중치",
                       "정규화최대점수", "하한포함", "상한포함",
                       "근거ID", "적용조건", "확정상태"]),
        (standards, ["기준ID"]),
    ]
    for table, columns in requirements:
        missing = set(columns) - set(table.columns)
        if missing:
            raise ValueError(f"필수 컬럼 누락: {sorted(missing)}")
    for table, key in [(tasks, "작업ID"), (questions, "항목ID"), (standards, "기준ID")]:
        if table[key].eq("").any() or table[key].duplicated().any():
            raise ValueError(f"{key}: 빈값 또는 중복")

    sequences = score_rules["조건순번"].map(lambda x: to_number(x, "조건순번"))
    if not sequences.map(lambda x: x >= 1 and x.is_integer()).all():
        raise ValueError("조건순번은 1 이상의 정수여야 합니다.")
    rule_keys = list(zip(score_rules["점수규칙ID"], sequences))
    if score_rules["점수규칙ID"].eq("").any() or len(set(rule_keys)) != len(rule_keys):
        raise ValueError("규칙ID가 비었거나 규칙ID+조건순번이 중복됩니다.")

    task_ids = set(tasks["작업ID"])
    rule_ids = set(score_rules["점수규칙ID"])
    standard_ids = set(standards["기준ID"])
    for _, question in questions.iterrows():
        if not split_ids(question["적용작업ID"]):
            raise ValueError(f"{question['항목ID']}: 적용작업ID 누락")
        if set(split_ids(question["적용작업ID"])) - task_ids:
            raise ValueError(f"{question['항목ID']}: 연결된 작업ID 오류")
        if question["점수규칙ID"] not in rule_ids:
            raise ValueError(f"{question['항목ID']}: 연결된 점수규칙ID 오류")
        if set(split_ids(question["연결기준ID"])) - standard_ids:
            raise ValueError(f"{question['항목ID']}: 연결된 기준ID 오류")
        read_flag(question["필수여부"], "필수여부")
        if not question["중복집계그룹"] or question["그룹집계방식"] != "MAX_PER_TASK":
            raise ValueError(f"{question['항목ID']}: 중복집계 설정 오류")

    for _, rule in score_rules.iterrows():
        if set(split_ids(rule["근거ID"])) - standard_ids:
            raise ValueError(f"{rule['점수규칙ID']}: 근거ID 오류")
    print("DB의 기본 연결·중복·집계 설정 검사 통과")

def get_questions_for_task(task_id):
    task_id = str(task_id).strip()
    get_single_row(tasks.loc[tasks["작업ID"] == task_id], f"작업 {task_id}")
    applies = questions["적용작업ID"].map(lambda value: task_id in split_ids(value))
    return questions.loc[applies].copy().reset_index(drop=True)

def score_answer(question_id, answer):
    question = get_question(question_id)
    if is_missing(answer):
        raise ValueError(f"{question['항목ID']}: 응답이 비었습니다.")
    rules = get_rules(question["점수규칙ID"])

    if question["입력형식"] == "선택":
        answer = str(answer).strip()
        allowed = [value.strip() for value in question["선택지·허용값"].split("/")]
        if answer not in allowed:
            raise ValueError(f"{question['항목ID']} 허용 응답: {allowed}")
        if not ((rules["규칙유형"] == "범주형") & (rules["비교연산자"] == "EQ")).all():
            raise ValueError("선택형 질문의 규칙유형·연산자를 확인하세요.")
        matched = rules.loc[rules["입력값·조건"] == answer]

    elif question["입력형식"] == "숫자":
        if "/" in question["단위"] or not rules["적용대상"].eq("02_위험요인").all():
            raise NotImplementedError("단위 환산·MSDS 파생변수 계산이 먼저 필요합니다.")
        answer = to_number(answer, question["확인항목"])
        if question["선택지·허용값"] != "0 이상":
            raise NotImplementedError("지원하지 않는 숫자 입력 제한입니다.")
        if answer < 0:
            raise ValueError("0 이상의 숫자를 입력하세요.")
        if not rules["규칙유형"].isin(["수치형", "범위형"]).all():
            raise ValueError("숫자형 질문의 규칙유형을 확인하세요.")
        mask = rules.apply(lambda rule: matches_numeric_rule(answer, rule), axis=1)
        matched = rules.loc[mask]
    else:
        raise NotImplementedError(f"지원하지 않는 입력형식: {question['입력형식']}")

    rule = get_single_row(matched, f"{question['점수규칙ID']} 응답 {answer}")
    return build_score_result(question, answer, rule)

def normalize_answers(answers):
    if not isinstance(answers, Mapping):
        raise ValueError("응답은 {질문ID: 응답} 형식의 사전이어야 합니다.")
    normalized = {}
    for key, value in answers.items():
        key = str(key).strip()
        if not key or key in normalized:
            raise ValueError(f"빈 질문ID 또는 공백 정리 후 중복된 질문ID: {key}")
        if not is_scalar(value):
            raise ValueError(f"{key}: 단일 응답값이 필요합니다.")
        normalized[key] = value
    return normalized

def get_prework_policy(question_id, task_id):
    policies = prework_policies.loc[prework_policies["항목ID"] == question_id]
    specific = policies.loc[
        policies["적용작업ID"].map(lambda value: task_id in split_ids(value))
    ]
    if not specific.empty:
        return get_single_row(specific, f"{task_id}/{question_id} 사전평가 설정")
    return get_single_row(
        policies.loc[policies["적용작업ID"] == "*"],
        f"{question_id} 기본 사전평가 설정",
    )

def validate_prework_policies():
    required_columns = [
        "항목ID", "적용작업ID", "사전평가사용", "사전확인항목",
        "사전안내", "제외조건_JSON", "설정상태",
    ]
    if set(required_columns) - set(prework_policies.columns):
        raise ValueError("사전평가 설정 CSV의 필수 컬럼이 없습니다.")
    question_ids = set(questions["항목ID"])
    if set(prework_policies["항목ID"]) != question_ids:
        raise ValueError("사전평가 설정과 질문ID 목록이 일치하지 않습니다.")
    for _, policy in prework_policies.iterrows():
        read_flag(policy["사전평가사용"], "사전평가사용")
        question = get_question(policy["항목ID"])
        if policy["적용작업ID"] != "*":
            if not split_ids(policy["적용작업ID"]) or (
                set(split_ids(policy["적용작업ID"])) - set(split_ids(question["적용작업ID"]))
            ):
                raise ValueError("사전평가 설정의 적용작업ID를 확인하세요.")
        condition_text = policy["제외조건_JSON"]
        if condition_text:
            condition = json.loads(condition_text)
            if (
                not isinstance(condition, dict)
                or set(condition) != {"rule_id", "operator", "value"}
                or condition["operator"] != "ALL_EQ"
            ):
                raise ValueError("지원하지 않는 질문 제외조건입니다.")
            parent_rules = get_rules(condition["rule_id"])
            if not parent_rules["규칙유형"].eq("범주형").all():
                raise ValueError("선행응답 조건은 범주형 규칙만 지원합니다.")
            if condition["value"] not in set(parent_rules["입력값·조건"]):
                raise ValueError("제외조건의 응답값이 선행 규칙에 없습니다.")
            if condition["rule_id"] == question["점수규칙ID"]:
                raise ValueError("질문이 자기 응답으로 제외 여부를 결정할 수 없습니다.")
    for _, question in questions.iterrows():
        for task_id in split_ids(question["적용작업ID"]):
            get_prework_policy(question["항목ID"], task_id)
    print("사전평가 설정 검사 통과")

def get_prework_questions(task_id, answers=None):
    """시점과 선행응답을 확인하여 적용/제외/대기 상태를 반환합니다."""
    task_id = str(task_id).strip()
    answers = normalize_answers({} if answers is None else answers)
    task_questions = get_questions_for_task(task_id)
    unexpected = set(answers) - set(task_questions["항목ID"])
    if unexpected:
        raise ValueError(f"작업 외 질문: {sorted(unexpected)}")

    rows = []
    for _, question in task_questions.iterrows():
        row = question.to_dict()
        policy = get_prework_policy(question["항목ID"], task_id)
        row["원래확인항목"] = question["확인항목"]
        row["확인항목"] = policy["사전확인항목"] or question["확인항목"]
        row["평가시점"] = "작업시작전"
        row["사전안내"] = policy["사전안내"]
        row["적용상태"] = "적용"
        row["제외사유"] = ""
        if not read_flag(policy["사전평가사용"], "사전평가사용"):
            row["적용상태"] = "시점제외"
            row["제외사유"] = policy["사전안내"]
        elif policy["제외조건_JSON"]:
            condition = json.loads(policy["제외조건_JSON"])
            parents = task_questions.loc[
                task_questions["점수규칙ID"] == condition["rule_id"]
            ]
            if parents.empty:
                # 선행질문 연결이 없는 경우 안전한 것으로 간주하지 않습니다.
                row["적용상태"] = "선행응답필요"
                row["제외사유"] = "해당 작업에 선행질문이 연결되지 않음"
            else:
                values = []
                for _, parent in parents.iterrows():
                    parent_id = parent["항목ID"]
                    parent_policy = get_prework_policy(parent_id, task_id)
                    if not read_flag(parent_policy["사전평가사용"], "사전평가사용"):
                        raise ValueError("사전평가 제외조건이 시점제외 질문에 의존합니다.")
                    value = answers.get(parent_id)
                    if not is_missing(value):
                        # 허용값이 아닌 응답 때문에 하위 질문이 제외되지 않도록 검증
                        score_answer(parent_id, value)
                        values.append(str(value).strip())
                if len(values) != len(parents):
                    row["적용상태"] = "선행응답필요"
                    row["제외사유"] = "먼저 응답할 질문: " + ";".join(parents["항목ID"])
                elif all(value == condition["value"] for value in values):
                    row["적용상태"] = "조건제외"
                    row["제외사유"] = "선행질문의 응답이 CSV 제외조건에 해당"
        rows.append(row)
    columns = list(task_questions.columns) + [
        "원래확인항목", "평가시점", "사전안내", "적용상태", "제외사유",
    ]
    return pd.DataFrame(rows, columns=columns)

def check_required_answers(task_id, answers):
    answers = normalize_answers(answers)
    table = get_prework_questions(task_id, answers)
    applicable = table["적용상태"].eq("적용")
    required = table["필수여부"].map(lambda value: read_flag(value, "필수여부"))
    missing = table.loc[
        applicable & required & table["항목ID"].map(
            lambda question_id: is_missing(answers.get(question_id))
        ), ["항목ID", "확인항목"]
    ].reset_index(drop=True)
    pending = table.loc[table["적용상태"] == "선행응답필요", "항목ID"].tolist()
    summary = {
        "작업ID": str(task_id).strip(),
        "평가시점": "작업시작전",
        "필수질문수": int((applicable & required).sum()),
        "누락질문수": len(missing),
        "선행응답대기ID": pending,
        "제외질문ID": table.loc[
            table["적용상태"].isin(["시점제외", "조건제외"]), "항목ID"
        ].tolist(),
        "필수응답입력완료": missing.empty and not pending,
    }
    return summary, missing

def select_representatives(detail):
    candidates = detail.loc[detail["점수합산대상"]]
    return (
        candidates.sort_values(["가중점수", "항목ID"], ascending=[False, True])
        .drop_duplicates("중복집계그룹", keep="first")
    )

def get_basic_grade(risk_index):
    if risk_index is None:
        return "평가불가"
    number = to_number(risk_index, "위험지수")
    rules = get_rules("S045")
    matched = rules.loc[
        rules.apply(lambda rule: matches_numeric_rule(number, rule), axis=1)
    ]
    rule = get_single_row(matched, f"위험지수 {number}의 기본등급")
    return rule["입력값·조건"]

def calculate_task_risk(task_id, answers):
    """사전 평가 대상만 합산하고 제외 응답은 별도 로그로 보존합니다."""
    answers = normalize_answers(answers)
    check, missing = check_required_answers(task_id, answers)
    if not check["필수응답입력완료"]:
        raise ValueError(
            f"필수응답 누락: {missing['항목ID'].tolist()} / "
            f"선행응답 대기: {check['선행응답대기ID']}"
        )
    table = get_prework_questions(task_id, answers)
    if table.empty:
        raise ValueError("해당 작업에 연결된 질문이 없습니다.")
    results = []
    for _, question in table.iterrows():
        question_id = question["항목ID"]
        answer = answers.get(question_id)
        active_answer = question["적용상태"] == "적용" and not is_missing(answer)
        if active_answer:
            result = score_answer(question_id, answer)
        else:
            # 제외나 미응답을 '안전한 0점 응답'으로 저장하지 않습니다.
            result = {
                "항목ID": question_id, "확인항목": question["확인항목"],
                "사용자응답": answer, "단위": question["단위"],
                "점수규칙ID": question["점수규칙ID"], "조건순번": "",
                "점수": None, "가중치": None, "가중점수": 0.0,
                "최대가중점수": 0.0, "점수합산대상": False,
                "중복집계그룹": question["중복집계그룹"],
                "그룹집계방식": question["그룹집계방식"],
                "관련기준ID": question["연결기준ID"],
                "적용조건": "", "확정상태": "점수미산정",
            }
        result["확인항목"] = question["확인항목"]
        result["평가시점"] = "작업시작전"
        result["적용상태"] = question["적용상태"]
        result["제외사유"] = question["제외사유"]
        result["사전안내"] = question["사전안내"]
        result["응답상태"] = "미응답" if is_missing(answer) else "입력"
        results.append(result)
    detail = pd.DataFrame(results)
    representatives = select_representatives(detail)
    detail["집계대표여부"] = detail.index.isin(representatives.index)
    total = float(representatives["가중점수"].sum())
    maximum = float(representatives["최대가중점수"].sum())
    risk_index = total / maximum * 100 if maximum > 0 else None
    summary = {
        "작업ID": str(task_id).strip(), "평가시점": "작업시작전",
        "적용질문수": int(table["적용상태"].eq("적용").sum()),
        "제외질문수": len(check["제외질문ID"]),
        "입력질문수": sum(not is_missing(value) for value in answers.values()),
        "집계항목수": len(representatives),
        "총가중위험점수": total, "최대가중점수": maximum,
        "위험지수": risk_index,
        "기본위험등급(잠정)": get_basic_grade(risk_index),
        "강제경고": "미검증",
        "최종판정": "보류: 법령·잔여 적용조건 미검증",
        "계산상태": "사전 시험 계산" if maximum > 0 else "계산 불가: 합산 대상 없음",
    }
    return summary, detail

def get_top_risks(detail, count=3):
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("표시 개수는 1 이상의 정수여야 합니다.")
    positive = detail.loc[detail["집계대표여부"] & (detail["가중점수"] > 0)]
    return (
        positive.sort_values(["가중점수", "항목ID"], ascending=[False, True])
        .head(count)[["항목ID", "확인항목", "사용자응답", "가중점수", "관련기준ID"]]
        .reset_index(drop=True)
    )

def get_related_standards(detail, count=3):
    rows = []
    for _, risk in get_top_risks(detail, count).iterrows():
        for standard_id in dict.fromkeys(split_ids(risk["관련기준ID"])):
            standard = get_single_row(
                standards.loc[standards["기준ID"] == standard_id], f"기준 {standard_id}"
            )
            rows.append({
                "항목ID": risk["항목ID"], "위험요인": risk["확인항목"],
                "사용자응답": risk["사용자응답"], "가중점수": risk["가중점수"],
                "기준ID": standard_id, "적용조건": standard["적용조건"],
                "필수조치": standard["필수조치"], "출처URL": standard["출처URL"],
                "판정상태": "관련 근거 조회 - 적용·위반 여부 미검증",
            })
    return pd.DataFrame(rows, columns=[
        "항목ID", "위험요인", "사용자응답", "가중점수", "기준ID",
        "적용조건", "필수조치", "출처URL", "판정상태",
    ])

def get_related_accidents(task_id, verified_only=True):
    task_id = str(task_id).strip()
    get_single_row(tasks.loc[tasks["작업ID"] == task_id], f"작업 {task_id}")
    selected = accidents.loc[
        accidents["작업ID"].map(lambda value: task_id in split_ids(value))
    ].copy()
    if verified_only:
        selected = selected.loc[selected["검수상태"] == "검수완료"]
    return selected[[
        "사고ID", "작업ID", "사고일자", "지역", "사고유형",
        "사고경위_원문", "사고원인_원문", "출처URL", "검수상태"
    ]].reset_index(drop=True)

def review_h05_watcher_conditions(answers):
    """H05 추가 응답을 검토합니다. 점수나 최종판정은 변경하지 않습니다."""
    if not isinstance(answers, dict):
        raise ValueError("응답은 {'W001': '예', ...} 형식이어야 합니다.")

    ids = watcher_questions["추가질문ID"].tolist()
    unknown_ids = set(answers) - set(ids)

    if unknown_ids:
        raise ValueError(f"알 수 없는 추가질문ID: {unknown_ids}")

    normalized = {}
    for question_id in ids:
        value = answers.get(question_id, "확인불가")

        if not isinstance(value, str):
            raise ValueError(f"{question_id}: 문자열 응답이 필요합니다.")

        value = value.strip()
        if value not in {"예", "아니오", "확인불가"}:
            raise ValueError(
                f"{question_id}: 예 / 아니오 / 확인불가 중 입력하세요."
            )
        normalized[question_id] = value

    place_ids = watcher_questions.loc[
        watcher_questions["구분"].eq("장소조건"), "추가질문ID"
    ].tolist()

    exception_id = watcher_questions.loc[
        watcher_questions["구분"].eq("예외검토"), "추가질문ID"
    ].item()

    matched = [qid for qid in place_ids if normalized[qid] == "예"]
    uncertain = [
        qid for qid in place_ids if normalized[qid] == "확인불가"
    ]
    exception = normalized[exception_id]

    if matched:
        place_status = "장소조건 해당 응답 있음"
    elif uncertain:
        place_status = "장소조건 확인 필요"
    else:
        place_status = "입력상 세 장소조건 모두 비해당"

    if exception == "예":
        review_status = "예외 근거 및 현장 조건 검토 필요"
    elif exception == "확인불가":
        review_status = "예외 적용 여부 확인 필요"
    elif matched:
        review_status = "배치 대상 검토: 장소조건 해당, 예외 적용 요청 없음"
    elif uncertain:
        review_status = "미확인 장소조건 추가 확인 필요"
    else:
        review_status = "적용 제외 후보: 현장 근거 확인 필요"

    summary = {
        "작업ID": "H05",
        "대상항목ID": "Q004",
        "연결기준ID": "R002",
        "장소조건검토": place_status,
        "해당조건ID": ", ".join(matched) or "-",
        "미확인조건ID": ", ".join(uncertain) or "-",
        "검토결과": review_status,
        "해당없음자동승인": False,
    }

    detail = watcher_questions.copy()
    detail["응답"] = detail["추가질문ID"].map(normalized)

    return summary, detail

def check_h05_watcher_response(watcher_answers, deployment_answer):
    """추가 현장 조건과 Q004 응답을 비교합니다."""
    allowed = {"배치", "미배치", "해당없음"}

    if not isinstance(deployment_answer, str):
        raise ValueError("Q004 응답은 문자열이어야 합니다.")

    deployment_answer = deployment_answer.strip()

    if deployment_answer not in allowed:
        raise ValueError("Q004는 배치 / 미배치 / 해당없음 중 입력하세요.")

    # 앞서 만든 함수로 추가 응답을 검증하고 결과를 다시 계산
    condition_summary, condition_detail = (
        review_h05_watcher_conditions(watcher_answers)
    )

    place_answers = condition_detail.loc[
        condition_detail["구분"].eq("장소조건"), "응답"
    ]

    exception_answer = condition_detail.loc[
        condition_detail["구분"].eq("예외검토"), "응답"
    ].item()

    has_condition = place_answers.eq("예").any()
    has_unknown = place_answers.eq("확인불가").any()

    if deployment_answer == "해당없음":
        status = "해당없음 근거 검토 필요"
        message = "추가 응답만으로 해당없음을 승인하지 않습니다."

    elif exception_answer != "아니오":
        status = "예외 적용 검토 필요"
        message = (
            "배치 예외의 적용 의사 또는 근거를 확인해야 합니다. "
            f"현재 Q004 응답은 '{deployment_answer}'입니다."
        )

    elif has_condition and deployment_answer == "미배치":
        status = "배치 상태 확인 필요"
        message = (
            "장소조건에 해당하는 응답이 있고 예외 적용 요청은 없지만, "
            "화재감시자가 미배치로 입력되어 있습니다."
        )

    elif has_condition:
        status = "배치 응답 확인"
        message = (
            "장소조건에 해당하는 응답과 배치 응답이 확인되었습니다. "
            "이 결과만으로 전체 안전조치가 완료된 것은 아닙니다."
        )

    elif has_unknown:
        status = "현장 조건 확인 필요"
        message = "확인불가로 남아 있는 장소조건을 확인하세요."

    else:
        status = "적용 여부 근거 확인 필요"
        message = (
            "입력상 세 장소조건은 모두 비해당입니다. "
            "현장 근거 확인 전에는 적용 제외를 확정하지 않습니다."
        )

    result = {
        **condition_summary,
        "Q004응답": deployment_answer,
        "응답비교결과": status,
        "확인메시지": message,
        "최종판정": "보류: 현장 근거 및 나머지 기준 미검증",
    }

    return result, condition_detail

watcher_questions = pd.DataFrame([{'추가질문ID': 'W001', '구분': '장소조건', '질문': '작업반경 11m 이내 건물구조 자체 또는 내부(개구부 등으로 개방된 부분 포함)에 가연성물질이 있는가?'}, {'추가질문ID': 'W002', '구분': '장소조건', '질문': '작업반경 11m 이내의 바닥 하부에 가연성물질이 11m 이상 떨어져 있지만 불꽃에 의해 쉽게 발화될 우려가 있는가?'}, {'추가질문ID': 'W003', '구분': '장소조건', '질문': '금속 칸막이·벽·천장·지붕의 반대쪽 면에 가연성물질이 인접하여 열전도·열복사로 발화될 우려가 있는가?'}, {'추가질문ID': 'W004', '구분': '예외검토', '질문': '같은 장소에서 상시·반복적으로 용접·용단하는 경우의 설비 구비 등 법령상 배치 예외를 적용하려는가?'}])
watcher_questions['허용응답'] = '예 / 아니오 / 확인불가'

def load_databases(directory=None):
    """필수 CSV를 검증합니다. 실패 시 기존 상태를 복구합니다."""
    names = {
        "tasks": "01_공정_세부작업DB.csv",
        "questions": "02_위험요인_입력항목DB.csv",
        "score_rules": "08_점수규칙DB.csv",
        "standards": "04_법령_KOSHA기준DB.csv",
        "prework_policies": "09_사전평가설정.csv",
        "accidents": "03_사고데이터.csv",
    }
    selected = Path(directory).resolve() if directory is not None else find_data_dir()
    missing = [name for name in names.values() if not (selected / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"필수 CSV 누락: {missing}\n확인 폴더: {selected}\n"
            "기존 설정 파일을 복원한 뒤 다시 실행하세요. 설정은 자동 생성하지 않습니다."
        )
    loaded = {}
    for key, filename in names.items():
        table = pd.read_csv(selected / filename, encoding="utf-8-sig",
                            dtype=str, keep_default_na=False)
        loaded[key] = table.apply(lambda column: column.str.strip())
    keys = ["data_dir", *names]
    old = {key: globals()[key] for key in keys if key in globals()}
    globals().update(loaded)
    globals()["data_dir"] = selected
    try:
        validate_databases()
        validate_prework_policies()
    except Exception:
        for key in keys:
            globals().pop(key, None)
        globals().update(old)
        raise
    return selected


# 평가 기록: CSV 원본과 분리된 SQLite 저장소
def build_evaluation(site_name, task_id, answers, watcher_answers=None,
                     evaluation_id=None, evaluated_at=None):
    """현재 입력으로 다시 계산한 평가 기록을 만듭니다. 저장은 별도 호출합니다."""
    from datetime import datetime, timezone, timedelta
    from uuid import uuid4
    import hashlib

    if data_dir is None:
        raise RuntimeError("먼저 load_databases()를 실행하세요.")
    if not isinstance(site_name, str) or not site_name.strip():
        raise ValueError("현장명을 입력하세요.")
    task_id = str(task_id).strip()
    normalized = normalize_answers(answers)
    summary, detail = calculate_task_risk(task_id, normalized)
    watcher_result, watcher_rows = None, None
    if task_id == "H05":
        # 누락된 추가응답은 기존 함수에서 확인불가로 표시합니다.
        extra = {} if watcher_answers is None else watcher_answers
        watcher_result, watcher_rows = check_h05_watcher_response(
            extra, normalized.get("Q004")
        )
    elif watcher_answers is not None:
        raise ValueError("화재감시자 추가 검토는 현재 H05만 지원합니다.")

    stamp = evaluated_at or datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat(timespec="seconds")
    parsed = datetime.fromisoformat(stamp)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("평가일시에는 시간대가 필요합니다. 예: +09:00")
    identifier = evaluation_id if evaluation_id is not None else str(uuid4())
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("평가ID는 비어 있지 않은 문자열이어야 합니다.")

    # 실제 계산에 사용한 메모리상의 데이터 버전을 기록합니다.
    snapshots = {
        name: globals()[name].to_json(orient="split", force_ascii=False)
        for name in ("tasks", "questions", "score_rules", "standards",
                     "prework_policies", "watcher_questions")
    }
    digest = hashlib.sha256(
        json.dumps(snapshots, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    record = {
        "저장형식버전": 1, "평가ID": identifier.strip(),
        "평가일시": parsed.isoformat(), "현장명": site_name.strip(),
        "작업ID": task_id,
        "응답": json.loads(pd.Series(normalized, dtype=object).to_json(force_ascii=False)),
        "요약": summary,
        "응답상세": json.loads(detail.to_json(orient="records", force_ascii=False)),
        "화재감시자검토": watcher_result,
        "화재감시자응답": None if watcher_rows is None else json.loads(
            watcher_rows.to_json(orient="records", force_ascii=False)
        ),
        "계산데이터SHA256": digest,
        "엔진SHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    # 데이터와 검토 결과를 JSON으로 저장할 수 있는지 미리 확인합니다.
    return json.loads(json.dumps(record, ensure_ascii=False, allow_nan=False))


def save_evaluation(record, storage_path):
    """평가 전체를 하나의 트랜잭션으로 저장. 같은 ID의 다른 내용은 거부합니다."""
    import sqlite3
    from contextlib import closing

    required = {"저장형식버전", "평가ID", "평가일시", "현장명", "작업ID",
                "요약", "응답", "응답상세", "화재감시자검토", "화재감시자응답",
                "계산데이터SHA256", "엔진SHA256"}
    if not isinstance(record, dict) or required - record.keys():
        raise ValueError("build_evaluation()으로 만든 평가 기록이 필요합니다.")
    if record["저장형식버전"] != 1:
        raise ValueError("지원하지 않는 저장형식입니다.")
    for key in ("평가ID", "평가일시", "현장명", "작업ID"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"{key} 값이 필요합니다.")
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    target = Path(storage_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as connection, connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS evaluations (
            evaluation_id TEXT PRIMARY KEY, payload TEXT NOT NULL
        )""")
        connection.execute("BEGIN IMMEDIATE")
        old = connection.execute(
            "SELECT payload FROM evaluations WHERE evaluation_id = ?",
            (record["평가ID"],)
        ).fetchone()
        if old is not None:
            if old[0] != payload:
                raise ValueError("같은 평가ID에 다른 내용이 있습니다. 새 평가ID를 사용하세요.")
            return {"평가ID": record["평가ID"], "저장상태": "이미 저장됨", "저장경로": str(target)}
        connection.execute("INSERT INTO evaluations VALUES (?, ?)",
                           (record["평가ID"], payload))
    return {"평가ID": record["평가ID"], "저장상태": "저장 완료", "저장경로": str(target)}


def load_evaluation(evaluation_id, storage_path):
    """저장 당시의 입력·결과를 조회합니다. 현재 규칙으로 다시 계산하지 않습니다."""
    import sqlite3
    from contextlib import closing
    target = Path(storage_path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    with closing(sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)) as connection, connection:
        row = connection.execute(
            "SELECT payload FROM evaluations WHERE evaluation_id = ?",
            (evaluation_id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"평가ID를 찾을 수 없습니다: {evaluation_id}")
    return json.loads(row[0])


def list_evaluations(storage_path):
    """저장된 평가 목록을 반환합니다."""
    import sqlite3
    from contextlib import closing
    columns = ["평가ID", "평가일시", "현장명", "작업ID", "위험지수",
               "기본위험등급(잠정)", "최종판정"]
    target = Path(storage_path).expanduser().resolve()
    if not target.is_file():
        return pd.DataFrame(columns=columns)
    with closing(sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)) as connection, connection:
        records = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM evaluations"
        ).fetchall()]
    rows = []
    for record in records:
        rows.append({
            **{key: record[key] for key in columns[:4]},
            **{key: record["요약"][key] for key in columns[4:]},
        })
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["평가일시", "평가ID"], ascending=False
    ).reset_index(drop=True)


