import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const dir="C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009";
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load('C:/Users/uijun/OneDrive/바탕 화면/건설현장_화재폭발_DB_v1.0_최종수정본.xlsx'));
const raw=JSON.parse(await fs.readFile(dir+'/source.json','utf8'));
const sheet=n=>wb.worksheets.getItem(n);
const put=(s,a,v)=>sheet(s).getRange(a).values=[[v]];
const note=(s,a,t)=>{const r=sheet(s).getRange(a);r.values=[[t]];r.format.wrapText=true;};
const records=n=>raw[n].rows.slice(1).map(row=>Object.fromEntries(Object.entries(row).map(([k,v])=>[k.replace(/\d/g,''),v])));
const rules=records('08_점수규칙DB'), qs=records('02_위험요인_입력항목DB'), mats=records('05_MSDS_물질DB');
const version='v1.1-draft';
function headers(name,range,values){const r=sheet(name).getRange(range);r.values=[values];r.format.fill='#E8EEF5';r.format.font={bold:true,color:'#17365D'};r.format.wrapText=true;r.format.rowHeight=44;r.format.columnWidth=19;}

// Canonical work mapping is D; retain P as audit reference.
put('04_법령_KOSHA기준DB','P1','이전적용작업ID_참고');
headers('04_법령_KOSHA기준DB','Q1:T1',['적용조건식_JSON','위반조건식_JSON','조건검토상태','자동경고사용여부']);
for(let r=2;r<=18;r++){
 put('04_법령_KOSHA기준DB','S'+r,'검토필요');
 put('04_법령_KOSHA기준DB','T'+r,0);
}
sheet('04_법령_KOSHA기준DB').getRange('P1').format.wrapText=true;
sheet('04_법령_KOSHA기준DB').getRange('P:P').format.columnWidth=28;

// Explicit bounds and fixed normalization base. Scores and weights stay unchanged.
headers('08_점수규칙DB','S1:Y1',['하한포함','상한포함','정규화최대점수','규칙역할','규칙버전','적용조건식_JSON','조건검토상태']);
for(let i=0;i<rules.length;i++){
 const r=i+2,x=rules[i],id=Number(x.A.slice(1));
 for(const c of ['B','I','J','L','M']) if(x[c]!==undefined && x[c]!=='' && Number.isFinite(Number(x[c]))) put('08_점수규칙DB',c+r,Number(x[c]));
 put('08_점수규칙DB','U'+r,id<=40?3:null);
 put('08_점수규칙DB','V'+r,id>=41?'최종계산':Number(x.M)===0?'분기·제외':'점수');
 put('08_점수규칙DB','W'+r,version);
 put('08_점수규칙DB','Y'+r,id>=41?'계산정의 확인':'적용조건 검토필요');
 if(x.H==='구간'){
  put('08_점수규칙DB','S'+r,['S016','S018'].includes(x.A)?0:1);
  put('08_점수규칙DB','T'+r,['S016','S018'].includes(x.A)||x.A==='S045'&&x.I==='75'?1:0);
 }
 if(['>','>='].includes(x.H))put('08_점수규칙DB','S'+r,x.H==='>='?1:0);
 if(['<','<='].includes(x.H))put('08_점수규칙DB','T'+r,x.H==='<='?1:0);
}
for(const c of ['B','I','J','L','M','S','T','U'])sheet('08_점수규칙DB').getRange(c+'2:'+c+'139').setNumberFormat('0.00');
note('08_점수규칙DB','G127','계산포함 항목의 정규화최대점수(3) × 가중치 합계');
note('08_점수규칙DB','R127','U열의 정규화최대점수 사용. 선택지 점수의 MAX를 사용하지 않음. 해당없음·분기용 제외. 동일 작업의 중복집계그룹은 대표 응답 1건만 포함.');
note('08_점수규칙DB','R4','점수 경계는 원안 유지: 거리 < 11m. R002의 법령 적용 경계와 별개이며 정확히 11m인 경우의 법령 판정은 검토 필요.');
note('08_점수규칙DB','R5','점수 경계는 원안 유지: 거리 >= 11m. 0점만으로 화재감시자 비대상 판정 금지. 하부·반대면 착화조건도 별도 확인.');
note('08_점수규칙DB','R135','강제경고여부=1은 후보 표시. 04의 자동경고사용여부=1이며 적용조건식·위반조건식 검토가 완료된 경우만 자동 판정. 검토 미완료는 확인필요이며 경고없음으로 처리 금지.');
note('08_점수규칙DB','R136','검토 완료된 적용 규칙을 평가한 결과 위반조건이 모두 거짓일 때만 경고 없음. 미검토·미응답은 확인필요.');
note('08_점수규칙DB','R129','분모>0과 함께 필수응답·조건분기·단위·규칙매칭 검증 완료 필요. 미완료는 잠정값이며 최종 안전등급 확정 금지.');
note('08_점수규칙DB','R139','가중점수>0인 집계 대표항목을 내림차순 정렬. 동일 작업의 중복집계그룹은 1회 출력. 상위 3~5개.');

