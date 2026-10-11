import runpy
ns0=runpy.run_path("outputs/check_prework_notebook.py")
ns=ns0["ns"]
calc=ns["calculate_task_risk"]
base=ns["h05_answers"]
review=ns["review_not_applicable"]
for q in ["Q003","Q004"]:
 try: calc("H05",{**base,q:"해당없음"})
 except ValueError as e: assert "계산 보류" in str(e)
 else: raise AssertionError(q)
for distance,expected in [(10.99,True),(11,True),(11.01,False)]:
 r=review("H05",{**base,"Q002":distance}).set_index("항목ID").loc["Q004"]
 assert ("Q002" in r["확인된검토신호"])==expected
for q in ["Q019","Q020"]:
 r=review("H05",{**base,q:"있음"}).set_index("항목ID").loc["Q004"]
 assert q in r["확인된검토신호"]
r=review("H05",{**base,"Q001":"없음","Q002":0}).set_index("항목ID").loc["Q004"]
assert "Q002" not in r["확인된검토신호"] and "Q002" in r["미확인신호"]
for q in ["Q003","Q004"]:
 r=review("H05",{**base,"Q001":"없음",q:"해당없음"}).set_index("항목ID")
 assert bool(r.loc[q,"계산보류"])
assert len(review("H05",{}))==2
assert calc("H05",base)[0]["위험지수"]==45
print("Additional applicability checks: 12 passed")

