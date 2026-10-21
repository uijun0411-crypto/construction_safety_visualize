import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';
import Assessment from './assessment-result';
import { AssessmentQuestionGroups, inputProgress } from './assessment-inputs';
import { emptyMaterials } from './materials';

const blank = () => ({ task_id: '', answers: {}, watcher_answers: {}, materials: emptyMaterials() });
const names = { '미작성': '미작성', '작성 중': '작성 중', '완료': '완료', '재계산 필요': '재계산 필요' };

export default function ZoneAssessment({ siteId, image, zones, selected, siteName, weather }) {
  const [tasks, setTasks] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [states, setStates] = useState({});
  const [results, setResults] = useState({});
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const draftsRef = useRef({});
  const queues = useRef({});
  const loaded = useRef(new Set());
  const edited = useRef(new Set());
  const imageId = image?.image_id;
  const visibleZones = zones.filter(zone => zone.image_id === imageId);
  const activeZone = selected?.image_id === imageId ? selected : null;
  const zoneId = activeZone?.zone_id;
  const key = imageId && zoneId ? `${imageId}/${zoneId}` : '';
  const draft = drafts[key] || blank();
  const path = key ? `/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}/zones/${encodeURIComponent(zoneId)}` : '';

  useEffect(() => {
    const controller = new AbortController();
    api('/zone-tasks', undefined, controller.signal).then(data => setTasks(data.tasks)).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!imageId) return;
    const controller = new AbortController();
    for (const zone of visibleZones) {
      const zoneKey = `${imageId}/${zone.zone_id}`;
      if (loaded.current.has(zoneKey)) continue;
      loaded.current.add(zoneKey);
      const url = `/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}/zones/${encodeURIComponent(zone.zone_id)}/assessment`;
      api(url, undefined, controller.signal).then(data => {
        if (data['초안'] && !draftsRef.current[zoneKey]) {
          draftsRef.current[zoneKey] = data['초안'];
          setDrafts(current => ({ ...current, [zoneKey]: data['초안'] }));
        }
        if (!edited.current.has(zoneKey)) setStates(current => ({ ...current, [zoneKey]: data['입력상태'] }));
        if (data['최근평가']) setResults(current => ({ ...current, [zoneKey]: data['최근평가'] }));
      }).catch(e => { loaded.current.delete(zoneKey); if (e.name !== 'AbortError') setError(e.message); });
    }
    return () => controller.abort();
  }, [siteId, imageId, zones]);

  useEffect(() => {
    setSchema(null);
    if (!draft.task_id || !key) return;
    const controller = new AbortController();
    setLoading(true);
    api('/zone-questions', { task_id: draft.task_id, answers: draft.answers || {}, watcher_answers: draft.watcher_answers || {} }, controller.signal)
      .then(data => { setSchema(data); setError(''); })
      .catch(e => { if (e.name !== 'AbortError') { setSchema(null); setError(e.message); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [key, draft.task_id, draft.answers, draft.watcher_answers]);

  function bodyFor(value) {
    return { site_name: siteName, task_id: value.task_id, answers: value.answers || {},
      watcher_answers: value.watcher_answers || {}, materials: value.materials || emptyMaterials(),
      weather_region_id: weather.region_id || null, weather_token: weather.token || null,
      weather_exposure: weather.exposure || '확인불가' };
  }

  function change(next) {
    if (!key) return;
    edited.current.add(key);
    draftsRef.current[key] = next;
    setDrafts(current => ({ ...current, [key]: next }));
    setStates(current => ({ ...current, [key]: results[key] ? '재계산 필요' : '작성 중' }));
    setNotice(''); setError('');
    if (!next.task_id || !siteName.trim()) return;
    const savePath = `${path}/assessment`;
    const body = bodyFor(next);
    const pending = (queues.current[key] || Promise.resolve()).catch(() => {}).then(() => api(savePath, body, undefined, 'PUT'));
    queues.current[key] = pending;
    pending.catch(e => setError(`초안 저장 실패: ${e.message}`));
  }

  async function evaluate() {
    if (!siteName.trim()) { setError('현장 이름을 입력하세요.'); return; }
    if (!draft.task_id) { setError('작업 종류를 선택하세요.'); return; }
    const extras = draft.watcher_answers || {};
    if ((schema?.watcher_questions || []).filter(q => q['추가질문ID'] !== 'W004' || schema?.watcher_context?.exception_required !== false).some(q => !extras[q['추가질문ID']])) {
      setError('화재감시자 조건을 모두 선택하세요.'); return;
    }
    const material = draft.materials || emptyMaterials();
    if (draft.answers?.Q001 === '있음' && !material.ids.length && !material.custom_names.length && !material.unknown) {
      setError('주변 가연물 종류를 입력하거나 확인 필요를 선택하세요.'); return;
    }
    setBusy(true); setError(''); setNotice('');
    try {
      if (queues.current[key]) await queues.current[key].catch(() => {});
      const current = draftsRef.current[key] || draft;
      const response = await api(`${path}/evaluate`, bodyFor(current));
      setResults(values => ({ ...values, [key]: response['평가'] }));
      setStates(values => ({ ...values, [key]: '완료' }));
      setNotice('구역 평가가 저장되었습니다.');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  if (!imageId || !visibleZones.length) return null;
  const extras = draft.watcher_answers || {};
  const progress = inputProgress(schema, draft.answers || {}, extras, draft.materials || emptyMaterials());
  return <section className="panel zone-assessment-panel">
    <div className="step-title"><span>03</span><h3>구역별 화재위험성평가</h3></div>
    <div className="zone-assessment-statuses">{visibleZones.map(zone => {
      const zoneKey = `${imageId}/${zone.zone_id}`;
      return <span key={zone.zone_id} className={zone.zone_id === zoneId ? 'selected' : ''}>{zone.name} · {names[states[zoneKey]] || '미작성'}</span>;
    })}</div>
    {!activeZone ? <p className="muted">조감도 또는 구역 목록에서 평가할 작업구역을 선택하세요.</p> : <>
      <h4>{activeZone.name} 위험조건</h4>
      <label className="field">작업 종류
        <select value={draft.task_id || ''} onChange={e => change({ ...blank(), task_id: e.target.value })}>
          <option value="">공정 DB의 작업을 선택하세요</option>
          {tasks.map(task => <option key={task.task_id} value={task.task_id}>{task.process} · {task.subprocess} · {task.name}</option>)}
        </select>
      </label>
      {draft.task_id && <>
        <p className="muted">{loading ? '질문 확인 중…' : `${progress.answered} / ${progress.total} 응답 · 미응답 ${progress.missing} · 확인 필요 ${progress.unknown}`}</p>
        <AssessmentQuestionGroups schema={schema} answers={draft.answers || {}} extras={extras} materials={draft.materials || emptyMaterials()}
          loading={loading} idPrefix="zone-"
          onChange={(id, value) => change({ ...draft, answers: { ...draft.answers, [id]: value },
            materials: id === 'Q001' && value !== '있음' ? emptyMaterials() : draft.materials })}
          onExtraChange={(id, value) => change({ ...draft, watcher_answers: { ...extras, [id]: value } })}
          onMaterialsChange={value => change({ ...draft, materials: value })} />
        <div className="actions"><p className="muted">입력은 구역별 초안으로 자동 저장됩니다. 수정한 결과는 다시 계산해야 합니다.</p>
          <button type="button" className="primary" disabled={loading || !schema || busy} onClick={evaluate}>{busy ? '계산 중…' : results[key] ? '수정 조건으로 재계산' : '이 구역 평가하기'}</button></div>
      </>}
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="success" role="status">{notice}</p>}
      {results[key] && states[key] === '재계산 필요' && <p className="notice">조건이 변경되었습니다. 아래 결과는 이전 평가 시점의 기록입니다. 재계산이 필요합니다.</p>}
      {results[key] && <Assessment record={results[key]} />}
    </>}
  </section>;
}
