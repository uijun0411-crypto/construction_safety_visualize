import React, { useEffect, useMemo, useState } from 'react';
import { api } from './api';

const order = { '동시작업 위험요인 발견': 0, '추가 확인 필요': 1, '작업시간 중복 없음': 2, '확인된 간섭 위험요인 없음': 3 };
const timeText = value => value ? value.replace('T', ' ').replace(/-/g, '.') : '미입력';
const minutesText = value => value == null ? '확인 필요' : value === 0 ? '0분' : value % 60 === 0 ? `${value / 60}시간` : `${Math.floor(value / 60)}시간 ${value % 60}분`;

export default function InterferenceCard({ record, live = false, revision = 0 }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const siteId = record?.['현장ID'] || record?.['현장조감도']?.['현장ID'];
  const imageId = record?.['현장조감도']?.['이미지ID'];
  const saved = record?.['동시작업분석'];

  useEffect(() => {
    if (!live || !siteId || !imageId) { setRows(null); setError(''); return; }
    const controller = new AbortController();
    setRows(null); setError('');
    api(`/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}/zone-interference`, undefined, controller.signal)
      .then(result => setRows(result['동시작업분석'] || []))
      .catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [live, siteId, imageId, revision]);

  const entries = useMemo(() => {
    const source = live ? rows : saved;
    const unique = new Map();
    for (const item of Array.isArray(source) ? source : []) {
      const ids = [item['작업구역ID_A'], item['작업구역ID_B']].sort();
      if (ids[0] && ids[1] && ids[0] !== ids[1]) unique.set(ids.join('/'), item);
    }
    return [...unique.values()].sort((a, b) => (order[a['분석상태']] ?? 9) - (order[b['분석상태']] ?? 9));
  }, [live, rows, saved]);

  if (!record || (!imageId && !saved)) return null;
  return <section className="panel interference-panel" aria-label="구역 간 동시작업 위험 확인">
    <div className="section-heading"><div><h3>구역 간 동시작업 위험 확인</h3><p className="muted">구역별 화재위험지수와 별도로 확인하는 작업 간 간섭 검토입니다. 새 위험점수를 산정하지 않습니다.</p></div></div>
    {live && error && <p className="error" role="alert">동시작업 분석을 불러오지 못했습니다: {error}</p>}
    {live && !error && rows === null && <p role="status">구역 간 동시작업 분석을 불러오는 중…</p>}
    {!live && !Array.isArray(saved) && <p className="empty">이 평가기록에는 저장된 동시작업 분석정보가 없습니다.</p>}
    {(live ? rows !== null : Array.isArray(saved)) && !entries.length && <p className="empty">비교할 작업구역 조합이 없습니다. 두 구역 이상 등록하면 분석 결과가 표시됩니다.</p>}
    <div className="interference-list">{entries.map(item => {
      const aId = item['작업구역ID_A'], bId = item['작업구역ID_B'];
      const taskA = (item['작업종류'] || []).find(task => task['작업구역ID'] === aId);
      const taskB = (item['작업종류'] || []).find(task => task['작업구역ID'] === bId);
      const schedule = item['작업시간'] || {};
      const intervals = schedule['구역별'] || {};
      const grade = item['분석상태'] || '추가 확인 필요';
      const reasons = item['확인된위험요인'] || [];
      const checks = item['추가확인필요사항'] || [];
      const actions = item['필요한예방조치'] || [];
      const evidence = item['기존DB근거'] || {};
      return <article key={`${aId}/${bId}`} className="interference-pair">
        <div className="interference-pair-head"><h4>{item['작업구역명_A'] || 'A구역'} ↔ {item['작업구역명_B'] || 'B구역'}</h4><span className={`interference-status status-${order[grade] ?? 'unknown'}`}>{grade}</span></div>
        <div className="interference-grid"><div><b>비교 대상</b><p>{item['작업구역명_A'] || aId}: {taskA?.['작업명'] || '작업 미지정'}</p><p>{item['작업구역명_B'] || bId}: {taskB?.['작업명'] || '작업 미지정'}</p></div>
          <div><b>작업시간</b><p>{item['작업구역명_A'] || 'A구역'}: {timeText(intervals[aId]?.['시작일시'])} ~ {timeText(intervals[aId]?.['종료일시'])}</p><p>{item['작업구역명_B'] || 'B구역'}: {timeText(intervals[bId]?.['시작일시'])} ~ {timeText(intervals[bId]?.['종료일시'])}</p><p>중복: {schedule['작업시간중복'] === null ? '시간정보 확인 필요' : schedule['작업시간중복'] || schedule['시간관계'] === '경계시각 일치' ? `${timeText(schedule['중복시작일시'])} ~ ${timeText(schedule['중복종료일시'])} (${minutesText(schedule['중복시간_분'])})` : '없음'}</p></div></div>
        <p className="interference-location"><b>조감도상 위치관계:</b> {item['조감도상영역관계'] || '확인 필요'} <span>실제 이격거리와 불티·증기 영향범위는 현장에서 확인해야 합니다.</span></p>
        {reasons.length > 0 && <div className="interference-section"><b>주요 위험요인</b><ul>{reasons.map((reason, index) => <li key={index}>{reason['위험요인']}</li>)}</ul></div>}
        {checks.length > 0 && <div className="interference-section"><b>추가 확인 필요 사항</b><ul>{checks.map(check => <li key={check}>{check}</li>)}</ul></div>}
        {(actions.length > 0 || Object.keys(evidence).length > 0) && <details className="interference-details"><summary>예방조치 및 DB 근거 보기</summary>
          {actions.length > 0 && <div className="interference-section"><b>검토할 예방조치</b><ul>{actions.map((action, index) => <li key={index}>{action}</li>)}</ul></div>}
          {(evidence['근거'] || []).map(row => <p key={row['기준ID']}><b>{row['기준ID']}</b> · 적용조건: {row['적용조건']}</p>)}
          {(evidence['MSDS'] || []).map(row => <p key={row['물질ID']}><b>{row['물질ID']}</b> · {row['제품명']} · {row['GHS인화성구분']}</p>)}
          <p className="muted">분석 기준 {item['분석기준버전'] || record?.['동시작업분석기준버전'] || '자료 없음'}</p>
        </details>}
      </article>;
    })}</div>
  </section>;
}
