import React, { useEffect, useState } from 'react';
import { api } from './api';
import Assessment, { colors } from './assessment-result';
import { ZonePreviousComparison } from './zone-dashboard';

const score = value => value == null ? '미산정' : Number(value).toFixed(2);

export default function ZoneHistoryDetail({ record, onReassess }) {
  const [blueprint, setBlueprint] = useState(null);
  const [blueprintError, setBlueprintError] = useState('');
  const siteId = record?.['현장ID'];
  const imageId = record?.['현장조감도']?.['이미지ID'];
  const evaluationId = record?.['평가ID'];

  useEffect(() => {
    const controller = new AbortController();
    setBlueprint(null); setBlueprintError('');
    if (siteId && imageId) api(`/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}`, undefined, controller.signal)
      .then(result => setBlueprint(result['조감도']))
      .catch(error => { if (error.name !== 'AbortError') setBlueprintError(error.message); });
    return () => controller.abort();
  }, [siteId, imageId]);

  const coordinates = record?.['작업구역좌표'];
  const grade = record?.['요약']?.['기본위험등급(잠정)'] || '평가불가';
  return <section className="zone-history-detail">
    <div className="section-heading"><div><p className="eyebrow">SAVED WORK ZONE RECORD</p><h2>{record['작업구역명'] || '작업구역'} · {record['작업명'] || '작업명 자료 없음'}</h2>
      <p className="muted">{new Date(record['평가일시']).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} · 이미지 버전 {record['현장조감도']?.['버전'] ?? '자료 없음'} · {grade} · {score(record['요약']?.['위험지수'])}</p></div>
      <button type="button" onClick={() => onReassess(record)}>이 조건으로 재평가 준비</button></div>
    {blueprintError && <p className="notice">평가 당시 조감도를 불러오지 못했습니다: {blueprintError}</p>}
    {blueprint && <div className="zone-history-blueprint">
      <img src={`data:${blueprint['MIME형식']};base64,${blueprint['이미지Base64']}`} alt={`${blueprint['파일명']} 평가 당시 조감도`} />
      {coordinates ? <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label={`${record['작업구역명']} 당시 위치, ${grade}`}>
        <rect x={coordinates.x * 1000} y={coordinates.y * 1000} width={coordinates.width * 1000} height={coordinates.height * 1000}
          fill={`${colors[grade] || colors['확인필요']}55`} stroke={colors[grade] || colors['확인필요']} />
        <text x={coordinates.x * 1000 + 8} y={Math.min(990, coordinates.y * 1000 + 24)}>{record['작업구역명']} · {grade}</text>
      </svg> : <p className="notice">이 평가기록에는 당시 구역 좌표가 저장되어 있지 않습니다. 현재 좌표를 과거 위치로 대신 표시하지 않았습니다.</p>}
      <p className="muted">평가 당시 조감도 버전 {record['현장조감도']?.['버전']} · {blueprint['파일명']}</p>
    </div>}
    <Assessment record={record} />
    <section className="panel previous-comparison"><h3>같은 구역의 직전 평가</h3><ZonePreviousComparison evaluationId={evaluationId} /></section>
  </section>;
}
