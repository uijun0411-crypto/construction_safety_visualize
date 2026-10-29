import { WeatherPicker } from './weather';
import BlueprintUpload from './blueprint';
import ZoneAssessment from './zone-assessment';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api';
import './styles.css';
import Assessment, { colors } from './assessment-result';
import Comparison from './comparison';
import PreviousComparison from './previous-comparison';
import ZoneDashboard from './zone-dashboard';
import ZoneHistoryDetail from './zone-history';
import InterferenceCard from './interference-card';
import { buildTrendPoints, formatRiskIndex, groupLegacySeries, groupZoneSeries, zoneRecordKey } from './risk-trend-data';

const text = value => value == null ? '—' : typeof value === 'boolean' ? (value ? '예' : '아니오') : typeof value === 'object' ? JSON.stringify(value) : String(value);
const score = value => value == null ? '미산정' : Number(value).toFixed(2);
const date = value => new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });

function Table({ rows }) {
  if (!rows?.length) return <p className="empty">표시할 기록이 없습니다.</p>;
  const columns = [...new Set(rows.flatMap(Object.keys))].filter(k => !/(?:ID|아이디)$/i.test(k) && k !== '적용상태');
  return <div className="table-wrap" tabIndex="0"><table><thead><tr>{columns.map(k => <th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{columns.map(k => <td key={k}>{text(r[k])}</td>)}</tr>)}</tbody></table></div>;
}

