import React, { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import Assessment, { colors } from './assessment-result';
import { WeatherSummary } from './weather';
import { PreviousResult } from './previous-comparison';

const gradeOrder = ['낮음', '주의', '높음', '매우높음'];
const gradeRank = grade => grade === '평가불가' ? 0 : gradeOrder.indexOf(grade) < 0 ? -1 : gradeOrder.indexOf(grade) + 1;
const scoreText = value => value == null ? '미산정' : Number(value).toFixed(2);

export function ZonePreviousComparison({ evaluationId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setResult(null); setError('');
    api(`/zone-assessments/${encodeURIComponent(evaluationId)}/previous`, undefined, controller.signal)
      .then(setResult).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [evaluationId]);
  if (error) return <p className="error" role="alert">직전 구역 비교 조회 실패: {error}</p>;
  if (!result) return <p role="status">같은 구역의 직전 평가 확인 중…</p>;
  return result.comparison ? <PreviousResult comparison={result.comparison} /> : <p className="empty">이 구역에 더 이른 평가기록이 없습니다.</p>;
}

function statusFor(item) {
  if (!item?.record) return item?.inputState === '작성 중' ? '미평가 · 작성 중' : '미평가';
  return item.inputState === '완료' ? '완료' : '재계산 필요';
}

function improvement(record) {
  if (!record) return '평가 완료 후 표시';
  const rows = (record['응답상세'] || []).filter(row => row['적용상태'] === '적용' &&
    (Number(row['가중점수']) > 0 || row['사용자응답'] == null || ['확인불가', '해당없음'].includes(row['사용자응답'])));
  return rows.length ? rows.slice(0, 2).map(row => row['확인항목']).join(' · ') : '연결된 개선 필요 항목 없음';
}

export default function ZoneDashboard({ record, revision, fallback }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [sort, setSort] = useState('risk');
  const siteId = record?.['현장ID'] || record?.['현장조감도']?.['현장ID'];
  const imageId = record?.['현장조감도']?.['이미지ID'];
  const key = `${siteId || ''}/${imageId || ''}`;

  useEffect(() => {
    if (!siteId || !imageId) { setData({ key, blueprint: null, zones: [] }); return; }
    const controller = new AbortController();
    setLoading(true); setError('');
    Promise.all([
      api(`/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}`, undefined, controller.signal),
      api(`/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}/zones`, undefined, controller.signal),
      api('/zone-tasks', undefined, controller.signal),
    ]).then(async ([imageResponse, zonesResponse, tasksResponse]) => {
      const zones = zonesResponse['작업구역'] || [];
      const assessments = await Promise.all(zones.map(async zone => {
        try {
          const result = await api(`/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}/zones/${encodeURIComponent(zone['작업구역ID'])}/assessment`, undefined, controller.signal);
          return [zone['작업구역ID'], { record: result['최근평가'], inputState: result['입력상태'], draft: result['초안'] }];
        } catch (e) { if (e.name === 'AbortError') throw e; return [zone['작업구역ID'], { error: e.message }]; }
      }));
      if (!controller.signal.aborted) {
        setData({ key, blueprint: imageResponse['조감도'], zones, results: Object.fromEntries(assessments), tasks: tasksResponse.tasks || [] });
        setSelectedId(current => zones.some(zone => zone['작업구역ID'] === current) ? current : zones[0]?.['작업구역ID'] || '');
      }
    }).catch(e => { if (e.name !== 'AbortError') { setError(e.message); setData({ key, blueprint: null, zones: [] }); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [key, revision]);

  const current = data?.key === key ? data : null;
  const rows = useMemo(() => (current?.zones || []).map(zone => {
    const result = current.results?.[zone['작업구역ID']] || {};
    const assessment = result.record;
    const task = current.tasks?.find(item => item.task_id === (assessment?.['작업ID'] || result.draft?.task_id));
    return { zone, ...result, record: assessment, taskName: assessment?.['작업명'] || task?.name || '작업 미지정' };
  }).sort((a, b) => {
    if (sort === 'name') return a.zone['이름'].localeCompare(b.zone['이름'], 'ko');
    if (sort === 'score') return (b.record?.['요약']?.['위험지수'] ?? -1) - (a.record?.['요약']?.['위험지수'] ?? -1);
    return gradeRank(b.record?.['요약']?.['기본위험등급(잠정)']) - gradeRank(a.record?.['요약']?.['기본위험등급(잠정)']) ||
      (b.record?.['요약']?.['위험지수'] ?? -1) - (a.record?.['요약']?.['위험지수'] ?? -1);
  }), [current, sort]);
  const selected = rows.find(item => item.zone['작업구역ID'] === selectedId);
  const highest = rows.reduce((best, item) => gradeRank(item.record?.['요약']?.['기본위험등급(잠정)']) > gradeRank(best) ? item.record['요약']['기본위험등급(잠정)'] : best, '미평가');

  if (!siteId || !imageId || (current && !current.blueprint) || (current && !current.zones.length)) return <>{fallback}</>;
  if (!current || loading) return <section className="panel" aria-live="polite"><p role="status">조감도와 구역별 평가결과를 불러오는 중…</p></section>;
  if (!current.blueprint) return <>{fallback}</>;

  const blueprint = current.blueprint;
  const imageSrc = `data:${blueprint['MIME형식']};base64,${blueprint['이미지Base64']}`;
  const maxIndex = rows.reduce((max, item) => Math.max(max, gradeRank(item.record?.['요약']?.['기본위험등급(잠정)'])), -1);
  return <>
    <section className="panel zone-overview">
      <div className="section-heading"><div><h3>현장 조감도 · 구역별 평가</h3><p className="muted">각 구역을 선택하면 해당 구역의 저장된 결과와 근거가 표시됩니다.</p></div></div>
      {error && <p className="error" role="alert">구역 자료를 불러오지 못했습니다: {error}</p>}
      <div className="zone-overview-stage">
        <img src={imageSrc} alt={`${blueprint['파일명']} 현장 조감도`} />
        <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="group" aria-label="구역별 위험수준 조감도 표시">
          {rows.map(item => {
            const zone = item.zone, rect = zone['좌표'] || {};
            const grade = item.record?.['요약']?.['기본위험등급(잠정)'];
            const color = colors[grade] || colors['확인필요'];
            const selectedZone = zone['작업구역ID'] === selectedId;
            return <g key={zone['작업구역ID']} role="button" tabIndex="0" aria-label={`${zone['이름']}, ${grade || '미평가'}, ${statusFor(item)}`} aria-pressed={selectedZone}
              className={`dashboard-zone${selectedZone ? ' selected' : ''}${grade === '매우높음' || grade === '높음' ? ' high-risk' : ''}`}
              onClick={() => setSelectedId(zone['작업구역ID'])} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedId(zone['작업구역ID']); } }}>
              <rect x={(rect.x || 0) * 1000} y={(rect.y || 0) * 1000} width={(rect.width || 0) * 1000} height={(rect.height || 0) * 1000} fill={`${color}55`} stroke={color} />
              <text x={(rect.x || 0) * 1000 + 8} y={Math.min(990, (rect.y || 0) * 1000 + 24)}>{zone['이름']} · {grade || '미평가'}</text>
            </g>;
          })}
        </svg>
      </div>
      <p className="muted zone-weather-note">위험수준은 저장된 평가결과를 표시합니다. 구역별 점수는 합산·평균하지 않습니다. 기상정보는 현장 공통정보이며 구역 점수에 별도로 더하지 않습니다.</p>
      <div className="zone-site-weather"><h4>현장 공통 기상정보</h4><WeatherSummary snapshot={record?.['기상정보']} location={record?.['현장위치']} /><p className="muted">현장 공통 참고정보이며 구역별 위험지수에 별도로 더하지 않습니다.</p></div>
      <div className="zone-highest" style={{ borderLeftColor: colors[highest] || colors['확인필요'] }}><b>현장 구역 요약</b><span>가장 높은 위험수준: <strong>{highest}</strong></span><span>{maxIndex >= 0 ? '구역별 결과는 아래 표에서 확인하세요.' : '완료된 구역 평가가 없습니다.'}</span></div>
      <div className="section-heading zone-summary-heading"><h3>구역별 평가 요약</h3><label className="field">정렬<select value={sort} onChange={event => setSort(event.target.value)}><option value="risk">위험수준 높은 순</option><option value="score">위험지수 높은 순</option><option value="name">구역명순</option></select></label></div>
      <div className="table-wrap" tabIndex="0"><table className="zone-summary-table"><thead><tr><th>구역명</th><th>작업명</th><th>위험지수</th><th>위험수준</th><th>평가 완료 여부</th><th>개선 필요사항</th></tr></thead><tbody>
        {rows.map(item => { const grade = item.record?.['요약']?.['기본위험등급(잠정)']; return <tr key={item.zone['작업구역ID']} className={item.zone['작업구역ID'] === selectedId ? 'active' : ''}>
          <td><button type="button" className="zone-table-select" onClick={() => setSelectedId(item.zone['작업구역ID'])}>{item.zone['이름']}</button></td><td>{item.taskName}</td><td>{scoreText(item.record?.['요약']?.['위험지수'])}</td><td><span className="zone-grade" style={{ color: colors[grade] || colors['확인필요'], borderColor: colors[grade] || colors['확인필요'] }}>{grade || '미평가'}</span></td><td>{statusFor(item)}</td><td>{improvement(item.record)}</td>
        </tr>; })}
      </tbody></table></div>
    </section>
    {selected?.record ? <><div className="zone-detail-heading"><span className="eyebrow">SELECTED WORK ZONE</span><h2>{selected.zone['이름']} · {selected.taskName}</h2><p className="muted">{statusFor(selected)} · 위험수준 {selected.record['요약']?.['기본위험등급(잠정)']} · 위험지수 {scoreText(selected.record['요약']?.['위험지수'])}</p></div><Assessment record={selected.record} /><section className="panel"><h3>같은 구역의 직전 평가</h3><ZonePreviousComparison evaluationId={selected.record['평가ID']} /></section></> : <section className="panel"><h3>{selected?.zone['이름'] || '작업구역'} · 미평가</h3><p>이 구역의 평가결과가 아직 없습니다. 저장된 조감도 좌표와 작업구역은 표시되며, 평가를 완료하면 위험수준과 상세 결과가 연결됩니다.</p>{selected?.draft?.task_id && <p className="muted">작성 중인 작업: {selected.taskName}</p>}</section>}
  </>;
}
