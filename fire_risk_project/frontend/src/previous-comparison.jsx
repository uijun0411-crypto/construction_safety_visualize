import React, { useEffect, useState } from 'react';
import { api } from './api';
import { MaterialChange } from './materials';

const number = v => typeof v === 'number' && Number.isFinite(v);
const score = v => number(v) ? v.toFixed(2) : '자료 없음';
const date = v => v ? new Date(v).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '자료 없음';
const answer = (row, prefix) => ['조건제외', '시점제외'].includes(row[prefix + '_적용상태']) ? '평가 제외' : String(row[prefix + '_사용자응답'] ?? '자료 없음');

export function PreviousResult({ comparison }) {
  if (!comparison) return <p className="empty">비교 가능한 이전 평가기록이 없습니다.</p>;
  const [before, after] = comparison['평가요약'];
  const info = comparison['비교안내'], delta = info['위험지수차이(이후-이전)'];
  const rows = comparison['전체항목'] || [];
  const groups = [
    ['개선된 항목', rows.filter(r => r['변화분류'] === '개선')],
    ['악화된 항목', rows.filter(r => r['변화분류'] === '악화')],
    ['변화가 없는 항목', rows.filter(r => ['변화 없음', '평가 제외 유지'].includes(r['변화분류']))],
    ['새롭게 발생하거나 확인이 필요한 항목', rows.filter(r => ['새롭게 발생', '비교 불가·확인 필요'].includes(r['변화분류']))],
    ['추가 개선이 필요한 항목', rows.filter(r => r['추가개선필요'])],
  ];
  return <>
    <div className="table-wrap" tabIndex="0"><table><thead><tr><th>구분</th><th>이전 평가</th><th>현재 평가</th></tr></thead><tbody>
      <tr><th>평가일시</th><td>{date(before['평가일시'])}</td><td>{date(after['평가일시'])}</td></tr>
      <tr><th>화재위험지수</th><td>{score(before['위험지수'])}</td><td>{score(after['위험지수'])}</td></tr>
      <tr><th>위험수준</th><td>{before['기본위험등급(잠정)'] || '자료 없음'}</td><td>{after['기본위험등급(잠정)'] || '자료 없음'}</td></tr>
    </tbody></table></div>
    <p className="comparison-outcome">위험지수 변화: <b>{number(delta) ? `${delta > 0 ? '+' : ''}${score(delta)}점` : '산정 보류'}</b> · 평가결과: <b>{info['변화상태']}</b></p>
    {!info['점수차이표시가능'] && <p className="notice">직접 비교할 수 없습니다: {info['비교제한사유']}</p>}
    {info['점수차이표시가능'] && <div aria-label="이전·현재 위험지수 비교">{[['이전 위험지수', before], ['현재 위험지수', after]].map(([label, r]) => <div className="bar-row" key={label}><div><span>{label}</span><b>{score(r['위험지수'])}점</b></div><div className={'bar-track ' + (r === before ? 'before-bar' : 'teal')} aria-hidden="true"><div style={{ width: `${Math.min(100, Math.max(0, r['위험지수']))}%` }} /></div></div>)}</div>}
    {groups.map(([label, items]) => <details className="evidence-group" key={label} open={label === '개선된 항목' || label === '악화된 항목'}><summary>{label} · {items.length}건</summary>{items.length ? items.map(r => <article className="change-card" key={r['항목ID']}><h4>{r['확인항목']}</h4><p>이전 응답: {answer(r, '이전')} → 현재 응답: {answer(r, '이후')}</p><p>가중점수: {score(r['이전_가중점수'])} → {score(r['이후_가중점수'])}</p><span className="state-badge">{r['변화분류']}</span></article>) : <p className="muted">해당 항목 없음</p>}</details>)}
    <p className="muted">추가 개선 항목은 현재 양수로 집계된 위험요인입니다. 평가 제외·미확인·자료 누락은 0점으로 간주하지 않습니다.</p>
    <p className="muted">{info['해석']}</p>
    <MaterialChange value={comparison['가연물변화']}/>
  </>;
}

export default function PreviousComparison({ record, revision }) {
  const [result, setResult] = useState(null), [error, setError] = useState('');
  const id = record?.['평가ID'];
  useEffect(() => {
    const controller = new AbortController(); setResult(null); setError('');
    if (id) api(`/evaluations/${id}/previous`, undefined, controller.signal).then(setResult).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [id, revision]);
  if (!id) return null;
  return <section className="panel previous-comparison"><h3>이전 평가 대비 변화</h3>{error ? <p className="error" role="alert">비교 조회 실패: {error}</p> : !result ? <p role="status">직전 평가 확인 중…</p> : <PreviousResult comparison={result.comparison} />}</section>;
}
