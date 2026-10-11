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

from collections import Counter
d=dst['06_현장입력_결과']['cells']
print('SAMPLE',[(a,d.get(a)) for a in ['P51','S2','T2','Y2','Z2']])
print('formula_count',sum(v['formula'] is not None for v in d.values()))
print('formula_cols',Counter(a.rstrip('0123456789') for a,v in d.items() if v['formula']))
for n in ['08_점수규칙DB','04_법령_KOSHA기준DB']:
 print(n,[(a,dst[n]['cells'].get(a)) for a in ['S2','T2','U2','V2','W2','Y2']])

