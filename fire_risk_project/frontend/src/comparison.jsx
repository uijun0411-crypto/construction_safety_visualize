import React from 'react';

import { MaterialChange } from './materials';
const number = v => typeof v === 'number' && Number.isFinite(v);
const fmt = v => number(v) ? v.toFixed(1) : '미산정';
const signed = v => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
export function contribution(row, prefix) {
  const state = row[prefix + '_적용상태'];
  if (['조건제외', '시점제외'].includes(state)) return { label: '평가 제외', value: null };
  if (state !== '적용') return { label: state === '선행응답필요' ? '선행 응답 필요' : '자료 없음', value: null };
  const value = row[prefix + '_가중점수'];
  if (!number(value)) return { label: '미산정', value: null };
  if (row[prefix + '_집계대표여부'] === false) return { label: '중복 집계 제외', value: null };
  return { label: fmt(value), value };
}
export function changeState(row, comparable) {
  const before = contribution(row, '이전'), after = contribution(row, '이후');
  if (before.label === '평가 제외' && after.label === '평가 제외') return { label: '평가 제외 유지' };
  if (after.label === '평가 제외') return { label: '평가 제외로 변경' };
  if (before.label === '평가 제외') return { label: '평가 대상으로 변경' };
  if (!comparable || before.value == null || after.value == null) return { label: '점수 비교 불가' };
  const delta = after.value - before.value;
  return { label: delta > 0 ? '위험 증가' : delta < 0 ? '위험 감소' : '위험기여 변화 없음', delta };
}
function answer(row, prefix) {
  if (contribution(row, prefix).label === '평가 제외') return '평가 제외';
  const v = row[prefix + '_사용자응답'];
  return v == null || v === '' ? '미입력' : `${v}${row['항목ID'] === 'Q002' && number(v) ? 'm' : ''}`;
}
export default function Comparison({ comparison }) {
  const info = comparison['비교안내'];
  const [before = {}, after = {}] = comparison['평가요약'] || [];
  const rows = comparison['변경항목'] || [];
  const extras = comparison['추가응답변경'] || [];
  // Derived W responses describe the same changed Q; count and show them once.
  const uniqueExtras = extras.filter(r => !rows.some(q => q['항목ID'] === ({W002:'Q019',W003:'Q020'}[r['추가질문ID']])));
  const comparable = info['점수차이표시가능'];
  const changes = rows.map(row => ({ row, ...changeState(row, comparable) }));
  const ranked = changes.filter(c => number(c.delta) && c.delta !== 0).sort((a,b) => Math.abs(b.delta)-Math.abs(a.delta));
  const maximum = Math.max(1, ...rows.flatMap(r => ['이전','이후'].map(p => contribution(r,p).value ?? 0)));
  const index = v => number(v) ? v.toFixed(2) : '미산정';
  const delta = info['위험지수차이(이후-이전)'];
  return <>
    <section className="comparison-summary"><h3>평가 변화</h3><div className="metrics">
      <div className="metric"><span>위험지수</span><strong>{index(before['위험지수'])} → {index(after['위험지수'])}</strong><small>{comparable && number(delta) ? `${delta>0?'+':''}${delta.toFixed(2)}` : '점수 비교 불가'}</small></div>
      <div className="metric"><span>위험등급</span><strong>{before['기본위험등급(잠정)'] || '미산정'} → {after['기본위험등급(잠정)'] || '미산정'}</strong></div>
      <div className="metric"><span>변경된 항목</span><strong>{rows.length + uniqueExtras.length}개</strong></div>
    </div>{!comparable && <p className="notice">{info['비교제한사유']}</p>}</section>
    <section><h3>변경 항목 비교</h3><p className="muted">위험기여는 집계된 가중점수입니다. 평가 제외는 0점과 구분하며 증감 계산에서 제외합니다.</p>
      {changes.map(({row,label,delta}) => <article className="change-card" key={row['항목ID']}><h4>{row['확인항목']}</h4><p>{answer(row,'이전')} → {answer(row,'이후')}</p>
        {['이전','이후'].map(prefix => { const c = contribution(row,prefix); return <div className="contribution-row" key={prefix}><span>{prefix}</span>{c.value == null ? <span className="excluded-contribution">{c.label}</span> : <><div className={'bar-track '+(prefix==='이전'?'before-bar':'')} aria-hidden="true"><div style={{width:`${c.value/maximum*100}%`}} /></div><b aria-label={`${prefix} 위험기여 ${c.label}`}>{c.label}</b></>}</div>; })}
        <span className={'state-badge '+(delta>0?'increase':delta<0?'decrease':'neutral')}>{label}</span>
      </article>)}
      {uniqueExtras.map(r => <article className="change-card" key={r['추가질문ID']}><h4>{{W001:'거리만으로 찾기 어려운 건물 내부·구조물 가연물',W002:'작업점 하부 가연물',W003:'반대면 열전도·복사 착화 우려',W004:'화재감시자 배치 예외 적용'}[r['추가질문ID']] || '추가 조건'}</h4><p>{r['이전응답'] ?? '미입력'} → {r['이후응답'] ?? '미입력'}</p><span className="state-badge neutral">판정조건 변경 · 점수 직접 반영 없음</span></article>)}
      {!rows.length && !uniqueExtras.length && <p className="empty">변경된 항목이 없습니다.</p>}
    </section>
    <section><h3>가장 큰 변화</h3>{ranked.length ? ranked.filter(c=>Math.abs(c.delta)===Math.abs(ranked[0].delta)).map(c=><article className="change-card" key={c.row['항목ID']}><h4>{c.row['확인항목']}</h4><p>{fmt(contribution(c.row,'이전').value)} → {fmt(contribution(c.row,'이후').value)}</p><b>위험기여 {signed(c.delta)}</b></article>) : <p className="muted">수치로 비교할 수 있는 위험기여 변화가 없습니다.</p>}</section>
    <p className="muted">{info['해석']}</p>
    <MaterialChange value={comparison['가연물변화']}/>
  </>;
}
