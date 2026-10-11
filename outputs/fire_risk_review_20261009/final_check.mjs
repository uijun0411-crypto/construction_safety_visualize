import fs from 'node:fs/promises';import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const dir="C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009";
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(dir+'/건설현장_화재폭발_DB_v1.1_구조정비본.xlsx'));
for(const [name,range,file] of [
['08_점수규칙DB','S1:Y5','final_bounds.png'],['04_법령_KOSHA기준DB','P1:T4','final_law.png'],
['02_위험요인_입력항목DB','K1:N4','final_groups.png'],['05_MSDS_물질DB','U1:W6','final_pressure.png'],
['06_현장입력_결과','P1:U4','final_results.png'],['06_현장응답상세','M1:O3','final_detail.png'],
['00_작성가이드','A36:H40','final_guide.png']]){
const b=await wb.render({sheetName:name,range,scale:1.1,format:'png'});await fs.writeFile(dir+'/'+file,new Uint8Array(await b.arrayBuffer()));
}
const sh=wb.worksheets.getItem('06_현장입력_결과'),ms=wb.worksheets.getItem('05_MSDS_물질DB');
function set(a,v){sh.getRange(a).values=[[v]];}
const cases=[
 ['vol%', 'M003',0.21,'vol%',10],['ppm','M003',2100,'ppm',10],['%LEL','',25,'%LEL',25],
 ['zero','',0,'%LEL',0],['negative','',-1,'%LEL','농도 확인'],['bad-unit','M003',1,'bad','단위 확인'],
 ['missing-lel','M004',1,'vol%','LEL 확인필요'],['blank','',null,'vol%','']
];
for(const [label,g,q,r,expected] of cases){
 set('G2',g);set('Q2',q);set('R2',r);wb.recalculate();const actual=sh.getRange('Z2').values[0][0];
 if(typeof expected==='number'?typeof actual!=='number'||Math.abs(actual-expected)>1e-8:actual!==expected)throw new Error(label+': '+JSON.stringify(actual));
 console.log('PASS',label);
}
set('G2','M001');set('P2',0);set('S2',0);
ms.getRange('F2').values=[[-5]];ms.getRange('R2').values=[['EQ']];ms.getRange('I2').values=[[0]];wb.recalculate();
console.log('TEMP_DEBUG',JSON.stringify(sh.getRange('P2:AA2').values)); if(sh.getRange('Y2').values[0][0]!==-5 || sh.getRange('AA2').values[0][0]!==0)throw new Error('zero temperature');
console.log('PASS zero temperature');
ms.getRange('R2').values=[['>']];wb.recalculate();
console.log('TEMP_DEBUG',JSON.stringify(sh.getRange('P2:AA2').values)); if(sh.getRange('Y2').values[0][0]!=='경계값·입력 확인')throw new Error('bounded flashpoint');
console.log('PASS bounded flashpoint');
console.log('FINAL_REOPEN_AND_10_TESTS_OK');



