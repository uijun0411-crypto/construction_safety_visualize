import ast, csv, json, copy
from pathlib import Path
root = Path("fire_risk_project")
target = root / "notebooks/03_작업시작전_평가.ipynb"
policy_path = root / "data/09_사전평가설정.csv"
if target.exists() or policy_path.exists():
    raise FileExistsError("같은 이름의 사전평가 파일이 있어 덮어쓰지 않습니다.")
with (root / "data/02_위험요인_입력항목DB.csv").open(encoding="utf-8-sig",newline="") as file:
    questions = list(csv.DictReader(file))
policies = []
for question in questions:
    policies.append({
        "항목ID": question["항목ID"], "적용작업ID": "*", "사전평가사용": "1",
        "사전확인항목": question["확인항목"],
        "사전안내": "이번에 시작할 작업의 현재 준비상태와 사용예정 자재·장비를 확인. 미확인 상태를 없음·완료로 대신 입력하지 않음.",
        "제외조건_JSON": "", "설정상태": "개발기준_검토중",
    })
lookup={p["항목ID"]:p for p in policies}
lookup["Q026"].update({
    "사전평가사용":"0",
    "사전안내":"작업 종료 후 잔불·불티 확인은 사후 점검 항목. 사전 점수와 필수응답에서 제외하며 사후 확인 의무가 없어지는 것은 아님.",
})
lookup["Q036"].update({
    "사전평가사용":"0",
    "사전안내":"현재 질문은 작업 후 실시 여부와 계획 여부가 혼재. 사전 점수에서 제외하며 계획 확인 질문은 별도 설계 필요.",
})
lookup["Q041"].update({
    "사전평가사용":"0",
    "사전안내":"현재 도장작업이 끝난 뒤의 환기 확인은 사전 평가에서 제외. 후속 열풍 작업 착수 전 선행 공정의 잔류증기 확인은 작업별 설정으로 유지.",
})
heat = copy.deepcopy(lookup["Q041"])
heat.update({
    "적용작업ID":"H21", "사전평가사용":"1",
    "사전확인항목":"열풍 건조 시작 전, 선행 도장·세척의 잔류증기 제거·환기 완료 여부",
    "사전안내":"이번 열풍 작업 전에 완료되어야 하는 선행 공정의 환기상태 확인. 미래의 사후점검을 완료했다고 입력하지 않음.",
})
policies.append(heat)
lookup["Q002"]["제외조건_JSON"]=json.dumps(
    {"rule_id":"S001","operator":"ALL_EQ","value":"없음"},ensure_ascii=False
)
lookup["Q002"]["사전안내"]="해당 작업의 주변 가연물 질문에 없음으로 응답한 경우만 제외. 선행응답이 없으면 확인 대기. 하부·반대면 착화 질문과 법령 판단은 별개."
lookup["Q031"]["사전확인항목"]="이번 작업에서 불티·화염 발생 작업을 실시할 예정인지 여부"
lookup["Q031"]["사전안내"]="실시/미실시는 이번 작업의 실시 예정 여부를 뜻함. 확인불가는 계획 미확정 상태이며 후속 화기질문을 자동 제외하지 않음."
for qid in ["Q007","Q038"]:
    lookup[qid]["사전확인항목"] += " (이번 작업 사용예정 기준)"
for qid in ["Q014","Q015","Q016","Q037"]:
    lookup[qid]["사전안내"]="시작 전 확인 가능한 점검결과·기존 사용상태를 근거로 응답. 가동 전이라 상태를 알 수 없으면 확인불가를 선택. 확인불가도 기존 CSV 점수에 반영되며 점수·가중치는 아직 미확정."
with policy_path.open("w",encoding="utf-8-sig",newline="") as file:
    writer=csv.DictWriter(file,fieldnames=list(policies[0]))
    writer.writeheader();writer.writerows(policies)
parts=json.loads(Path("outputs/prework_sections.json").read_text(encoding="utf-8-sig"))
nb=json.loads((root/"notebooks/02_계산엔진_정리.ipynb").read_text(encoding="utf-8-sig"))
nb["cells"]=nb["cells"][:14]
def set_source(index,text):
    nb["cells"][index]["source"]=text.splitlines(keepends=True)
