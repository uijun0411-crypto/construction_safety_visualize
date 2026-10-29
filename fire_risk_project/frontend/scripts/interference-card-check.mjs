import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true }, appType: 'custom' });
try {
  const { default: InterferenceCard } = await server.ssrLoadModule('/src/interference-card.jsx');
  const a = 'a', b = 'b', c = 'c';
  const pair = (first, second, status, minutes) => ({
    작업구역ID_A: first, 작업구역ID_B: second, 작업구역명_A: `${first.toUpperCase()}구역`, 작업구역명_B: `${second.toUpperCase()}구역`,
    작업종류: [{ 작업구역ID: first, 작업명: '용접작업' }, { 작업구역ID: second, 작업명: '도장작업' }],
    작업시간: { 작업시간중복: minutes > 0, 시간관계: minutes > 0 ? '작업시간 중복' : '작업시간 중복 없음',
      중복시작일시: minutes > 0 ? '2026-10-29T10:00' : null, 중복종료일시: minutes > 0 ? '2026-10-29T12:00' : null,
      중복시간_분: minutes, 구역별: { [first]: { 시작일시: '2026-10-29T09:00', 종료일시: '2026-10-29T12:00' },
        [second]: { 시작일시: '2026-10-29T10:00', 종료일시: '2026-10-29T13:00' } } },
    조감도상영역관계: '분리', 분석상태: status, 확인된위험요인: status === '동시작업 위험요인 발견' ? [{ 위험요인: '불티와 인화성 물질' }] : [],
    추가확인필요사항: status === '추가 확인 필요' ? ['실제 구역 간 인접 여부'] : [],
    필요한예방조치: ['불티 비산방지조치'], 기존DB근거: { 근거: [{ 기준ID: 'R001', 적용조건: '가연물 존재' }] }, 분석기준버전: '1.0',
  });
  const record = { 현장ID: 'site', 현장조감도: { 이미지ID: 'image' }, 동시작업분석: [
    pair(a, c, '작업시간 중복 없음', 0), pair(a, b, '동시작업 위험요인 발견', 120),
    pair(b, c, '추가 확인 필요', 120), pair(b, a, '동시작업 위험요인 발견', 120),
  ] };
  const html = renderToStaticMarkup(React.createElement(InterferenceCard, { record }));
  assert.match(html, /구역 간 동시작업 위험 확인/);
  assert.match(html, /10:00.*12:00 \(2시간\)/);
  assert.match(html, /불티와 인화성 물질/);
  assert.match(html, /실제 구역 간 인접 여부/);
  assert.match(html, /<details/);
  assert.equal((html.match(/class="interference-pair"/g) || []).length, 3);
  assert.ok(html.indexOf('동시작업 위험요인 발견') < html.indexOf('추가 확인 필요'));
  const old = renderToStaticMarkup(React.createElement(InterferenceCard, { record: { 현장조감도: { 이미지ID: 'image' } } }));
  assert.match(old, /저장된 동시작업 분석정보가 없습니다/);
  console.log('PASS: three unique pairs, priority, time, risk, follow-up, details, legacy record.');
} finally {
  await server.close();
}
