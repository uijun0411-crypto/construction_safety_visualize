import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load('C:/Users/uijun/OneDrive/바탕 화면/건설현장_화재폭발_DB_v1.0_최종수정본.xlsx'));
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:2000})).ndjson);
for(const [name,range,file] of [['08_점수규칙DB','A1:D8','before_rules.png'],['06_현장입력_결과','P1:U4','before_results.png']]){
 const b=await wb.render({sheetName:name,range,scale:1.5,format:'png'});
 await fs.writeFile('C:/Users/uijun/OneDrive/바탕 화면/python-study/outputs/fire_risk_review_20261009/'+file,new Uint8Array(await b.arrayBuffer()));
}
console.log('RENDERED');