set_source(0,"# 작업 시작 전 위험도 시험 평가\n\nCSV의 시점·제외조건 설정을 읽는 사전평가입니다. 위에서 아래로 모두 실행하세요. 기존 01·02 노트북과 원본 CSV는 변경하지 않습니다.\n\n시점/가연물-거리 분기는 구현됐지만 법령 자동경고, 모든 해당없음 응답의 타당성, MSDS 파생변수는 미구현입니다. 등급은 잠정값이며 최종 안전판정은 보류합니다.\n\n설정은 data/09_사전평가설정.csv에서 관리합니다. 기존 엑셀을 CSV로 재변환해도 이 추가 설정 파일을 삭제하지 마세요.\n")
src="".join(nb["cells"][1]["source"])
src="import json\n"+src
src += '\nprework_policies = read_database("09_사전평가설정.csv")\n'
set_source(1,src)
set_source(4,"## 2. 원본 DB 연결 확인\n\n원본 H05 질문은 여전히 9개입니다. 아래 사전평가 분기에서 사후 질문을 제외합니다.\n")
src="".join(nb["cells"][9]["source"])
lines=src.splitlines(keepends=True)
tree=ast.parse(src)
replacements=[]
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in ["check_required_answers","calculate_task_risk"]:
        text=parts["check"] if node.name=="check_required_answers" else parts["calc"]
        if node.name=="check_required_answers":text=parts["helpers"]+"\n"+text
        replacements.append((node.lineno-1,node.end_lineno,text+"\n"))
for start,end,text in sorted(replacements,reverse=True):lines[start:end]=[text]
src="".join(lines)+'\nvalidate_prework_policies()\n'
set_source(9,src)
set_source(8,"## 4. 사전 질문 분기와 합산\n\n사후 질문은 시점제외, 가연물이 없을 때 거리 질문은 조건제외로 표시합니다. 선행응답이 빠지면 대기로 남기고 전체 계산을 막습니다. 제외 질문에 예전 응답이 남아도 분자·분모에 포함하지 않습니다. 제외한 질문의 점수는 빈값이며 제외 사유와 기존 입력은 로그에 남습니다.\n\nQ041은 도장 H19에서는 제외하지만, 후속 열풍 건조 H21에서는 착수 전 확인으로 유지합니다. 작업ID별 구체 설정이 기본 설정보다 우선합니다.\n")
set_source(10,"## 5. H05 사전평가 예시\n\n가상 응답입니다. Q026(작업 후 잔불 확인)은 입력하지 않습니다. 적용 질문 8개, 집계 항목 7개, 분자 13.5, 분모 30, 위험지수 45.0, 잠정등급 주의가 예상됩니다. 이전 40.91과의 차이는 0점이던 사후 질문의 분모 3을 제외했기 때문입니다.\n")
src="".join(nb["cells"][11]["source"]).replace('    "Q026": "완료",\n','')
src += '\nprework_question_table = get_prework_questions("H05", h05_answers)\ndisplay(prework_question_table[["항목ID", "확인항목", "적용상태", "제외사유"]])\n'
set_source(11,src)
set_source(12,"## 6. 경계값과 필수응답 확인\n\n등급 구간은 그대로 CSV를 사용합니다. 두 응답만 입력하면 사후 Q026은 누락으로 세지 않으며, Q001에 의존하는 Q002는 선행응답 대기 상태로 구분됩니다.\n")
def add(kind,source):
    cell={"cell_type":kind,"metadata":{},"source":source.splitlines(keepends=True)}
    if kind=="code":cell.update(execution_count=None,outputs=[])
    nb["cells"].append(cell)
add("markdown","## 7. 가연물이 없을 때 거리 질문 제외\n\nQ001=없음이고 Q002를 생략해도 계산할 수 있습니다. Q004의 해당없음 여부나 하부·반대면 착화조건을 자동으로 판단하는 기능은 아닙니다.\n")
add("code",'''no_combustibles = dict(h05_answers)
no_combustibles["Q001"] = "없음"
no_combustibles.pop("Q002")
no_combustibles_summary, no_combustibles_detail = calculate_task_risk("H05", no_combustibles)
display(pd.DataFrame([no_combustibles_summary]))
display(no_combustibles_detail[["항목ID", "사용자응답", "적용상태", "점수", "가중점수", "최대가중점수", "제외사유"]])
''')
add("markdown","## 8. 관련 근거와 사고사례\n\n현재 사전평가의 집계 대표 위험요인만 근거 조회에 사용합니다. 사고사례는 설명용이며 점수에 더하지 않습니다.\n")
add("code",parts["related"])
add("markdown","## 다음 단계\n\n1. 가상 예시가 45.0으로 계산되는지 확인합니다.\n2. 09_사전평가설정.csv의 사전안내를 검토하고 실제 작업 준비상태로 응답해 봅니다.\n3. 화재감시자·불티방지조치 등의 해당없음 선택 가능 조건과 법령 조건을 별도로 구조화합니다. 미검증을 경고 없음으로 처리하지 않습니다.\n\n가열장비 점검 등은 사용 전 알 수 없는 상태를 임의로 정상으로 채우지 않습니다. 현재 단계는 준비상태 평가 시제품이며 실제 사고 확률을 뜻하지 않습니다.\n")
for i,c in enumerate(nb["cells"]):
    c["id"]="prework-"+str(i)
    if c["cell_type"]=="code":c["execution_count"]=None;c["outputs"]=[]
target.write_text(json.dumps(nb,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
print("Created",target,"and",policy_path,"with",len(policies),"policy rows")