// Preserve both questions, explicitly deduplicate only within a task.
headers('02_위험요인_입력항목DB','M1:N1',['중복집계그룹','그룹집계방식']);
for(let i=0;i<qs.length;i++){
 const q=qs[i],group=['Q007','Q038'].includes(q.A)?'인화성제품사용':q.A;
 put('02_위험요인_입력항목DB','M'+(i+2),group);
 put('02_위험요인_입력항목DB','N'+(i+2),'MAX_PER_TASK');
}
headers('06_현장응답상세','N1:O1',['중복집계그룹','집계대표여부']);

// Keep raw vapor pressure and add numeric interval columns.
headers('05_MSDS_물질DB','U1:W1',['증기압_하한','증기압_상한','증기압_값형식']);
for(let i=0;i<mats.length;i++){
 const v=mats[i].J,r=i+2;if(v===undefined)continue;
 const parts=String(v).split('~').map(Number);
 if(parts.every(Number.isFinite)){
  put('05_MSDS_물질DB','U'+r,parts[0]);put('05_MSDS_물질DB','V'+r,parts.at(-1));
  put('05_MSDS_물질DB','W'+r,parts.length===2?'범위':'단일값');
 }
}
sheet('05_MSDS_물질DB').getRange('U2:V17').setNumberFormat('0.###');

// Replace stale result formulas, retain input cells and empty engine-owned outputs.
const result=sheet('06_현장입력_결과');
result.getRange('P2:AA500').clear({applyTo:'contents'});
const lookup=(r,col,numeric)=>{
 const match="MATCH(G"+r+",'05_MSDS_물질DB'!$A$2:$A$17,0)";
 const ref="INDEX('05_MSDS_물질DB'!$"+col+"$2:$"+col+"$17,"+match+")";
 return '=IF(G'+r+'="","",IF(COUNTIF(\'05_MSDS_물질DB\'!$A$2:$A$17,G'+r+')<>1,"물질ID 확인",IF('+ (numeric?'COUNT('+ref+')=0':ref+'=""')+',"",'+ref+')))';
};
const formulas=[];
for(let r=2;r<=500;r++){
 formulas.push([
 lookup(r,'R',false),lookup(r,'F',true),lookup(r,'S',false),lookup(r,'G',true),lookup(r,'I',true),
 '=IF(OR(ISBLANK(P'+r+'),NOT(ISNUMBER(U'+r+'))),"",IF(AND(ISNUMBER(P'+r+'),ISNUMBER(U'+r+'),OR(T'+r+'="=",T'+r+'="EQ")),U'+r+'-P'+r+',"경계값·입력 확인"))',
 '=IF(OR(ISBLANK(Q'+r+'),R'+r+'=""),"",IF(NOT(ISNUMBER(Q'+r+')),"농도 확인",IF(Q'+r+'<0,"농도 확인",IF(R'+r+'="%LEL",Q'+r+',IF(OR(R'+r+'="vol%",R'+r+'="ppm"),IF(AND(ISNUMBER(W'+r+'),W'+r+'>0),IF(R'+r+'="ppm",Q'+r+'/10000,Q'+r+')/W'+r+'*100,"LEL 확인필요"),"단위 확인")))))',
 '=IF(OR(ISBLANK(S'+r+'),NOT(ISNUMBER(X'+r+'))),"",IF(AND(ISNUMBER(S'+r+'),ISNUMBER(X'+r+')),X'+r+'-S'+r+',"온도 확인"))'
 ]);
}
result.getRange('T2:AA500').formulas=formulas;
for(const c of ['P','Q','S','U','W','X','Y','Z','AA'])result.getRange(c+'2:'+c+'500').setNumberFormat('0.##');
for(const c of ['R','T','V'])result.getRange(c+'2:'+c+'500').setNumberFormat('@');
result.getRange('R2:R500').dataValidation={rule:{type:'list',values:['vol%','ppm','%LEL']}};

