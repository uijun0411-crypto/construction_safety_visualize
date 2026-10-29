"""Conservative cross-zone fire interference review using existing project data."""
from . import risk_engine as engine, materials

VERSION = "1.0"
SOURCE_FILES = {
    "공정": "01_공정_세부작업DB.csv",
    "위험조건": "02_위험요인_입력항목DB.csv",
    "근거": "04_법령_KOSHA근거DB.csv",
    "MSDS": "05_MSDS_물질DB.csv",
}


def _task(task_id):
    rows = engine.tasks.loc[engine.tasks["작업ID"] == task_id]
    return rows.iloc[0].to_dict() if len(rows) == 1 else None


def _hot(task, answers):
    if not task:
        return None
    group = task["위험작업군"]
    if "화기·불티" not in group and "마찰·절삭" not in group and "가열·열원" not in group:
        return False
    if task["작업ID"] in ("H29", "H30"):
        return {"실시": True, "미실시": False}.get(answers.get("Q031"))
    return True


def _question_applies(task_id, question_id):
    rows = engine.questions.loc[engine.questions["항목ID"] == question_id]
    return any(task_id in row["적용작업ID"].split(";") for _, row in rows.iterrows())


def _material(task, answers, selection, catalogue):
    """Return confirmed flammability only when the existing answer and SDS agree."""
    if not task:
        return None, [], ["작업 종류"]
    use = answers.get("Q007")
    presence = answers.get("Q001")
    if _question_applies(task["작업ID"], "Q007") and use is None:
        return None, [], ["인화성 물질 사용 여부(Q007)"]
    if _question_applies(task["작업ID"], "Q001") and presence is None:
        return None, [], ["주변 가연물 존재 여부(Q001)"]
    if use == "미사용" and not selection.get("ids") and not selection.get("custom_names"):
        return False, [], []
    if presence == "없음" and use is None:
        return False, [], []
    if use == "확인불가" or selection.get("unknown") or selection.get("custom_names"):
        return None, [], ["가연물 종류와 실제 제품 MSDS"]
    ids = selection.get("ids") or []
    if not ids:
        if use == "사용" or presence == "있음" or "인화성물질" in task["위험작업군"]:
            return None, [], ["실제 사용 물질과 MSDS 인화성 분류"]
        return False, [], []
    if catalogue is None:
        return None, [], ["MSDS DB 조회"]
    lookup = {row["물질ID"]: row for row in catalogue["rows"]}
    evidence, classifications = [], []
    for identifier in ids:
        row = lookup.get(identifier)
        if not row or task["작업ID"] not in row["적용작업ID"].split(";"):
            return None, evidence, ["실제 사용 제품과 작업의 MSDS 연결"]
        label = row["GHS인화성구분"].replace(" ", "")
        if label.startswith("비인화성"):
            classifications.append(False)
        elif "인화성액체" in label or "가연성가스" in label:
            classifications.append(True)
        else:
            classifications.append(None)
        evidence.append({"물질ID": identifier, "제품명": row["제품명"], "GHS인화성구분": row["GHS인화성구분"],
                         "물성근거URL": row["물성근거URL"], "확인필요사유": row["확인필요사유"]})
    if use == "미사용" and any(classifications):
        return None, evidence, ["인화성 물질 사용 응답과 MSDS 선택의 불일치"]
    if use == "사용" or presence == "있음":
        if any(classification is True for classification in classifications):
            return True, evidence, []
        if all(classification is False for classification in classifications):
            return False, evidence, []
        return None, evidence, ["실제 제품 MSDS 인화성 분류"]
    return None, evidence, ["가연물 존재 또는 인화성 물질 사용 여부"]


def _evidence(task_ids, question_ids, standard_ids):
    tasks = [row.to_dict() for _, row in engine.tasks.iterrows() if row["작업ID"] in task_ids]
    questions = [row.to_dict() for _, row in engine.questions.iterrows() if row["항목ID"] in question_ids]
    standards = [row.to_dict() for _, row in engine.standards.iterrows() if row["기준ID"] in standard_ids]
    return {"공정": [{"작업ID": r["작업ID"], "주요위험원": r["주요위험원"]} for r in tasks],
            "질문": [{"항목ID": r["항목ID"], "확인항목": r["확인항목"], "연결기준ID": r["연결기준ID"]} for r in questions],
            "근거": [{"기준ID": r["기준ID"], "적용조건": r["적용조건"], "필수조치": r["필수조치"],
                    "출처URL": r["출처URL"]} for r in standards]}


