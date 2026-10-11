import json, io, contextlib, math, ast
from pathlib import Path

path = Path("fire_risk_project/notebooks/02_계산엔진_정리.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8-sig"))
namespace = {}
execution_count = 0
all_definitions = []
for cell in notebook["cells"]:
    if cell["cell_type"] != "code":
        continue
    source = "".join(cell["source"])
    tree = ast.parse(source)
    all_definitions += [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    outputs = []
    def display(value):
        data = {"text/plain": repr(value)}
        if hasattr(value, "to_html"):
            data["text/html"] = value.to_html()
        outputs.append({"output_type": "display_data", "data": data, "metadata": {}})
    namespace["display"] = display
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exec(compile(source, str(path), "exec"), namespace)
    if stream.getvalue():
        outputs.insert(0, {"output_type": "stream", "name": "stdout", "text": stream.getvalue()})
    execution_count += 1
    cell["execution_count"] = execution_count
    cell["outputs"] = outputs
assert len(all_definitions) == len(set(all_definitions)), "Duplicate function definitions"

passed = []
def check(label, condition):
    assert condition, label
    passed.append(label)
def rejects(label, fn, exception=ValueError):
    try:
        fn()
    except exception:
        passed.append(label)
    else:
        raise AssertionError(label)

calc=namespace["calculate_task_risk"]
score=namespace["score_answer"]
grade=namespace["get_basic_grade"]
answers=namespace["h05_answers"]
summary, detail=calc("H05", answers)
check("H05 score preserved", math.isclose(summary["위험지수"], 13.5/33*100))
check("H05 denominator", summary["최대가중점수"]==33)
check("H05 representative count", summary["집계항목수"]==8)
check("H05 provisional grade", summary["기본위험등급(잠정)"]=="주의")
check("Unverified warning retained", summary["강제경고"]=="미검증")
check("Excluded answer denominator", score("Q004","해당없음")["최대가중점수"]==0)
check("Safe answer denominator retained", score("Q004","배치")["최대가중점수"]==6)
check("Zero distance retained", score("Q002",0)["점수"]==1)
check("Distance boundary below", score("Q002",10.9)["점수"]==1)
check("Distance boundary equal", score("Q002",11)["점수"]==0)
expected=["낮음","낮음","주의","주의","높음","높음","매우높음","매우높음"]
check("Grade boundaries", [grade(x) for x in [0,24.99,25,49.99,50,74.99,75,100]]==expected)
check("No denominator grade", grade(None)=="평가불가")
rejects("Negative distance",lambda:score("Q002",-1))
rejects("NaN distance",lambda:score("Q002",float("nan")))
rejects("Infinite distance",lambda:score("Q002",float("inf")))
rejects("Boolean distance",lambda:score("Q002",True))
rejects("Wrong choice",lambda:score("Q004","아무값"))
rejects("Unknown question",lambda:score("Q999","없음"))
rejects("Unknown task",lambda:calc("H999",answers))
rejects("Required answer omitted",lambda:calc("H05",{"Q003":"미실시"}))
rejects("Extra task question",lambda:calc("H05",{**answers,"Q005":"없음"}))
rejects("Normalized ID collision",lambda:calc("H05",{**answers," Q001 ":"없음"}))
rejects("Collection answer",lambda:calc("H05",{**answers,"Q001":["있음"]}))
rejects("Out of range grade",lambda:grade(100.1))
rejects("Derived concentration blocked",lambda:score("Q030",1),NotImplementedError)
h29=namespace["get_questions_for_task"]("H29")
h29_answers={r["항목ID"]:r["선택지·허용값"].split("/")[0].strip() for _,r in h29.iterrows()}
h29_summary,h29_detail=calc("H29",h29_answers)
group=h29_detail.loc[h29_detail["중복집계그룹"]=="인화성제품사용"]
check("H29 two responses retained",len(group)==2)
check("H29 group counted once",int(group["집계대표여부"].sum())==1)
check("H29 group stable tie",group.loc[group["집계대표여부"],"항목ID"].tolist()==["Q007"])
top=namespace["get_top_risks"](detail)
check("Top risks ordered",top["항목ID"].tolist()==["Q004","Q003","Q001"])
missing,_=namespace["check_required_answers"]("H05",{"Q003":"미실시","Q004":"배치"})
check("Missing question count",missing["누락질문수"]==7)
# Ensure grade boundaries really come from the table, rather than fixed Python numbers.
rules=namespace["score_rules"]
indices=rules.index[rules["점수규칙ID"]=="S045"].tolist()
left,right=indices[:2]
old_upper,old_lower=rules.at[left,"기준값2"],rules.at[right,"기준값1"]
try:
    rules.at[left,"기준값2"]="30"
    rules.at[right,"기준값1"]="30"
    check("Grade thresholds data driven",grade(27)=="낮음")
finally:
    rules.at[left,"기준값2"]=old_upper
    rules.at[right,"기준값1"]=old_lower

path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
print("Executed code cells:", execution_count)
print("Unique functions:",len(all_definitions))
print("Checks passed:",len(passed))
print(json.dumps(summary,ensure_ascii=False))
print("Notebook saved:",path)