// Append review notes to existing guide, leaving original content intact.
const guide=sheet('00_작성가이드');
const guideRows=[
 ['수정본 상태','v1.1-draft / 2026-10-09. DB 구조 정비본. 점수·가중치·법령 적합성 확정본이 아님.'],
 ['결과 수식','T:X는 G열 물질ID 조회. Y=인화점−현장기온, Z=단위 환산 후 LEL 대비율, AA=자연발화온도−표면온도. 2~500행 적용.'],
 ['입력·엔진 구분','P:S는 사용자 입력. AB:AV의 점수·등급·경고 등은 Python 엔진 결과 저장용이며 이 파일에서 자동 산출하지 않음.'],
 ['인화점 경계값','연산자가 = 또는 EQ인 정확한 인화점만 Y에서 계산. >, >=, <, <=, ~ 등은 경계값·입력 확인 표시 후 추가 해석. 빈칸을 0으로 채우지 않음.'],
 ['농도 단위','ppm은 vol%로 나누기 10000 후 변환. %LEL은 이미 대비율이므로 그대로 사용. vol%·ppm 입력은 양수 LEL 값이 있어야 계산.'],
 ['점수 분모','08 U열 정규화최대점수=3 사용. Σ(3×포함 가중치). 규칙 행의 실제 점수 MAX를 분모로 사용하지 않음. 해당없음·분기용 제외.'],
 ['중복 집계','평가ID+작업ID+02 중복집계그룹별 가중점수가 가장 높은 응답 1건을 대표로 반영. 동점은 항목ID 오름차순. 대표 응답의 분자·분모를 함께 사용.'],
 ['H29 처리','Q007·Q038 응답은 모두 보존. 동일 작업에서 인화성제품사용 그룹으로 한 번만 반영. 미응답을 0점으로 간주하지 않음.'],
 ['작업ID 기준열','04 D열 적용작업ID를 공식 연결 열로 사용. P열 이전적용작업ID_참고는 이력 보존용이며 엔진 조회에서 제외.'],
 ['수치 구간','08 S/T열은 하한/상한 포함 여부(1=포함, 0=제외). S016·S018은 하한 제외/상한 포함, S017·S045는 하한 포함/상한 제외. S045 마지막 구간은 100 포함.'],
 ['11m 경계 검토','S002 점수 기준 <11 / >=11은 보존. 법령 R002의 11m 경계 및 하부·반대면 조건은 별도 검토. 거리 점수 0을 법적 비대상으로 사용 금지.'],
 ['자동경고 상태','04 Q/R열 조건식은 검토 후 입력. T열 자동경고사용여부는 현재 모두 0. 이는 경고 없음이 아니라 자동판정 미준비를 뜻함. 기존 강제경고여부는 보존.'],
 ['조건식 형식','후속 엔진은 JSON 조건트리 사용 권장: all/any/not 및 field/op/value. 빈 조건식은 참이나 거짓으로 자동 해석하지 않고 확인필요로 반환.'],
 ['평가 유효성','분모 0, 필수응답 누락, 알 수 없는 선택지, 적용조건 미확인, 단위 오류는 상태로 구분. 유효성이 확보되지 않으면 최종 안전등급을 확정하지 않음.'],
 ['증기압','05 J열 원문과 K열 단위를 보존. U/V에 하한·상한을 분리. 단위와 측정온도가 다르면 값을 직접 비교하지 않음.'],
 ['검토 우선순위','법령 조건식과 경계값 확인 → 점수·가중치 검토 → 질문 추출 → 규칙엔진 → 경계·결측·중복·경고 시나리오 검증.'],
 ['검증 범위','수식·ID·선택지·범위 구조를 검증. 법령 최신성, 위험지수의 현장 타당성, 실제 Excel 앱 재계산은 별도 확인 대상.']
];
guide.mergeCells('A36:H36');put('00_작성가이드','A36','v1.1 수정 및 구현 기준');
guide.getRange('A36:H36').format.fill='#E8EEF5';guide.getRange('A36:H36').format.font={bold:true,color:'#17365D'};
for(let i=0;i<guideRows.length;i++){
 const r=37+i;put('00_작성가이드','A'+r,guideRows[i][0]);guide.mergeCells('B'+r+':H'+r);put('00_작성가이드','B'+r,guideRows[i][1]);
 guide.getRange('A'+r+':H'+r).format.wrapText=true;guide.getRange('A'+r+':H'+r).format.rowHeight=44;
}
for(const a of ['R4','R5','R127','R129','R135','R136','R139'])sheet('08_점수규칙DB').getRange(a).format.rowHeight=90;
sheet('08_점수규칙DB').getRange('R:R').format.columnWidth=65;
for(const [n,a] of [['08_점수규칙DB','S2:Y139'],['04_법령_KOSHA기준DB','Q2:T18'],['02_위험요인_입력항목DB','M2:N42'],['05_MSDS_물질DB','U2:W17'],['06_현장응답상세','N2:O500']]){
 const rng=sheet(n).getRange(a);rng.format.font={name:'맑은 고딕',size:10,color:'#222222'};rng.format.verticalAlignment='center';rng.format.wrapText=true;
}
sheet('08_점수규칙DB').getRange('S2:U139').setNumberFormat('0');
sheet('08_점수규칙DB').getRange('B2:B139').setNumberFormat('0');
sheet('04_법령_KOSHA기준DB').getRange('T2:T18').setNumberFormat('0');
guide.getRange('A36:H53').format.verticalAlignment='center';
wb.recalculate();
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:15},maxChars:1800})).ndjson);
for(const [name,range,file] of [
 ['08_점수규칙DB','A1:D8','after_rules.png'],['08_점수규칙DB','S1:Y6','after_bounds.png'],
 ['04_법령_KOSHA기준DB','P1:T5','after_law.png'],['02_위험요인_입력항목DB','K1:N9','after_groups.png'],
 ['05_MSDS_물질DB','U1:W7','after_pressure.png'],['06_현장입력_결과','P1:U4','after_results.png'],
 ['06_현장응답상세','M1:O4','after_detail.png'],['00_작성가이드','A36:H43','after_guide.png']
]){
 const b=await wb.render({sheetName:name,range,scale:1.2,format:'png'});await fs.writeFile(dir+'/'+file,new Uint8Array(await b.arrayBuffer()));
}
const path=dir+'/건설현장_화재폭발_DB_v1.1_구조정비본.xlsx';
await (await SpreadsheetFile.exportXlsx(wb)).save(path);
console.log('EXPORTED '+path);
// Test representative formulas on a disposable in-memory scenario, after final export.
const cases=[
 {label:'vol-percent',g:'M003',q:0.21,r:'vol%',expect:10},
 {label:'ppm',g:'M003',q:2100,r:'ppm',expect:10},
 {label:'direct-lel',g:'',q:25,r:'%LEL',expect:25},
 {label:'zero-lel',g:'',q:0,r:'%LEL',expect:0},
];
for(const t of cases){
 result.getRange('G2').values=[[t.g]];result.getRange('Q2:R2').values=[[t.q,t.r]];wb.recalculate();
 const actual=result.getRange('Z2').values[0][0];console.log('TEST',t.label,JSON.stringify(actual),t.expect);
 if(typeof actual!=='number'||Math.abs(actual-t.expect)>1e-8)throw new Error('Formula test failed '+t.label);
}
console.log('TESTS_OK');

