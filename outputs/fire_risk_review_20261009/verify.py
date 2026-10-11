import zipfile,xml.etree.ElementTree as E,json
from pathlib import Path
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def read(p):
 z=zipfile.ZipFile(p); ss=[''.join(x.itertext()) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)] if 'xl/sharedStrings.xml' in z.namelist() else []
 rels={r.attrib['Id']:r.attrib['Target'] for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))};out={}
 for s in E.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns):
  t=rels[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]; root=E.fromstring(z.read(t.lstrip('/') if t.startswith('/') else 'xl/'+t));cells={}
  for c in root.findall('m:sheetData/m:row/m:c',ns):
   v=c.find('m:v',ns);val=v.text if v is not None else None
   if c.get('t')=='s':val=ss[int(val)]
   elif c.get('t')=='inlineStr':val=''.join(c.find('m:is',ns).itertext())
   elif val is not None and c.get('t') not in ['str','e']: 
    try:val=float(val)
    except ValueError:pass
   f=c.find('m:f',ns)
   if val is not None or f is not None:cells[c.get('r')]={'value':val,'formula':f.text if f is not None else None}
  out[s.get('name')]={'cells':cells,'validations':[(x.get('sqref'),''.join(x.itertext())) for x in root.findall('m:dataValidations/m:dataValidation',ns)]}
 return out
src=read(r'C:/Users/uijun/OneDrive/바탕 화면/건설현장_화재폭발_DB_v1.0_최종수정본.xlsx')
dst=read(r'C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009/건설현장_화재폭발_DB_v1.1_구조정비본.xlsx')
assert list(src)==list(dst)
for name in src:
 if name in ['01_공정_세부작업DB','03_사고데이터','07_기상데이터','99_코드표']:
  assert src[name]['cells']==dst[name]['cells'],name+' changed'
 print(name,'validations',len(src[name]['validations']),len(dst[name]['validations']))
print('UNCHANGED_SOURCE_SHEETS_OK')
print('RESULT_ORIGINAL_VALIDATIONS',src['06_현장입력_결과']['validations'])
print('RESULT_FINAL_VALIDATIONS',dst['06_현장입력_결과']['validations'])
for name in ['02_위험요인_입력항목DB','04_법령_KOSHA기준DB','05_MSDS_물질DB','08_점수규칙DB']:
 diffs=[(a,v,dst[name]['cells'].get(a)) for a,v in src[name]['cells'].items() if dst[name]['cells'].get(a)!=v]
 print('CHANGED_ORIGINAL_CELLS',name,json.dumps(diffs,ensure_ascii=False))
out=dst['06_현장입력_결과']['cells']
assert not any(out.get(c+str(r),{}).get('formula') for c in ['P','Q','R','S'] for r in range(2,501))
assert sum(bool(x['formula']) for x in out.values())==499*8
assert all(out.get(c+'2',{}).get('formula') for c in ['T','U','V','W','X','Y','Z','AA'])
for n,d in dst.items():
 errors=[(a,v['value']) for a,v in d['cells'].items() if v['value'] in ['#REF!','#DIV/0!','#VALUE!','#NAME?','#NUM!']]
 assert not errors,(n,errors)
print('FORMULA_STRUCTURE_OK')
print('SIZE',Path(r'C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009/건설현장_화재폭발_DB_v1.1_구조정비본.xlsx').stat().st_size)

