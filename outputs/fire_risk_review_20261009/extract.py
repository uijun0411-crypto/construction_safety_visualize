import zipfile, xml.etree.ElementTree as E, json
p=r'C:\Users\uijun\OneDrive\바탕 화면\건설현장_화재폭발_DB_v1.0_최종수정본.xlsx'
z=zipfile.ZipFile(p)
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ss=[ ''.join(x.itertext()) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)] if 'xl/sharedStrings.xml' in z.namelist() else []
rels={r.attrib['Id']:r.attrib['Target'] for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
db={}
for s in E.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns):
 t=rels[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
 path=t.lstrip('/') if t.startswith('/') else 'xl/'+t
 root=E.fromstring(z.read(path)); rows=[]; forms=[]
 for r in root.findall('m:sheetData/m:row',ns):
  vals={}
  for c in r.findall('m:c',ns):
   v=c.find('m:v',ns); typ=c.get('t'); val=v.text if v is not None else ''
   if typ=='s': val=ss[int(val)]
   elif typ=='inlineStr': val=''.join(c.find('m:is',ns).itertext())
   f=c.find('m:f',ns)
   if f is not None: forms.append([c.get('r'),f.text]); val={'value':val,'formula':f.text}
   if val!='': vals[c.get('r')]=val
  if vals: rows.append(vals)
 db[s.get('name')]={'rows':rows,'forms':forms}

from pathlib import Path
Path(r'C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009/source.json').write_text(json.dumps(db,ensure_ascii=False),encoding='utf-8')
print('source extracted')
print('features',[n for n in z.namelist() if any(k in n for k in ['table','drawing','comment','vba'])])

