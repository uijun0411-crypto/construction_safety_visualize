
import zipfile,xml.etree.ElementTree as E,copy,re,io
from pathlib import Path
src=Path(r'C:/Users/uijun/OneDrive/바탕 화면/건설현장_화재폭발_DB_v1.0_최종수정본.xlsx')
dst=Path(r'C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009/건설현장_화재폭발_DB_v1.1_구조정비본.xlsx')
s=zipfile.ZipFile(src); d=zipfile.ZipFile(dst)
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
N={'m':NS};tag=lambda x:'{'+NS+'}'+x
E.register_namespace('',NS)
E.register_namespace('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
def strs(z):return [''.join(x.itertext()) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',N)] if 'xl/sharedStrings.xml' in z.namelist() else []
ds=strs(d)
styles=E.fromstring(s.read('xl/styles.xml'))
fonts=styles.find('m:fonts',N);fills=styles.find('m:fills',N);xfs=styles.find('m:cellXfs',N)
def font(bold):
 f=E.Element(tag('font'))
 E.SubElement(f,tag('sz'),{'val':'10'});E.SubElement(f,tag('name'),{'val':'맑은 고딕'})
 E.SubElement(f,tag('color'),{'rgb':'FF17365D' if bold else 'FF222222'})
 if bold:E.SubElement(f,tag('b'))
 fonts.append(f);return len(fonts)-1
normal_font=font(False);head_font=font(True)
fi=E.Element(tag('fill'));pf=E.SubElement(fi,tag('patternFill'),{'patternType':'solid'});E.SubElement(pf,tag('fgColor'),{'rgb':'FFE8EEF5'});E.SubElement(pf,tag('bgColor'),{'indexed':'64'});fills.append(fi)
head_fill=len(fills)-1
def style(num=0,header=False):
 xf=E.Element(tag('xf'),{'numFmtId':str(num),'fontId':str(head_font if header else normal_font),'fillId':str(head_fill if header else 0),'borderId':'0','xfId':'0','applyAlignment':'1','applyFont':'1','applyFill':'1','applyNumberFormat':'1'})
 E.SubElement(xf,tag('alignment'),{'vertical':'center','horizontal':'right' if num else 'left','wrapText':'1'})
 xfs.append(xf);return str(len(xfs)-1)
text_style=style();int_style=style(1);num_style=style(2);head_style=style(header=True)
for el in [fonts,fills,xfs]:el.set('count',str(len(el)))
def serial(root,original):
 data=E.tostring(root,encoding='utf-8',xml_declaration=True).decode('utf-8')
 # Preserve declarations referenced by mc:Ignorable or other prefix-valued attributes.
 original=original.decode('utf-8')
 start=data.index('<',data.index('?>')+2);end=data.index('>',start)
 for prefix,url in re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"',original.split('>',2)[1] if original.startswith('<?xml') else original.split('>',1)[0]):
  if 'xmlns:'+prefix+'=' not in data[start:end]:
   data=data[:end]+' xmlns:'+prefix+'="'+url+'"'+data[end:];end=data.index('>',start)
 return data.encode('utf-8')
def cn(addr):
 letters=re.match('[A-Z]+',addr).group();n=0
 for c in letters:n=n*26+ord(c)-64
 return n
def rn(addr):return int(re.search('[0-9]+',addr).group())
def maps(root):
 return {c.get('r'):c for c in root.findall('m:sheetData/m:row/m:c',N)}
def converted(c):
 c=copy.deepcopy(c)
 if c.get('t')=='s':
  val=ds[int(c.find('m:v',N).text)]
  for v in list(c):
   if v.tag in [tag('v'),tag('is')]:c.remove(v)
  c.set('t','inlineStr');i=E.SubElement(c,tag('is'));E.SubElement(i,tag('t')).text=val
 c.attrib.pop('s',None)
 return c
updates={}
# worksheet indices are verified from original workbook order.
for idx in [1,3,5,6,7,10,11]:
 path='xl/worksheets/sheet'+str(idx)+'.xml'
 orig_bytes=s.read(path);root=E.fromstring(orig_bytes);target=E.fromstring(d.read(path));old=maps(root);new=maps(target);data=root.find('m:sheetData',N)
 rows={int(r.get('r')):r for r in data}
 def row(r):
  if r not in rows:
   el=E.Element(tag('row'),{'r':str(r)});rows[r]=el
   pos=next((j for j,x in enumerate(data) if int(x.get('r'))>r),len(data));data.insert(pos,el)
  return rows[r]
 def setcell(addr,c,sty=None):
  r=row(rn(addr))
  for prev in list(r):
   if prev.get('r')==addr:r.remove(prev)
  if c is None:return
  c=converted(c)
  if sty is None and addr in old and old[addr].get('s') is not None:c.set('s',old[addr].get('s'))
  elif sty is not None:c.set('s',sty)
  pos=next((j for j,x in enumerate(r) if cn(x.get('r'))>cn(addr)),len(r));r.insert(pos,c)
 if idx==1:
  for a,c in new.items():
   if rn(a)>=36:setcell(a,c,head_style if rn(a)==36 else text_style)
  for r in range(36,54):row(r).set('ht','40' if r>36 else '24');row(r).set('customHeight','1')
  merges=root.find('m:mergeCells',N)
  if merges is None:
   merges=E.Element(tag('mergeCells'))
   # mergeCells belongs after sheetData and existing protection/filter elements, before validations.
   following=['phoneticPr','conditionalFormatting','dataValidations','hyperlinks','printOptions','pageMargins','pageSetup','headerFooter','rowBreaks','colBreaks','drawing','extLst']
   pos=next((j for j,x in enumerate(root) if x.tag.split('}')[-1] in following),len(root));root.insert(pos,merges)
  for el in target.findall('m:mergeCells/m:mergeCell',N):
   if rn(el.get('ref').split(':')[0])>=36:merges.append(copy.deepcopy(el))
  merges.set('count',str(len(merges)))
 elif idx in [3,5,6,10,11]:
  first={3:13,5:17,6:21,10:19,11:14}[idx]
  for a,c in new.items():
   if cn(a)>=first and (rn(a)==1 or c.find('m:v',N) is not None or c.find('m:is',N) is not None):
    st=head_style if rn(a)==1 else int_style if idx==5 and cn(a)==20 or idx==10 and cn(a) in [19,20,21] else num_style if idx==6 and cn(a) in [21,22] else text_style
    setcell(a,c,st)
  row(1).set('ht','42');row(1).set('customHeight','1')
  if idx==5:setcell('P1',new['P1'],head_style)
  if idx==10:
   for a in ['R4','R5','G127','R127','R129','R135','R136','R139']:setcell(a,new[a],text_style)
   for a,c in old.items():
    if rn(a)>1 and cn(a) in [2,9,10,12,13]:
     newc=copy.deepcopy(c);newc.set('s',int_style if cn(a)==2 else num_style)
     # Existing strings, numbers and provenance remain from the original XML.
     old[a].set('s',newc.get('s'))
   for r in [4,5,127,129,135,136,139]:row(r).set('ht','90');row(r).set('customHeight','1')
 else:
  for a in list(old):
   if rn(a)>=2 and 16<=cn(a)<=27:setcell(a,None)
  for a,c in new.items():
   if rn(a)>=2 and 20<=cn(a)<=27:
    setcell(a,c,text_style if cn(a) in [20,22] else num_style)
  dvs=root.find('m:dataValidations',N)
  if dvs is not None:
   for el in dvs:
    if el.get('sqref')=='AH2:AH500':el.set('sqref','AN2:AN500')
  else:
   dvs=E.Element(tag('dataValidations'));root.append(dvs)
  for el in target.findall('m:dataValidations/m:dataValidation',N):
   if el.get('sqref')=='R2:R500':dvs.append(copy.deepcopy(el))
  dvs.set('count',str(len(dvs)))
 # Preserve original widths, adding only widths for new fields.
 ranges={1:[],3:[(13,14,22)],5:[(16,16,29),(17,20,23)],6:[(21,23,20)],7:[],10:[(18,18,65),(19,21,18),(22,25,25)],11:[(14,15,23)]}[idx]
 if ranges:
  cols=root.find('m:cols',N)
  if cols is None:cols=E.Element(tag('cols'));root.insert(list(root).index(data),cols)
  for lo,hi,width in ranges:
   # Split existing spans before overriding this bounded range.
   for el in list(cols):
    a,b=int(el.get('min')),int(el.get('max'))
    if b<lo or a>hi:continue
    cols.remove(el)
    if a<lo:
     x=copy.deepcopy(el);x.set('max',str(lo-1));cols.append(x)
    if b>hi:
     x=copy.deepcopy(el);x.set('min',str(hi+1));cols.append(x)
   cols.append(E.Element(tag('col'),{'min':str(lo),'max':str(hi),'width':str(width),'customWidth':'1'}))
  cols[:]=sorted(cols,key=lambda x:int(x.get('min')))
 dim=root.find('m:dimension',N)
 if dim is not None:dim.set('ref',{1:'A1:H53',3:'A1:N42',5:'A1:T18',6:'A1:W17',7:'A1:AV500',10:'A1:Y139',11:'A1:O500'}[idx])
 updates[path]=serial(root,orig_bytes)
updates['xl/styles.xml']=serial(styles,s.read('xl/styles.xml'))
work=E.fromstring(s.read('xl/workbook.xml'));calc=work.find('m:calcPr',N)
if calc is None:calc=E.SubElement(work,tag('calcPr'))
calc.set('calcMode','auto');calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1')
updates['xl/workbook.xml']=serial(work,s.read('xl/workbook.xml'))
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as zout:
 for item in s.infolist():zout.writestr(item,updates.get(item.filename,s.read(item.filename)))
d.close();s.close();dst.write_bytes(buffer.getvalue())
print('Native workbook preservation complete',dst.stat().st_size)

