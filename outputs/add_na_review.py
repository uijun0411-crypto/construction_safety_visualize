import json, shutil, csv
from pathlib import Path
from datetime import datetime
p=Path("fire_risk_project/notebooks/03_작업시작전_평가.ipynb")
n=json.loads(p.read_text(encoding="utf-8-sig"))
backup=Path("outputs") / ("03_before_applicability_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".ipynb")
shutil.copy2(p,backup)
config=Path("fire_risk_project/data/10_해당없음검토설정.csv")
if config.exists(): raise FileExistsError(config)
rows=[
 {"작업ID":"H05","항목ID":"Q003","기준ID":"R001","보류응답":"해당없음","추가확인사항":"가연성물질 없음만으로 불티 비산방지조치를 제외하지 않음. 제241조제2항·제3항과 실제 작업조건을 함께 검토할 것.","검토신호_JSON":json.dumps([{"question":"Q001","op":"EQ","value":"있음"}],ensure_ascii=False),"출처URL":"https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=153999","확인일자":"2026-10-09"},
 {"작업ID":"H05","항목ID":"Q004","기준ID":"R002","보류응답":"해당없음","추가확인사항":"건물구조·내부(개구부 포함)의 가연물, 바닥 하부 및 반대편 발화우려를 확인. 같은 장소의 상시·반복 용접·용단 및 경보용 설비·기구, 소화설비 또는 소화기 관련 단서도 원문과 대조. 거리만으로 배치 의무나 예외를 확정하지 않음.","검토신호_JSON":json.dumps([{"question":"Q002","op":"LTE_STANDARD","standard":"R002","column":"기준값"},{"question":"Q019","op":"EQ","value":"있음"},{"question":"Q020","op":"EQ","value":"있음"}],ensure_ascii=False),"출처URL":"https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1016870875","확인일자":"2026-10-09"}
]
with config.open("w",encoding="utf-8-sig",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
code=r'''
def validate_na_review_policies():
    required = {"작업ID", "항목ID", "기준ID", "보류응답", "추가확인사항", "검토신호_JSON"}
    if required - set(na_review_policies.columns):
        raise ValueError("해당없음 검토 설정의 필수 컬럼이 없습니다.")
    if na_review_policies.duplicated(["작업ID", "항목ID"]).any():
        raise ValueError("해당없음 검토 설정 중복")
    for _, policy in na_review_policies.iterrows():
        table = get_questions_for_task(policy["작업ID"])
        if policy["항목ID"] not in set(table["항목ID"]):
            raise ValueError("해당없음 검토 대상 작업/질문 불일치")
        score_answer(policy["항목ID"], policy["보류응답"])
        get_single_row(standards.loc[standards["기준ID"] == policy["기준ID"]], "검토 기준")
        signals = json.loads(policy["검토신호_JSON"])
        if not isinstance(signals, list) or not signals:
            raise ValueError("검토신호는 비어 있지 않은 목록이어야 합니다.")
        for signal in signals:
            if signal["question"] not in set(table["항목ID"]):
                raise ValueError("검토신호가 작업 외 질문을 참조합니다.")
            if signal["op"] == "EQ":
                if set(signal) != {"question", "op", "value"}:
                    raise ValueError("EQ 설정 오류")
                score_answer(signal["question"], signal["value"])
            elif signal["op"] == "LTE_STANDARD":
                if set(signal) != {"question", "op", "standard", "column"}:
                    raise ValueError("LTE_STANDARD 설정 오류")
                standard = get_single_row(standards.loc[standards["기준ID"] == signal["standard"]], "검토 기준")
                to_number(standard[signal["column"]], "검토 기준값")
            else:
                raise ValueError("지원하지 않는 검토신호 연산자")

def review_not_applicable(task_id, answers):
    """법령 자동판정이 아닌, 응답 검증과 추가 현장확인 목록입니다."""
    answers = normalize_answers(answers)
    table = get_prework_questions(task_id, answers)
    policies = na_review_policies.loc[na_review_policies["작업ID"] == str(task_id).strip()]
    result = []
    for _, policy in policies.iterrows():
        qid = policy["항목ID"]
        question = get_single_row(table.loc[table["항목ID"] == qid], "검토 질문")
        if question["적용상태"] != "적용":
            continue
        answer = answers.get(qid)
        if not is_missing(answer):
            score_answer(qid, answer)
        signals_found, unknown = [], []
        for signal in json.loads(policy["검토신호_JSON"]):
            parent_id = signal["question"]
            parent = get_single_row(table.loc[table["항목ID"] == parent_id], "신호 질문")
            value = answers.get(parent_id)
            # 조건/시점 제외된 과거 응답은 재사용하지 않습니다.
            if parent["적용상태"] != "적용" or is_missing(value):
                unknown.append(parent_id)
                continue
            score_answer(parent_id, value)
            if signal["op"] == "EQ":
                matched = str(value).strip() == signal["value"]
            elif signal["op"] == "LTE_STANDARD":
                standard = get_single_row(standards.loc[standards["기준ID"] == signal["standard"]], "검토 기준")
                matched = to_number(value, parent_id) <= to_number(standard[signal["column"]], "검토 기준값")
            else:
                raise ValueError("지원하지 않는 검토신호 연산자")
            if matched:
                signals_found.append(parent_id)
        blocked = not is_missing(answer) and str(answer).strip() == policy["보류응답"]
        result.append({
            "항목ID": qid, "기준ID": policy["기준ID"], "사용자응답": answer,
            "계산보류": bool(blocked),
            "검토상태": "해당없음 근거 확인 필요" if blocked else "적용조건 별도 확인 필요",
            "확인된검토신호": ";".join(signals_found),
            "미확인신호": ";".join(unknown),
            "추가확인사항": policy["추가확인사항"],
        })
    return pd.DataFrame(result, columns=[
        "항목ID", "기준ID", "사용자응답", "계산보류", "검토상태",
        "확인된검토신호", "미확인신호", "추가확인사항",
    ])

def enforce_not_applicable_review(task_id, answers):
    review = review_not_applicable(task_id, answers)
    blocked = review.loc[review["계산보류"].eq(True), "항목ID"].tolist()
    if blocked:
        raise ValueError(
            f"계산 보류: {blocked}의 해당없음 근거가 검증되지 않았습니다. "
            "review_not_applicable(task_id, answers)로 추가확인사항을 확인하세요. "
            "실제 조치 여부와 다르게 응답을 바꾸지 마세요."
        )

validate_na_review_policies()
'''
n["cells"][1]["source"] += ['na_review_policies = read_database("10_해당없음검토설정.csv")\n']
s="".join(n["cells"][9]["source"])
marker='    table = get_prework_questions(task_id, answers)\n    if table.empty:'
assert marker in s
s=s.replace(marker,'    enforce_not_applicable_review(task_id, answers)\n'+marker,1)
# Functions are defined before any scenario calculation.
s += "\n"+code
n["cells"][9]["source"]=s.splitlines(keepends=True)
def cell(kind,source,id):
 c={"cell_type":kind,"id":id,"metadata":{},"source":source.splitlines(keepends=True)}
 if kind=="code":c.update(execution_count=None,outputs=[])
 return c
n["cells"][-1:]=[
 cell("markdown",'''## 해당없음 응답 검토 (H05 / R001·R002)
두 질문의 해당없음 응답은 근거 확인 전까지 계산을 보류합니다. 아래 예제는 오류를 잡아 안내문으로 출력하므로 모두 실행해도 중단되지 않습니다.

검토신호는 법령 위반 판정이 아닙니다. 거리 11m 이내 여부와 기존 응답을 표시할 뿐, 건물 구조·개구부나 배치 예외를 자동 확인하지 않습니다. **신호가 없다는 것도 적용 제외의 근거가 아닙니다.** Q003은 가연물이 없다는 응답만으로 제외하지 않습니다.

이 단계는 H05의 Q003/Q004만 다룹니다. 다른 작업·법령과 예외 자동판정은 아직 구현하지 않았고 최종판정은 계속 보류됩니다. 원문과 검토사항은 data/10_해당없음검토설정.csv에 있습니다.
''',"na-review-notes"),
 cell("code",'''# 1. 기존 응답의 추가 확인 목록
display(review_not_applicable("H05", h05_answers))

# 2. 근거 없는 해당없음 입력을 막는 예제 (테스트용 복사본)
na_example = {**h05_answers, "Q004": "해당없음"}
display(review_not_applicable("H05", na_example))
try:
    calculate_task_risk("H05", na_example)
except ValueError as error:
    print(error)

# 실제 평가 입력은 위 h05_answers를 사용합니다.
# 다음 개발 단계: 추가 현장 질문으로 배치 조건과 예외를 구조화한 뒤 검증합니다.
''',"na-review-example")
]
p.write_text(json.dumps(n,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
print("Backup:",backup)
print("Updated:",p)

