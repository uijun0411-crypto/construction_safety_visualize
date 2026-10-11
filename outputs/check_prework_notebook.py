import json, ast, io, contextlib, math
from pathlib import Path
path=Path("fire_risk_project/notebooks/03_작업시작전_평가.ipynb")
nb=json.loads(path.read_text(encoding="utf-8-sig"))
ns={}
definitions=[]
count=0
for cell in nb["cells"]:
    if cell["cell_type"]!="code":continue
    source="".join(cell["source"]);tree=ast.parse(source)
    definitions.extend(n.name for n in tree.body if isinstance(n,ast.FunctionDef))
    outputs=[]
    def display(value):
        data={"text/plain":repr(value)}
        if hasattr(value,"to_html"):data["text/html"]=value.to_html()
        outputs.append({"output_type":"display_data","data":data,"metadata":{}})
    ns["display"]=display
    capture=io.StringIO()
    with contextlib.redirect_stdout(capture):
        exec(compile(source,str(path),"exec"),ns)
    if capture.getvalue():outputs.insert(0,{"output_type":"stream","name":"stdout","text":capture.getvalue()})
    count+=1;cell["execution_count"]=count;cell["outputs"]=outputs
assert len(definitions)==len(set(definitions)),"duplicate function"
passed=[]
def check(name,condition):
    assert condition,name
    passed.append(name)
def rejects(name,fn,exception=ValueError):
    try:fn()
    except exception:passed.append(name)
    else:raise AssertionError(name)
calc=ns["calculate_task_risk"];get=ns["get_prework_questions"];score=ns["score_answer"]
base=ns["h05_answers"]
s,d=calc("H05",base)
check("H05 eight active questions",s["적용질문수"]==8)
check("H05 excludes post check",s["제외질문수"]==1)
check("H05 denominator 30",s["최대가중점수"]==30)
check("H05 numerator 13.5",s["총가중위험점수"]==13.5)
check("H05 risk 45",s["위험지수"]==45)
check("H05 provisional grade",s["기본위험등급(잠정)"]=="주의")
check("H05 warning unknown",s["강제경고"]=="미검증")
for value in ["완료","미완료","확인불가"]:
    sx,dx=calc("H05",{**base,"Q026":value})
    check("Post response does not change risk "+value,sx["위험지수"]==45)
    row=dx.loc[dx["항목ID"]=="Q026"].iloc[0]
    check("Excluded response logged "+value,row["사용자응답"]==value and row["최대가중점수"]==0 and not row["점수합산대상"])
none=dict(base);none["Q001"]="없음";none.pop("Q002")
sn,dn=calc("H05",none)
check("Distance excluded only after no combustible",sn["적용질문수"]==7 and sn["최대가중점수"]==25.5)
check("Distance excluded row",dn.loc[dn["항목ID"]=="Q002","적용상태"].iloc[0]=="조건제외")
stale,stale_d=calc("H05",{**none,"Q002":0})
check("Stale distance not scored",stale["위험지수"]==sn["위험지수"])
unknown=dict(base);unknown.pop("Q001")
rejects("Missing parent blocks calculation",lambda:calc("H05",unknown))
state=get("H05",unknown)
check("Missing parent leaves distance pending",state.loc[state["항목ID"]=="Q002","적용상태"].iloc[0]=="선행응답필요")
rejects("Invalid parent not used for exclusion",lambda:calc("H05",{**base,"Q001":"?"}))
rejects("Missing applicable distance",lambda:calc("H05",{k:v for k,v in base.items() if k!="Q002"}))
for task in ["H14","H21","H60"]:
    state=get(task)
    check("Post cooling excluded "+task,state.loc[state["항목ID"]=="Q036","적용상태"].iloc[0]=="시점제외")
check("Painting own post ventilation excluded",get("H19").set_index("항목ID").loc["Q041","적용상태"]=="시점제외")
check("Pre heating ventilation retained",get("H21").set_index("항목ID").loc["Q041","적용상태"]=="적용")
check("H13 dependency uses Q006",get("H13",{"Q006":"없음"}).set_index("항목ID").loc["Q002","적용상태"]=="조건제외")
rejects("Extra question",lambda:calc("H05",{**base,"Q005":"없음"}))
rejects("Unknown task",lambda:get("H999"))
rejects("Duplicate normalized ID",lambda:calc("H05",{**base," Q001 ":"없음"}))
rejects("Collection response",lambda:calc("H05",{**base,"Q001":[]}))
rejects("NaN required distance",lambda:calc("H05",{**base,"Q002":float("nan")}))
rejects("Negative distance",lambda:score("Q002",-1))
rejects("Boolean distance",lambda:score("Q002",True))
check("Zero distance valid",score("Q002",0)["점수"]==1)
check("11m current scoring retained",score("Q002",11)["점수"]==0)
rejects("Gas unit conversion still explicit",lambda:score("Q030",1),NotImplementedError)
grade=ns["get_basic_grade"]
check("Grade boundaries unchanged",[grade(v) for v in [0,25,50,75,100]]==["낮음","주의","높음","매우높음","매우높음"])
h29=ns["get_questions_for_task"]("H29")
h29_answers={r["항목ID"]:r["선택지·허용값"].split("/")[0].strip() for _,r in h29.iterrows()}
_,d29=calc("H29",h29_answers)
check("H29 duplication still removed",d29.loc[d29["중복집계그룹"]=="인화성제품사용","집계대표여부"].sum()==1)
policies=ns["prework_policies"]
i=policies.index[(policies["항목ID"]=="Q026") & (policies["적용작업ID"]=="*")][0]
before=policies.at[i,"사전평가사용"]
try:
    policies.at[i,"사전평가사용"]="1"
    sx,_=calc("H05",{**base,"Q026":"완료"})
    check("Phase config data driven",math.isclose(sx["위험지수"],13.5/33*100))
finally:policies.at[i,"사전평가사용"]=before
check("Related standards still work",ns["get_related_standards"](d)["기준ID"].tolist()==["R002","R001","R001"])
check("Accident lookup still works","A001" in ns["get_related_accidents"]("H05")["사고ID"].tolist())
path.write_text(json.dumps(nb,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
print("Executed code cells:",count)
print("Checks passed:",len(passed))
print(json.dumps(s,ensure_ascii=False))
print("Saved:",path)

