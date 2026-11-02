import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true }, appType: 'custom' });
try {
  const { default: Assessment, RepeatMitigationNotice, responseStatus } = await server.ssrLoadModule('/src/assessment-result.jsx');
  const render = record => renderToStaticMarkup(React.createElement(RepeatMitigationNotice, { record }));
  const record = (sparkScore, watcherScore, previous, state) => ({
    '응답상세': [
      { '항목ID': 'Q003', '사용자응답': sparkScore ? '미실시' : '실시', '점수': sparkScore, '가중치': 1, '적용상태': '적용', '집계대표여부': true },
      { '항목ID': 'Q004', '사용자응답': watcherScore ? '미배치' : '배치', '점수': watcherScore, '가중치': 1, '적용상태': '적용', '집계대표여부': true },
    ],
    '반복미조치판정': { '항목': [
      { '항목ID': 'Q003', '직전응답': previous?.[0] ?? null, '현재응답': sparkScore ? '미실시' : '실시', '상태': state?.[0] ?? (sparkScore === 2 ? '반복 미조치' : '최초 미조치'), '적용점수': sparkScore },
      { '항목ID': 'Q004', '직전응답': previous?.[1] ?? null, '현재응답': watcherScore ? '미배치' : '배치', '상태': state?.[1] ?? (watcherScore === 2 ? '반복 미조치' : '최초 미조치'), '적용점수': watcherScore },
    ] },
  });

  const first = record(1, 1);
  assert.equal(render(first), '');
  for (const row of first['응답상세']) assert.equal(responseStatus(row, true), '최초 미조치 · 1점');

  const second = record(2, 2, ['미실시', '미배치']);
  const repeated = render(second);
  assert.equal((repeated.match(/class="action-card"/g) || []).length, 2);
  for (const text of ['불티·화염 통제조치', '화재감시자 배치 확인', '이전 평가의 조치 상태', '현재 평가의 조치 상태', '최초 미조치 점수', '반복 미조치 적용 점수', '반복 미조치 여부', '이전 평가에서 확인된 위험요인이 개선되지 않아 반복 미조치 가중치가 적용되었습니다.']) assert.ok(repeated.includes(text), text);
  assert.match(repeated, /최초 미조치 점수<\/dt><dd>1점/);
  assert.match(repeated, /반복 미조치 적용 점수<\/dt><dd>2점/);
  assert.match(repeated, /반복 미조치 여부<\/dt><dd>예/);
  assert.equal(render(record(2, 2, ['미실시', '미배치'])), repeated); // third and later stay at two points
  assert.equal(render(record(0, 0, ['미실시', '미배치'], ['조치 완료', '조치 완료'])), '');
  assert.equal(render(record(1, 1, ['실시', '배치'])), ''); // recurrence starts at one point
  assert.equal((render(record(2, 1, ['미실시', '배치'])).match(/class="action-card"/g) || []).length, 1);

  const exception = record(2, null, ['미실시', '미배치'], ['반복 미조치', '화재감시자 적용·예외조건 확인 필요']);
  assert.equal((render(exception).match(/class="action-card"/g) || []).length, 1);
  assert.equal(render({ ...first, '반복미조치판정': undefined }), ''); // older records
  assert.equal(render({ ...second, '응답상세': [] }), ''); // never claim a score without saved detail
  const full = row => renderToStaticMarkup(React.createElement(Assessment, { record: {
    ...row, '현장명': '테스트 현장', '평가일시': '2026-11-02T00:00:00Z',
    '요약': { '점수기준버전': '점검상태-0-1-2-v1', '반복미조치기준버전': '구역반복-v1', '위험지수': 50, '최대가중점수': 4 },
  } }));
  assert.equal((full(first).match(/반복 미조치 적용 내역/g) || []).length, 0);
  assert.equal((full(second).match(/반복 미조치 적용 내역/g) || []).length, 2); // heading and aria label
  assert.equal((full(record(0, 0, ['미실시', '미배치'])).match(/반복 미조치 적용 내역/g) || []).length, 0);
  console.log('PASS: repeat notice and first-miss labels, repeat/cap/completion/recurrence, exception, legacy records.');
} finally {
  await server.close();
}
