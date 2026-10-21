import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const server = await createServer({configLoader:'runner',server:{middlewareMode:true},appType:'custom'});
try {
  const {default: Comparison, changeState, contribution} = await server.ssrLoadModule('/src/comparison.jsx');
  const row = {'항목ID':'Q020','확인항목':'반대면 가연물 우려',
    '이전_사용자응답':'있음','이후_사용자응답':'없음',
    '이전_적용상태':'적용','이후_적용상태':'적용',
    '이전_가중점수':3,'이후_가중점수':0,'이전_집계대표여부':true,'이후_집계대표여부':true};
  assert.deepEqual(changeState(row,true),{label:'위험 감소',delta:-3});
  const excluded = {...row,'이후_적용상태':'조건제외'};
  assert.deepEqual(contribution(excluded,'이후'),{label:'평가 제외',value:null});
  assert.deepEqual(changeState(excluded,true),{label:'평가 제외로 변경'});
  assert.deepEqual(changeState({...row,'이전_적용상태':'조건제외'},true),{label:'평가 대상으로 변경'});
  assert.deepEqual(changeState({...row,'이후_가중점수':null},true),{label:'점수 비교 불가'});
  assert.deepEqual(changeState(row,false),{label:'점수 비교 불가'});
  const makeComparison = rows => ({'비교안내':{'점수차이표시가능':true,'위험지수차이(이후-이전)':1.39},
    '평가요약':[{'위험지수':38.89,'기본위험등급(잠정)':'주의'},{'위험지수':40.28,'기본위험등급(잠정)':'주의'}],
    '변경항목':rows,'추가응답변경':[{'추가질문ID':'W003','이전응답':'예','이후응답':'아니오'}]});
  const render = rows => renderToStaticMarkup(React.createElement(Comparison,{comparison:makeComparison(rows)}));
  const markup = render([row]);
  assert.match(markup,/위험 감소/);
  assert.match(markup,/위험기여 -3.0/);
  assert.match(markup,/1개/); // Derived W003 is not a second changed question.
  const excludedMarkup = render([excluded]);
  assert.match(excludedMarkup,/평가 제외로 변경/);
  assert.doesNotMatch(excludedMarkup,/위험 감소|위험기여 -3.0|이후 위험기여 0.0/);
  assert.match(excludedMarkup,/수치로 비교할 수 있는 위험기여 변화가 없습니다/);
  assert.doesNotMatch(excludedMarkup,/NaN|undefined/);
  console.log('PASS: zero vs exclusion, reverse exclusion, missing score, incompatible criteria, largest change and deduplicated counts.');
} finally { await server.close(); }
