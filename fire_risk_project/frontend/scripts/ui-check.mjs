// Run with the API running on a disposable test database, never production.
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
const endpoint = process.env.UI_TEST_API || 'http://127.0.0.1:8000/api';
async function post(path, body) {
  const r = await fetch(endpoint + path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  assert.equal(r.status,200,await r.clone().text());return r.json();
}
try {
  const inputs = await server.ssrLoadModule('/src/assessment-inputs.jsx');
  const result = await server.ssrLoadModule('/src/assessment-result.jsx');
  const render = (Component,props) => renderToStaticMarkup(React.createElement(Component,props));
  const schema = await post('/questions',{answers:{}});
  const initial = render(inputs.AssessmentQuestionGroups,{schema,answers:{},onChange:()=>{}});
  assert.match(initial,/id="question-Q002"[^>]*disabled/);
  assert.match(initial,/01<\/em>/);
  assert.match(initial,/평가 제외/);
  assert.equal((initial.match(/id="watch-W001"/g)||[]).length,1);
  assert.equal((initial.match(/id="watch-W004"/g)||[]).length,1);
  assert.doesNotMatch(initial,/watch-W002|watch-W003/);
  const numbers = [...initial.matchAll(/<em>(\d+)<\/em>/g)].map(m=>Number(m[1]));
  assert.deepEqual(numbers,numbers.map((_,i)=>i+1));
  const watchers = render(inputs.FireWatchConditions,{questions:schema.watcher_questions,extras:{},onChange:()=>{}});
  assert.equal((watchers.match(/value="" selected=""/g)||[]).length,3);
  assert.doesNotMatch(watchers,/watch-W002|watch-W003/);
  assert.match(watchers,/value="아니오">예외조건 미충족/);
  const absent = await post('/questions',{answers:{Q001:'없음'}});
  assert.equal(absent.questions.find(q=>q['항목ID']==='Q002')['적용상태'],'조건제외');
  const answers = {Q001:'있음',Q002:5,Q003:'미실시',Q004:'미배치',Q018:'용접방화포 미사용',Q019:'없음',Q020:'없음',Q025:'적정'};
  const present = await post('/questions',{answers});
  assert.equal(present.questions.find(q=>q['항목ID']==='Q002')['적용상태'],'적용');
  const activeMarkup=render(inputs.AssessmentQuestionGroups,{schema:present,answers,onChange:()=>{}});
  assert.doesNotMatch(activeMarkup,/id="question-Q002"[^>]*disabled/);
  const record=await post('/evaluate',{site_name:'임시 DB UI 자동검증',answers,watcher_ui_version:'integrated-v1',materials:{ids:['M008']},watcher_answers:{W001:'예',W002:'아니오',W003:'아니오',W004:'아니오'}});
  const markup=render(result.default,{record});
  for(const title of ['위험요인 분석','위험기여도 TOP 5','필요한 조치','판단 근거','화재감시자 배치 및 예외조건 확인','현장 가연물 정보','SikaCor Thinner-8'])assert.ok(markup.includes(title),title);
  assert.ok(markup.includes(record['요약']['위험지수'].toFixed(2)));
  assert.doesNotMatch(markup,/<details[^>]*open/);
  assert.doesNotMatch(markup,/NaN|undefined|강제경고 0건/);
  const representatives=record['응답상세'].filter(r=>r['집계대표여부']&&r['가중점수']>0);
  const contributions=representatives.reduce((sum,r)=>sum+r['가중점수']/record['요약']['최대가중점수']*100,0);
  assert.ok(Math.abs(contributions-record['요약']['위험지수'])<0.02);
  const refs=(await server.ssrLoadModule('/src/reference-data.json')).default;
  const linked=record['응답상세'].flatMap(r=>(r['관련기준ID']||'').split(';'));
  const action=refs.standards.find(s=>linked.includes(s['기준ID'])&&s['필수조치']);
  assert.ok(action&&markup.includes(action['필수조치']));
  console.log('PASS: live API + React rendering, question conditions, W mapping, unset values, score contribution, DB actions and closed details.');
  console.log('Real engine score:',record['요약']['위험지수']);
} finally {await server.close();}
