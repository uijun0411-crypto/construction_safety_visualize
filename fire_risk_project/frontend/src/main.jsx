import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, setAccessKey } from './api';
import './styles.css';
import Assessment, { colors } from './assessment-result';
import { AssessmentQuestionGroups, inputProgress } from './assessment-inputs';
import Comparison from './comparison';
import PreviousComparison from './previous-comparison';
import { emptyMaterials } from './materials';

const text = value => value == null ? '—' : typeof value === 'boolean' ? (value ? '예' : '아니오') : typeof value === 'object' ? JSON.stringify(value) : String(value);
const score = value => value == null ? '미산정' : Number(value).toFixed(2);
const date = value => new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });

function Table({ rows }) {
  if (!rows?.length) return <p className="empty">표시할 기록이 없습니다.</p>;
  const columns = [...new Set(rows.flatMap(Object.keys))].filter(k => !/(?:ID|아이디)$/i.test(k) && k !== '적용상태');
  return <div className="table-wrap" tabIndex="0"><table><thead><tr>{columns.map(k => <th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{columns.map(k => <td key={k}>{text(r[k])}</td>)}</tr>)}</tbody></table></div>;
}

function Metrics({ items }) {
  return <div className="metrics">{items.map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}

function NewEvaluation({ current, setCurrent, onSaved, onCompleted }) {
  const [site, setSite] = useState('');
  const [answers, setAnswers] = useState({});
  const [extras, setExtras] = useState({});
  const [materials, setMaterials] = useState(emptyMaterials);
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [retry, setRetry] = useState(0);
  const [saved, setSaved] = useState(false);
  const requestId = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api('/questions', { answers, watcher_answers: Object.fromEntries(Object.entries(extras).filter(([,value])=>value)) }, controller.signal).then(data => { setSchema(data); setError(''); }).catch(e => {
      if (e.name !== 'AbortError') { setSchema(null); setError(e.message); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [answers, extras, retry]);
  function invalidate() { requestId.current = null; setCurrent(null); setSaved(false); setNotice(''); setError(''); }
  async function evaluate(event) {
    event.preventDefault();
    if ((schema?.watcher_questions || []).filter(q=>q['추가질문ID']!=='W004'||schema?.watcher_context?.exception_required!==false).some(q=>!extras[q['추가질문ID']])) {
      setError('위험 조건을 모두 선택하세요. 판단이 어려우면 확인불가 또는 확인 필요를 선택하세요.');
      return;
    }
    if(answers.Q001==='있음'&&!materials.ids.length&&!materials.custom_names.length&&!materials.unknown){setError('주변 가연물 종류를 선택하거나 직접 입력 또는 가연물 종류 확인 필요를 선택하세요.');return;}
    setBusy(true); setError(''); setNotice('');
    requestId.current ||= crypto.randomUUID();
    const watcherAnswers=Object.fromEntries(Object.entries(extras).filter(([id,value])=>value&&(id!=='W004'||schema?.watcher_context?.exception_required!==false)));
    try { setCurrent(await api('/evaluate', { site_name: site, answers, materials, watcher_answers: watcherAnswers, watcher_ui_version: 'integrated-v1', request_id: requestId.current })); setSaved(true); setNotice('평가 완료 · 자동 저장됨'); onSaved(); onCompleted(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setError('');
    try { const result = await api(`/evaluations/${current['평가ID']}/save`, {}); setSaved(true); setNotice(result['저장상태']); onSaved(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  const progress = inputProgress(schema,answers,extras,materials);
  return <><div className="section-heading"><div><p className="eyebrow">PRE-WORK CHECK</p><h2>작업 시작 전 평가</h2><p className="muted">현장 상태를 확인하고 평가 기록을 남기세요.</p></div><span className="badge">H05 · 용접·용단</span></div>
    <form onSubmit={evaluate}><fieldset disabled={busy}>
    <section className="panel"><div className="step-title"><span>01</span><h3>현장 정보</h3></div><label className="field">현장명<input value={site} maxLength={200} required placeholder="예: 서울 ○○ 신축공사" onChange={e => { invalidate(); setSite(e.target.value); }} /></label></section>
    <section className="panel"><div className="step-title"><span>02</span><h3>위험 조건</h3><small aria-live="polite">{loading ? '질문 확인 중…' : `${progress.answered} / ${progress.total} 응답 (하위 입력 포함) · 미응답 ${progress.missing} · 확인 필요 ${progress.unknown} · 평가 제외 ${progress.excluded}`}</small></div>
    <details className="guide"><summary>거리 입력과 용접방화포 질문 안내</summary><p>현재 거리 점수는 11m 미만/이상으로 구분합니다. 화재감시자의 거리 관련 조건은 정확히 11m를 포함하는 ‘11m 이내’입니다. 거리만으로 배치 의무 전체를 판정하지 않습니다.</p><p>불티 비산방지조치 실시 여부와 용접방화포 사용 시 성능인증 여부를 각각 확인합니다. 다른 방법을 쓴다면 방화포 미사용으로 응답하되 실제 비산방지조치 상태도 확인하세요.</p></details>
    <AssessmentQuestionGroups schema={schema} answers={answers} extras={extras} materials={materials} onMaterialsChange={value=>{invalidate();setMaterials(value);}} onExtraChange={(id,value)=>{invalidate();setExtras(a=>({...a,[id]:value}));}} loading={loading} onChange={(id,value)=>{invalidate();if(id==='Q001'&&value!=='있음')setMaterials(emptyMaterials());setAnswers(a=>({...a,[id]:value}));}} />
    {!schema && !loading && <button type="button" onClick={() => setRetry(n => n + 1)}>질문 다시 불러오기</button>}</section>
    <div className="actions"><p className="muted">선택하지 않은 항목은 미입력으로 남습니다.</p><button className="primary" disabled={loading || !schema || busy}>평가하기 <span>→</span></button></div>
    </fieldset></form>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="success" role="status">{notice}</p>}
    {current && <><Assessment record={current} /><div className="actions"><p className="muted">완료된 평가는 자동 저장됩니다. 결과 대시보드에서 이전 평가와의 변화를 확인하세요.</p><button onClick={save} disabled={busy || saved} className="primary">{saved ? '자동 저장됨' : busy ? '처리 중…' : '이 평가 저장'}</button></div></>}
  </>;
}

function History({ revision, onSelect }) {
  const [keyword, setKeyword] = useState('');
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);
  const [before, setBefore] = useState('');
  const [after, setAfter] = useState('');
  const [comparison, setComparison] = useState(null);
  const [retry, setRetry] = useState(0);
  const selection = useRef(0);
  useEffect(() => {
    const controller = new AbortController(); setBusy(true); setError('');
    api(`/evaluations?site_keyword=${encodeURIComponent(keyword)}`, undefined, controller.signal).then(setRows).catch(e => { if (e.name !== 'AbortError') { setRows([]); setError(e.message); } }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
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
  const label = r => `${date(r['평가일시'])} · ${r['현장명']} · ${r['평가ID'].slice(0, 8)}`;
  return <><div className="section-heading"><div><p className="eyebrow">ASSESSMENT ARCHIVE</p><h2>저장 기록·비교</h2></div><button onClick={() => setRetry(n => n + 1)} disabled={busy}>새로고침</button></div><section className="panel"><label className="field">현장명 검색<input placeholder="현장명으로 검색" value={keyword} onChange={e => setKeyword(e.target.value)} /></label>{busy && <p role="status">불러오는 중…</p>}
    <div className="record-list">{rows.map(r => <button className="record-row" key={r['평가ID']} onClick={() => open(r['평가ID'])}><span><b>{r['현장명']}</b><small>{date(r['평가일시'])}</small></span><span><b>{score(r['위험지수'])}</b><small>{r['기본위험등급(잠정)']} · 잠정</small></span><span aria-hidden="true">↗</span></button>)}</div>{!rows.length && !busy && <p className="empty">검색 조건에 맞는 저장 기록이 없습니다.</p>}</section>
    {error && <p className="error" role="alert">{error}</p>}
    {detail && <><Assessment record={detail} /><details className="panel"><summary>저장된 평가 요약·원래 입력</summary><Table rows={[detail['요약']]} /><Table rows={Object.entries(detail['응답']).map(([k, v]) => ({ 항목ID: k, 입력값: v }))} /></details><button onClick={() => onSelect(detail)}>이 평가를 대시보드에서 보기</button></>}
    <section className="panel"><h3>평가 두 건 비교</h3><p className="muted">같은 현장·작업을 선택하세요. 계산 기준이 다르면 점수 차이를 표시하지 않습니다.</p><div className="questions">{[['이전 평가', before, setBefore], ['이후 평가', after, setAfter]].map(([title, value, setter]) => <label className="field" key={title}>{title}<select value={value} disabled={busy} onChange={e => { setter(e.target.value); setComparison(null); }}><option value="">평가 선택</option>{rows.map(r => <option key={r['평가ID']} value={r['평가ID']}>{label(r)}</option>)}</select></label>)}</div><button className="primary" disabled={busy || !before || !after} onClick={compare}>비교하기</button>
    {comparison && <div className="comparison"><Comparison comparison={comparison} />{['평가요약', '변경항목', '추가응답변경', '화재감시자검토'].map(k => <details key={k}><summary>{k} 상세</summary><Table rows={comparison[k]} /></details>)}</div>}</section></>;
}

function Dashboard({ current, selected, revision }) {
  const [site, setSite] = useState('');
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [group, setGroup] = useState('');
  const [view, setView] = useState('current');
  const [retry, setRetry] = useState(0);
  const [records, setRecords] = useState([]);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState('');
  const [listError, setListError] = useState('');
  useEffect(() => { if (selected) setView(selected['평가ID']); }, [selected]);
  useEffect(() => {
    const controller = new AbortController(); setListError('');
    api('/evaluations', undefined, controller.signal).then(rows => {
      setRecords(rows);
      setView(value => value === 'current' && !current ? (rows[0]?.['평가ID'] || '') : value);
    }).catch(e => { if (e.name !== 'AbortError') setListError(e.message); });
    return () => controller.abort();
  }, [revision, retry, current]);
  useEffect(() => {
    const controller = new AbortController(); setDetail(null); setDetailError('');
    if (view && view !== 'current') api(`/evaluations/${view}`, undefined, controller.signal).then(setDetail).catch(e => { if (e.name !== 'AbortError') setDetailError(e.message); });
    return () => controller.abort();
  }, [view, retry]);
  useEffect(() => {
    const controller = new AbortController(); setStats(null); setError('');
    api(`/dashboard?site=${encodeURIComponent(site)}`, undefined, controller.signal).then(setStats).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [site, revision, retry]);
  const groups = [...new Set((stats?.trends || []).filter(t => t.group[0] && t.group[1]).map(t => JSON.stringify(t.group)))];
  const activeGroup = groups.includes(group) ? group : groups[0];
  const trend = (stats?.trends || []).filter(t => JSON.stringify(t.group) === activeGroup).sort((a, b) => new Date(a.date) - new Date(b.date) || a.id.localeCompare(b.id));
  return <><div className="section-heading"><div><p className="eyebrow">RISK OVERVIEW</p><h2>결과 대시보드</h2></div><button onClick={() => setRetry(n => n + 1)}>새로고침</button></div>
    <label className="field view-select">상세 결과 기준<select value={view} onChange={e => { setDetail(null); setView(e.target.value); }}>{current && <option value="current">현재 평가</option>}{!current && !records.length && <option value="">저장된 평가 없음</option>}{records.map(r => <option key={r['평가ID']} value={r['평가ID']}>{r['현장명']} / {r['작업명']} / {date(r['평가일시'])}</option>)}</select></label>
    {listError && <p className="error" role="alert">평가 목록 조회 실패: {listError}</p>}
    {detailError ? <p className="error" role="alert">{detailError}</p> : view && view !== 'current' && !detail ? <p role="status">평가 불러오는 중…</p> : <><Assessment record={view === 'current' ? current : detail} /><PreviousComparison key={view === 'current' ? current?.['평가ID'] : view} record={view === 'current' ? current : detail} revision={retry + revision} /></>}
    <section className="panel"><div className="section-heading"><h3>저장된 평가 현황</h3><label className="field">현장 필터<select value={site} onChange={e => { setSite(e.target.value); setGroup(''); }}><option value="">전체 현장</option>{(stats?.sites || (site ? [site] : [])).map(s => <option key={s}>{s}</option>)}</select></label></div>
    {error ? <p className="error" role="alert">{error}</p> : !stats ? <p role="status">불러오는 중…</p> : <><Metrics items={[["저장 평가", stats.count], ['현장', stats.site_count], ['판정 보류', stats.held_count]]} /><p className="muted">같은 현장의 반복 평가도 각각 한 건입니다. 저장 당시의 잠정등급이며 사고 건수나 확률이 아닙니다.</p>
    {Object.entries(stats.grades).map(([grade, count]) => <div className="bar-row" key={grade}><div><span>{grade}</span><b>{count}건</b></div><div className="bar-track teal"><div style={{ width: `${count / Math.max(stats.count, 1) * 100}%`, background: colors[grade] || colors['확인필요'] }} /></div></div>)}{!stats.count && <p className="empty">평가를 저장하면 현황이 표시됩니다.</p>}
    <h3>현장별 점수 기록</h3>{!site ? <p className="muted">한 현장을 선택하면 동일한 계산 기준의 점수 기록을 볼 수 있습니다.</p> : groups.length ? <><label className="field">계산 기준<select value={activeGroup} onChange={e => setGroup(e.target.value)}>{groups.map((g, i) => <option key={g} value={g}>기준 그룹 {i + 1} · 분모 {JSON.parse(g)[2]}</option>)}</select></label><p className="muted">같은 데이터·엔진·분모를 사용한 {trend.length}건입니다. 점수 하락을 안전성 개선으로 단정하지 않습니다.</p><div className="trend" role="img" aria-label="동일 계산 기준 평가의 위험지수 추이"><svg viewBox="0 0 600 180">{[0, 50, 100].map(n => <g key={n}><line x1="35" x2="580" y1={155 - n * 1.3} y2={155 - n * 1.3} stroke="#dbe2e5" /><text x="0" y={160 - n * 1.3}>{n}</text></g>)}<polyline fill="none" stroke="#2b7880" strokeWidth="2" points={trend.map((t, i) => t.score == null ? '' : `${40 + i * 530 / Math.max(trend.length - 1, 1)},${155 - t.score * 1.3}`).join(' ')} />{trend.filter(t => t.score != null).map(t => <circle key={t.id} cx={40 + trend.indexOf(t) * 530 / Math.max(trend.length - 1, 1)} cy={155 - t.score * 1.3} r="4" fill="#2b7880"><title>{date(t.date)} · {score(t.score)}</title></circle>)}</svg></div><Table rows={trend.map(t => ({ 평가일시: date(t.date), 위험지수: t.score, 평가ID: t.id }))} /></> : <p className="empty">계산 기준 정보가 있는 기록이 없습니다.</p>}</>}
    </section></>;
}

function App() {
  const [connected, setConnected] = useState(false);
  const [checking, setChecking] = useState(true);
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [tab, setTab] = useState('new');
  const [current, setCurrent] = useState(null);
  const [selected, setSelected] = useState(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => { let active = true; api('/session').then(() => { if (active) setConnected(true); }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setChecking(false); }); return () => { active = false; }; }, []);
  async function connect(e) {
    e.preventDefault(); setChecking(true); setError(''); setAccessKey(key);
    try { await api('/session'); setConnected(true); setKey(''); }
    catch (e) { setError(e.message); }
    finally { setChecking(false); }
  }
  return <div className="app"><aside className="sidebar"><div className="brand"><span className="brand-icon">F</span><div>FIRE RISK<small>건설현장 화재 위험도</small></div></div><p className="nav-label">WORKSPACE</p><nav aria-label="주 메뉴">{[['new', '01', '새 평가'], ['dashboard', '02', '결과 대시보드'], ['history', '03', '저장 기록·비교']].map(([id, n, title]) => <button key={id} aria-current={tab === id ? 'page' : undefined} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}><span>{n}</span>{title}</button>)}</nav><div className="sidebar-bottom"><span className="status-dot" /> 작업 시작 전 평가<small>H05 · 용접·용단<br />규칙 기반 시험 평가</small></div></aside>
    <div className="workspace"><header><span>현장 안전 관리 <b>/ 화재 위험도 평가</b></span><span className="header-tag">PRE-WORK</span></header><main><div className="notice global-notice"><b>잠정 평가 안내</b><span>법령·잔여 적용조건이 미검증되어 최종판정은 보류됩니다.</span></div>
    {!connected ? <form className="panel login" onSubmit={connect}><p className="eyebrow">WORKSPACE ACCESS</p><h2>{checking ? '연결 확인 중…' : '평가 서비스 접속'}</h2><label className="field">접속 키<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder="관리자에게 받은 접속 키" /></label><p className="muted">접속 키는 이 탭이 열려 있는 동안만 유지됩니다.</p>{error && <p role="alert" className="error">{error}</p>}<button className="primary" disabled={checking}>연결하기</button></form> : <>
      <div hidden={tab !== 'new'}><NewEvaluation current={current} setCurrent={setCurrent} onSaved={() => setRevision(n => n + 1)} onCompleted={() => { setSelected(null); setTab('dashboard'); }} /></div>
      {tab === 'dashboard' && <Dashboard current={current} selected={selected} revision={revision} />}
      {tab === 'history' && <History revision={revision} onSelect={r => { setSelected(r); setTab('dashboard'); }} />}
    </>}
    <footer>화재 위험도 평가 · 작업 시작 전 확인 기록</footer></main></div></div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