function Metrics({ items }) {
  return <div className="metrics">{items.map(([label, value, description]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong>{description && <small>{description}</small>}</div>)}</div>;
}

function RiskTrend({ site, zoneRecords, legacyTrends }) {
  const [zoneKey, setZoneKey] = useState('');
  const [seriesKey, setSeriesKey] = useState('');
  const siteRecords = useMemo(() => zoneRecords.filter(record => record['현장명'] === site), [zoneRecords, site]);
  const zones = useMemo(() => [...new Map(siteRecords.map(record => [zoneRecordKey(record), record])).entries()], [siteRecords]);
  const activeZoneKey = zones.some(([key]) => key === zoneKey) ? zoneKey : zones[0]?.[0] || '';
  const zoneGroups = useMemo(() => {
    return groupZoneSeries(siteRecords, site, activeZoneKey).map(({ key, records }) => ({
      key: `zone:${key}`, records,
      label: `${records[0]['작업명']} · 점수규칙 ${String(records[0]['계산기준']?.[0] || '').slice(0, 8)} · 분모 ${records[0]['계산기준']?.[2] ?? '자료 없음'}`,
      zone: true,
    }));
  }, [siteRecords, site, activeZoneKey]);
  const legacyGroups = useMemo(() => {
    return groupLegacySeries(legacyTrends, site).map(({ key, records }) => ({
      key: `legacy:${key}`, records,
      label: `기존 단일 작업 · 점수규칙 ${String(records[0].group[0] || '').slice(0, 8)} · 분모 ${records[0].group[2] ?? '자료 없음'}`,
      zone: false,
    }));
  }, [legacyTrends, site]);
  const series = zoneGroups.length ? zoneGroups : legacyGroups;
  const activeSeries = series.find(item => item.key === seriesKey) || series[0];
  const points = useMemo(() => {
    return activeSeries ? buildTrendPoints(activeSeries.records, activeSeries.zone) : [];
  }, [activeSeries]);
  const plotted = points.filter(point => point.score != null);
  const start = plotted.length ? new Date(plotted[0].date).getTime() : 0;
  const end = plotted.length ? new Date(plotted[plotted.length - 1].date).getTime() : 0;
  const x = point => plotted.length < 2 || end === start ? 400 : 60 + (new Date(point.date).getTime() - start) / (end - start) * 680;
  const y = point => 220 - point.score * 1.9;
  let path = '';
  let inSegment = false;
  for (const point of points) {
    if (point.score == null) { inSegment = false; continue; }
    path += `${inSegment ? ' L' : 'M'}${x(point).toFixed(1)},${y(point).toFixed(1)}`;
    inSegment = true;
  }
  return <>
    <div className="trend-selectors">
      <label className="field">작업구역<select value={activeZoneKey} onChange={event => { setZoneKey(event.target.value); setSeriesKey(''); }} disabled={!zones.length}>
        {!zones.length && <option value="">선택한 현장에 구역 평가가 없습니다</option>}
        {zones.map(([key, record]) => <option key={key} value={key}>{record['작업구역명']} · {record['작업명']}</option>)}
      </select></label>
      <label className="field">작업·점수규칙<select value={activeSeries?.key || ''} onChange={event => setSeriesKey(event.target.value)} disabled={!series.length}>
        {!series.length && <option value="">표시할 평가기록이 없습니다</option>}
        {series.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
      </select></label>
    </div>
    <p className="muted">위험지수 = 대표 질문의 가중점수 합계 ÷ 최대가중점수 × 100입니다. 표시된 분모는 평가 당시 최대가중점수이며, 점수규칙 데이터나 엔진 버전이 다른 기록은 같은 추이로 연결하지 않습니다.</p>
    {!site ? <p className="empty">현장을 선택하면 해당 현장 또는 작업구역의 기록을 표시합니다.</p> : !points.length ? <p className="empty">선택한 현장에 표시할 위험지수 기록이 없습니다.</p> : <>
      <div className="trend" role="img" aria-label="선택한 현장 또는 작업구역의 평가 시점별 위험지수 변화">
        <svg viewBox="0 0 800 280" preserveAspectRatio="xMidYMid meet">
          {[0, 20, 40, 60, 80, 100].map(value => <g key={value}><line x1="55" x2="760" y1={220 - value * 1.9} y2={220 - value * 1.9} stroke="#dbe2e5" /><text x="8" y={224 - value * 1.9}>{value}</text></g>)}
          <path d={path} fill="none" stroke="#2b7880" strokeWidth="2" />
          {plotted.map(point => <g key={point.id}><circle cx={x(point)} cy={y(point)} r="5" fill={colors[point.grade] || colors['확인필요']}><title>{`${date(point.date)} · ${formatRiskIndex(point.score)} · ${point.grade || '위험수준 자료 없음'} · 이전 대비 ${point.delta == null ? '비교 없음' : `${point.delta > 0 ? '+' : ''}${point.delta.toFixed(2)}점`}`}</title></circle><text x={x(point)} y={y(point) - 11} textAnchor="middle">{Number(point.score).toFixed(2)}</text></g>)}
        </svg>
      </div>
      <div className="trend-legend">{['낮음', '주의', '높음', '매우높음', '확인필요'].map(grade => <span key={grade}><i style={{ background: colors[grade] }} />{grade}</span>)}</div>
      <div className="table-wrap" tabIndex="0"><table><thead><tr><th>평가일시</th><th>위험지수</th><th>위험수준</th><th>이전 평가 대비</th></tr></thead><tbody>
        {points.map(point => <tr key={point.id}><td>{date(point.date)}</td><td>{formatRiskIndex(point.score)}</td><td>{point.grade || '자료 없음'}</td><td>{point.delta == null ? '비교 없음' : `${point.delta > 0 ? '+' : ''}${point.delta.toFixed(2)}점`}</td></tr>)}
      </tbody></table></div>
    </>}
  </>;
}

function NewEvaluation({ onZoneSaved, reassessment }) {
  const siteInfo = (() => { try { return JSON.parse(localStorage.getItem('fire-risk-site-draft')) || {}; } catch { return {}; } })();
  const [site, setSite] = useState(reassessment?.record?.['현장명'] || siteInfo.site_name || '');
  const [siteId] = useState(() => reassessment?.record?.['현장ID'] || (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(siteInfo.site_id || '') ? siteInfo.site_id : crypto.randomUUID()));
  const [weather, setWeather] = useState({region_id:reassessment?.inputs?.weather_region_id || reassessment?.record?.['현장위치']?.id || siteInfo.region_id || '',snapshot:null,token:null,exposure:reassessment?.inputs?.weather_exposure || '확인불가'});
  const [blueprint, setBlueprint] = useState(null);
  const [zoneView, setZoneView] = useState({ zones: [], selected: null });
  useEffect(() => {
    try { localStorage.setItem('fire-risk-site-draft', JSON.stringify({site_id:siteId, site_name:site, region_id:weather.region_id || ''})); } catch { /* Evaluation remains usable when browser storage is unavailable. */ }
  }, [siteId, site, weather.region_id]);
  return <><div className="section-heading"><div><p className="eyebrow">PRE-WORK CHECK</p><h2>작업 시작 전 평가</h2><p className="muted">현장 상태를 확인하고 평가 기록을 남기세요.</p></div><span className="badge">용접·용단</span></div>
    <ol className="evaluation-steps" aria-label="평가 이용 순서">{['현장정보 입력','조감도 등록','작업구역 지정','구역별 위험조건 입력','평가결과 확인'].map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, '0')}</span>{step}</li>)}</ol>
    <section className="panel"><div className="step-title"><span>01</span><h3>현장 기본정보</h3></div><label className="field">현장 이름<input value={site} maxLength={200} required placeholder="예: 서울 ○○ 신축공사" onChange={e => setSite(e.target.value)} /><small className="field-help">화재위험성평가를 진행할 현장의 이름을 입력하세요.</small></label><WeatherPicker value={weather} onChange={setWeather} /></section>
    <BlueprintUpload key={`${siteId}/${reassessment?.record?.['현장조감도']?.['이미지ID'] || ''}`} siteId={siteId}
      initialImageId={reassessment?.record?.['현장조감도']?.['이미지ID'] || ''} initialZoneId={reassessment?.record?.['작업구역ID'] || ''}
      onChange={setBlueprint} onZoneChange={setZoneView} />
    <ZoneAssessment key={`${siteId}/${reassessment?.record?.['작업구역ID'] || ''}`} siteId={siteId} image={blueprint} zones={zoneView.zones} selected={zoneView.selected} siteName={site} weather={weather} reassessment={reassessment} onEvaluated={onZoneSaved} />
  </>;
}

