import zipfile,xml.etree.ElementTree as E,json
from pathlib import Path
p=Path(r'C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009/건설현장_화재폭발_DB_v1.1_구조정비본.xlsx')
z=zipfile.ZipFile(p);ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ss=[''.join(x.itertext()) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)] if 'xl/sharedStrings.xml' in z.namelist() else []
for name in ['xl/worksheets/sheet5.xml','xl/worksheets/sheet10.xml']:
 root=E.fromstring(z.read(name)); print(name)
 for row in root.findall('m:sheetData/m:row',ns)[:6]:
  vals={}
  for c in row:
   a=c.get('r'); v=c.find('m:v',ns); val=v.text if v is not None else None
   if c.get('t')=='s':val=ss[int(val)]
   if c.get('t')=='inlineStr':val=''.join(c.find('m:is',ns).itertext())
   if a and a.rstrip('0123456789') in ['S','T','U','V','W','X','Y']:vals[a]=val
  print(vals)
 print('MERGES',[x.attrib for x in root.findall('m:mergeCells/m:mergeCell',ns)])