def analyze_pairs(relations, zones, inputs, confirmations=None):
    confirmations = confirmations or {}
    by_id = {zone["zone_id"]: zone for zone in zones}
    try:
        catalogue = materials.catalogue()
    except materials.MaterialDataError:
        catalogue = None
    results = []
    for relation in relations:
        a_id, b_id = relation["작업구역ID_A"], relation["작업구역ID_B"]
        pair = (a_id, b_id)
        first, second = inputs.get(a_id) or {}, inputs.get(b_id) or {}
        task_a, task_b = _task(first.get("task_id")), _task(second.get("task_id"))
        tasks = [{"작업구역ID": zid, "작업ID": task["작업ID"] if task else None,
                  "작업명": task["세부작업"] if task else None}
                 for zid, task in ((a_id, task_a), (b_id, task_b))]
        relevant_answers = ("Q001", "Q002", "Q003", "Q004", "Q007", "Q008", "Q009", "Q031", "Q040", "Q041")
        existing_answers = {zone_id: {qid: (source.get("answers") or {})[qid] for qid in relevant_answers
                                      if qid in (source.get("answers") or {})}
                            for zone_id, source in ((a_id, first), (b_id, second))}
        result = {"작업구역ID_A": a_id, "작업구역ID_B": b_id, "작업종류": tasks,
                  "작업시간": {key: relation[key] for key in ("작업시간중복", "시간관계", "중복시작일시", "중복종료일시", "중복시간_분")},
                  "조감도상영역관계": relation["조감도상영역관계"], "기존위험조건응답": existing_answers,
                  "확인된위험요인": [],
                  "분석상태": None, "추가확인필요사항": [], "필요한예방조치": [],
                  "기존DB근거": {}, "분석기준버전": VERSION, "참조DB": SOURCE_FILES}
        if relation["작업시간중복"] is False:
            result["분석상태"] = "작업시간 중복 없음"
            result["추가확인필요사항"] = ["잔류 열원·인화성 증기 등 작업 전후 영향 여부"]
            results.append(result)
            continue
        if relation["작업시간중복"] is None:
            result["분석상태"] = "추가 확인 필요"
            result["추가확인필요사항"] = ["두 구역의 작업 시작·종료일시"]
            results.append(result)
            continue
        if not task_a or not task_b:
            result["분석상태"] = "추가 확인 필요"
            result["추가확인필요사항"] = ["두 구역의 작업 종류"]
            results.append(result)
            continue
        candidates = []
        missing = []
        evidence_materials = []
        for source_id, source_task, source_input, target_id, target_task, target_input in (
            (a_id, task_a, first, b_id, task_b, second), (b_id, task_b, second, a_id, task_a, first)):
            hot = _hot(source_task, source_input.get("answers") or {})
            if hot is None:
                missing.append("불티·화염 발생 작업 실시 여부")
            if hot is not True:
                continue
            material, rows, needs = _material(target_task, target_input.get("answers") or {},
                                              target_input.get("materials") or {}, catalogue)
            evidence_materials.extend(rows)
            missing.extend(needs)
            if material is True:
                candidates.append((source_id, target_id))
        if not candidates:
            result["분석상태"] = "추가 확인 필요" if missing else "확인된 간섭 위험요인 없음"
            result["추가확인필요사항"] = sorted(set(missing))
            results.append(result)
            continue
        extra = confirmations.get(pair) or {}
        if relation["위치정보확인필요"] or relation["조감도상영역관계"] == "분리":
            if extra.get("actual_adjacent") is None:
                missing.append("실제 구역 간 인접 여부 및 거리")
        if extra.get("spark_reaches") is None:
            missing.append("불티 비산 가능성")
        if extra.get("vapor_reaches") is None:
            missing.append("인화성 증기 이동 가능성")
        if extra.get("barrier") in (None, "확인불가"):
            missing.append("차단조치 상태")
        existing_ventilation = [((inputs.get(target) or {}).get("answers") or {}).get("Q008") for _, target in candidates]
        ventilation_known = extra.get("ventilation") in ("양호", "보통", "미흡") or all(
            value in ("양호", "보통", "미흡") for value in existing_ventilation)
        if not ventilation_known:
            missing.append("환기상태")
        reaches = extra.get("spark_reaches") is True or extra.get("vapor_reaches") is True
        blocked = extra.get("barrier") == "있음"
        if reaches and not blocked and extra.get("barrier") == "없음":
            result["분석상태"] = "동시작업 위험요인 발견"
            result["확인된위험요인"] = [{"점화원구역ID": source, "인화성물질구역ID": target,
                                     "위험요인": "불티·화염 또는 인화성 증기와 점화원의 상호 영향"}
                                    for source, target in candidates]
        elif extra.get("spark_reaches") is False and extra.get("vapor_reaches") is False and blocked and not missing:
            result["분석상태"] = "확인된 간섭 위험요인 없음"
        else:
            result["분석상태"] = "추가 확인 필요"
        result["추가확인필요사항"] = sorted(set(missing))
        standards = _evidence({task_a["작업ID"], task_b["작업ID"]}, {"Q001", "Q002", "Q003", "Q007", "Q008", "Q009", "Q031", "Q040"}, {"R001", "R004", "R006"})
        result["기존DB근거"] = {**standards, "MSDS": evidence_materials}
        result["필요한예방조치"] = [row["필수조치"] for row in standards["근거"]]
        results.append(result)
    return results