function History({ revision, onSelect, onReassess }) {
  const [keyword, setKeyword] = useState('');
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);
  const [before, setBefore] = useState('');
  const [after, setAfter] = useState('');
  const [comparison, setComparison] = useState(null);
  const [zoneRows, setZoneRows] = useState([]);
  const [zoneSite, setZoneSite] = useState('');
  const [zoneId, setZoneId] = useState('');
  const [zoneDetail, setZoneDetail] = useState(null);
  const [zoneError, setZoneError] = useState('');
  const [retry, setRetry] = useState(0);
  const selection = useRef(0);
  useEffect(() => {
    const controller = new AbortController(); setBusy(true); setError('');
    api(`/evaluations?site_keyword=${encodeURIComponent(keyword)}`, undefined, controller.signal).then(setRows).catch(e => { if (e.name !== 'AbortError') { setRows([]); setError(e.message); } }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [keyword, revision, retry]);
  useEffect(() => {
    const controller = new AbortController(); setZoneError('');
    api(`/zone-assessments?site_keyword=${encodeURIComponent(keyword)}`, undefined, controller.signal)
      .then(result => setZoneRows(result['평가이력'] || []))
      .catch(e => { if (e.name !== 'AbortError') { setZoneRows([]); setZoneError(e.message); } });
    return () => controller.abort();
  }, [keyword, revision, retry]);
  async function open(id) {
    const version = ++selection.current; setError(''); setDetail(null);
    try { const record = await api(`/evaluations/${id}`); if (selection.current === version) setDetail(record); }
    catch (e) { if (selection.current === version) setError(e.message); }
  }
  async function compare() {
    setBusy(true); setError(''); setComparison(null);
    try { setComparison(await api('/compare', { before_id: before, after_id: after })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function openZone(id) {
    setZoneError(''); setZoneDetail(null);
    try { setZoneDetail(await api(`/zone-assessments/${encodeURIComponent(id)}`)); }
    catch (e) { setZoneError(e.message); }
  }
  const zoneSites = [...new Map(zoneRows.map(row => [row['현장ID'], row['현장명']])).entries()];
  const siteZoneRows = zoneRows.filter(row => !zoneSite || row['현장ID'] === zoneSite);
  const zonesForSite = [...new Map(siteZoneRows.map(row => [row['작업구역ID'], row['작업구역명']])).entries()];
  const filteredZoneRows = siteZoneRows.filter(row => !zoneId || row['작업구역ID'] === zoneId);
  const label = r => `${date(r['평가일시'])} · ${r['현장명']}`;
  return <><div className="section-heading"><div><p className="eyebrow">ASSESSMENT ARCHIVE</p><h2>저장 기록·비교</h2></div><button onClick={() => setRetry(n => n + 1)} disabled={busy}>새로고침</button></div><section className="panel"><label className="field">현장명 검색<input placeholder="현장명으로 검색" value={keyword} onChange={e => setKeyword(e.target.value)} /></label>{busy && <p role="status">불러오는 중…</p>}
    <div className="record-list">{rows.map(r => <button className="record-row" key={r['평가ID']} onClick={() => open(r['평가ID'])}><span><b>{r['현장명']}</b><small>{date(r['평가일시'])}</small></span><span><b>{score(r['위험지수'])}</b><small>{r['기본위험등급(잠정)']} · 잠정</small></span><span aria-hidden="true">↗</span></button>)}</div>{!rows.length && !busy && <p className="empty">검색 조건에 맞는 저장 기록이 없습니다.</p>}</section>
    <section className="panel zone-history-list"><h3>구역별 평가이력</h3><p className="muted">현장과 구역을 선택해 평가일시별 이력을 확인하고, 같은 구역의 직전 기록과 비교할 수 있습니다.</p>
      <div className="questions"><label className="field">현장<select value={zoneSite} onChange={event => { setZoneSite(event.target.value); setZoneId(''); setZoneDetail(null); }}><option value="">전체 현장</option>{zoneSites.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label className="field">작업구역<select value={zoneId} onChange={event => { setZoneId(event.target.value); setZoneDetail(null); }}><option value="">전체 구역</option>{zonesForSite.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label></div>
      {zoneError && <p className="error" role="alert">구역 이력 조회 실패: {zoneError}</p>}
      <div className="zone-history-table-wrap"><table className="zone-history-table"><thead><tr><th>현장</th><th>구역</th><th>평가일시</th><th>작업명</th><th>위험지수</th><th>위험수준</th><th>조감도 버전</th><th>기록</th></tr></thead><tbody>
        {filteredZoneRows.map(row => <tr key={row['평가ID']} data-evaluation-id={row['평가ID']}><td>{row['현장명']}</td><td>{row['작업구역명']}</td><td>{date(row['평가일시'])}</td><td>{row['작업명']}</td><td>{score(row['위험지수'])}</td><td>{row['위험수준'] || '미산정'}</td><td>{row['이미지버전'] ?? '자료 없음'}</td><td><button type="button" onClick={() => openZone(row['평가ID'])}>조회·비교</button></td></tr>)}
      </tbody></table></div>{!filteredZoneRows.length && !zoneError && <p className="empty">선택한 조건의 구역 평가이력이 없습니다.</p>}
    </section>
    {zoneDetail?.['평가'] && <ZoneHistoryDetail record={zoneDetail['평가']} onReassess={record => onReassess(record, zoneDetail['재평가입력'])} />}
    {error && <p className="error" role="alert">{error}</p>}
    {detail && <><Assessment record={detail} /><details className="panel"><summary>저장된 평가 요약·원래 입력</summary><Table rows={[detail['요약']]} /><Table rows={Object.entries(detail['응답']).map(([k, v]) => ({ 항목ID: k, 입력값: v }))} /></details><button onClick={() => onSelect(detail)}>이 평가를 대시보드에서 보기</button></>}
    <section className="panel"><h3>평가 두 건 비교</h3><p className="muted">같은 현장·작업을 선택하세요. 계산 기준이 다르면 점수 차이를 표시하지 않습니다.</p><div className="questions">{[['이전 평가', before, setBefore], ['이후 평가', after, setAfter]].map(([title, value, setter]) => <label className="field" key={title}>{title}<select value={value} disabled={busy} onChange={e => { setter(e.target.value); setComparison(null); }}><option value="">평가 선택</option>{rows.map(r => <option key={r['평가ID']} value={r['평가ID']}>{label(r)}</option>)}</select></label>)}</div><button className="primary" disabled={busy || !before || !after} onClick={compare}>비교하기</button>
    {comparison && <div className="comparison"><Comparison comparison={comparison} />{['평가요약', '변경항목', '추가응답변경', '화재감시자검토'].map(k => <details key={k}><summary>{k} 상세</summary><Table rows={comparison[k]} /></details>)}</div>}</section></>;
}

function Dashboard({ current, zoneCurrent, selected, revision }) {
  const [site, setSite] = useState('');
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [view, setView] = useState('current');
  const [retry, setRetry] = useState(0);
  const [records, setRecords] = useState([]);
  const [zoneRecords, setZoneRecords] = useState([]);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState('');
  const [listError, setListError] = useState('');
  const displayRecord = view === 'current' ? (zoneCurrent || current) : detail;
  useEffect(() => { if (zoneCurrent) setView('current'); }, [zoneCurrent]);
  useEffect(() => { if (selected) setView(selected['평가ID']); }, [selected]);
  useEffect(() => {
    const controller = new AbortController(); setListError('');
    Promise.all([
      api('/evaluations', undefined, controller.signal),
      api('/zone-assessments', undefined, controller.signal),
    ]).then(([rows, zoneResult]) => {
      const zones = zoneResult['\uD3C9\uAC00\uC774\uB825'] || [];
      setRecords(rows);
      setZoneRecords(zones);
      setView(value => value === 'current' && !current && !zoneCurrent
        ? (rows[0]?.['\uD3C9\uAC00ID'] || (zones[0]?.['\uD3C9\uAC00ID'] ? `zone:${zones[0]['\uD3C9\uAC00ID']}` : ''))
        : value);
    }).catch(e => { if (e.name !== 'AbortError') setListError(e.message); });
    return () => controller.abort();
  }, [revision, retry, current, zoneCurrent]);
  useEffect(() => {
    const controller = new AbortController(); setDetail(null); setDetailError('');
    if (view?.startsWith('zone:')) api(`/zone-assessments/${encodeURIComponent(view.slice(5))}`, undefined, controller.signal).then(result => setDetail(result['\uD3C9\uAC00'])).catch(e => { if (e.name !== 'AbortError') setDetailError(e.message); });
    else if (view && view !== 'current') api(`/evaluations/${view}`, undefined, controller.signal).then(setDetail).catch(e => { if (e.name !== 'AbortError') setDetailError(e.message); });
    return () => controller.abort();
  }, [view, retry]);
  useEffect(() => {
    const controller = new AbortController(); setStats(null); setError('');
    api(`/dashboard?site=${encodeURIComponent(site)}`, undefined, controller.signal).then(setStats).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [site, revision, retry]);
  const siteChoices = [...new Set([...(stats?.sites || []), ...zoneRecords.map(record => record['현장명']).filter(Boolean)])].sort((a, b) => a.localeCompare(b, 'ko'));
  return <><div className="section-heading"><div><p className="eyebrow">RISK OVERVIEW</p><h2>결과 대시보드</h2></div><button onClick={() => setRetry(n => n + 1)}>새로고침</button></div>
    <label className="field view-select">{ '\uC0C1\uC138 \uACB0\uACFC \uAE30\uC900' }<select value={view} onChange={e => { setDetail(null); setView(e.target.value); }}>{(zoneCurrent || current) && <option value="current">{ '\uD604\uC7AC \uAD6C\uC5ED \uD3C9\uAC00' }</option>}{!zoneCurrent && !current && !records.length && !zoneRecords.length && <option value="">{ '\uC800\uC7A5\uB41C \uD3C9\uAC00 \uC5C6\uC74C' }</option>}{records.map(r => <option key={r['\uD3C9\uAC00ID']} value={r['\uD3C9\uAC00ID']}>{r['\uD604\uC7A5\uBA85']} / {r['\uC791\uC5C5\uBA85']} / {date(r['\uD3C9\uAC00\uC77C\uC2DC'])}</option>)}{zoneRecords.map(r => <option key={`zone:${r['\uD3C9\uAC00ID']}`} value={`zone:${r['\uD3C9\uAC00ID']}`}>{r['\uD604\uC7A5\uBA85']} / {r['\uC791\uC5C5\uAD6C\uC5ED\uBA85']} / {r['\uC791\uC5C5\uBA85']} / {date(r['\uD3C9\uAC00\uC77C\uC2DC'])}</option>)}</select></label>
    {listError && <p className="error" role="alert">평가 목록 조회 실패: {listError}</p>}
    {detailError ? <p className="error" role="alert">{detailError}</p> : view && view !== 'current' && !detail ? <p role="status">평가 불러오는 중…</p> : <ZoneDashboard key={view === 'current' ? current?.['평가ID'] || 'current' : view} record={view === 'current' ? displayRecord : detail} revision={retry + revision} fallback={<><Assessment record={view === 'current' ? displayRecord : detail} /><PreviousComparison key={view === 'current' ? current?.['평가ID'] : view} record={view === 'current' ? displayRecord : detail} revision={retry + revision} /></>} />}
    {!detailError && (view === 'current' || detail) && <InterferenceCard record={displayRecord} live={view === 'current'} revision={retry + revision} />}
    <section className="panel"><div className="section-heading"><div><h3>저장된 평가 현황</h3><p className="muted">이 화면에서는 저장된 평가결과와 위험지수의 변화를 확인할 수 있습니다. 현장과 작업구역을 선택하여 이전 평가와 비교해 보세요.</p></div><label className="field">현장 필터<select value={site} onChange={e => { setSite(e.target.value); }}><option value="">전체 현장</option>{siteChoices.map(s => <option key={s}>{s}</option>)}</select></label></div>
    {error ? <p className="error" role="alert">{error}</p> : !stats ? <p role="status">불러오는 중…</p> : <><Metrics items={[["저장 평가", stats.count, '기존 단일 작업 평가기록 수'], ['현장', stats.site_count, '기존 단일 작업 평가기록이 존재하는 고유 현장 수'], ['판정 보류', stats.held_count, '기존 단일 작업 평가 중 최종판정이 보류로 시작한 기록 수']]} /><p className="muted">같은 현장의 반복 평가도 각각 한 건입니다. 저장 당시의 잠정등급이며 사고 건수나 확률이 아닙니다.</p>
    {Object.entries(stats.grades).map(([grade, count]) => <div className="bar-row" key={grade}><div><span>{grade}</span><b>{count}건</b></div><div className="bar-track teal"><div style={{ width: `${count / Math.max(stats.count, 1) * 100}%`, background: colors[grade] || colors['확인필요'] }} /></div></div>)}{!stats.count && <p className="empty">평가를 저장하면 현황이 표시됩니다.</p>}
    <h3>화재위험지수 변화 추이</h3><p className="muted">선택한 현장 또는 작업구역의 평가 시점별 위험지수 변화를 보여줍니다.</p><RiskTrend site={site} zoneRecords={zoneRecords} legacyTrends={stats?.trends || []} /></>}
    </section></>;
}

function App() {
  const [tab, setTab] = useState('new');
  const [current, setCurrent] = useState(null);
  const [zoneCurrent, setZoneCurrent] = useState(null);
  const [selected, setSelected] = useState(null);
  const [zoneReassessment, setZoneReassessment] = useState(null);
  const [revision, setRevision] = useState(0);
  return <div className="app"><aside className="sidebar"><div className="brand"><span className="brand-icon">F</span><div>FIRE RISK<small>건설현장 화재 위험도</small></div></div><p className="nav-label">WORKSPACE</p><nav aria-label="주 메뉴">{[['new', '01', '새 평가'], ['dashboard', '02', '결과 대시보드'], ['history', '03', '저장 기록·비교']].map(([id, n, title]) => <button key={id} aria-current={tab === id ? 'page' : undefined} className={tab === id ? 'active' : ''} onClick={() => { if (id === 'new') setZoneReassessment(null); setTab(id); }}><span>{n}</span>{title}</button>)}</nav><div className="sidebar-bottom"><span className="status-dot" /> 작업 시작 전 평가<small>용접·용단<br />규칙 기반 시험 평가</small></div></aside>
    <div className="workspace"><header><span>현장 안전 관리 <b>/ 화재 위험도 평가</b></span><span className="header-slogan">작업 전 <strong>화재 위험</strong>, 정해진 <strong>기준</strong>으로 평가하세요</span><span className="header-tag">PRE-WORK</span></header><main>
      <div hidden={tab !== 'new'}><NewEvaluation key={zoneReassessment?.record?.['평가ID'] || 'new-evaluation'} reassessment={zoneReassessment} onZoneSaved={record => { setZoneCurrent(record); setSelected(null); setRevision(n => n + 1); }} /></div>
      {tab === 'dashboard' && <Dashboard current={current} zoneCurrent={zoneCurrent} selected={selected} revision={revision} />}
      {tab === 'history' && <History revision={revision} onSelect={r => { setSelected(r); setTab('dashboard'); }} onReassess={(record, inputs) => { setZoneReassessment({ record, inputs }); setTab('new'); }} />}
    <footer>화재 위험도 평가 · 작업 시작 전 확인 기록</footer></main></div></div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
