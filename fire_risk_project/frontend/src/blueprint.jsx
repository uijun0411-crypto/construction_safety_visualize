import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';

const MAX_BYTES = 3_000_000;
const TYPES = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };
const metadata = image => image ? ({
  site_id: image['현장ID'], image_id: image['이미지ID'], version: image['버전'],
  filename: image['파일명'], media_type: image['MIME형식'], width: image['원본너비'],
  height: image['원본높이'], byte_size: image['원본크기바이트'], created_at: image['등록시각'],
}) : null;
const zoneRecord = zone => ({
  zone_id: zone['작업구역ID'], image_id: zone['이미지ID'], name: zone['이름'], geometry_type: zone['영역유형'],
  coordinates: zone['좌표'], created_at: zone['생성시각'], updated_at: zone['수정시각'],
});
const clamp = value => Math.max(0, Math.min(1, value));
const rectangleFromPoints = (a, b) => ({
  x: clamp(Math.min(a.x, b.x)), y: clamp(Math.min(a.y, b.y)),
  width: clamp(Math.max(a.x, b.x)) - clamp(Math.min(a.x, b.x)),
  height: clamp(Math.max(a.y, b.y)) - clamp(Math.min(a.y, b.y)),
});
function nextZoneName(zones) {
  const used = new Set(zones.map(zone => zone.name));
  for (let i = 0; i < 26; i++) {
    const name = `${String.fromCharCode(65 + i)}구역`;
    if (!used.has(name)) return name;
  }
  let suffix = zones.length + 1;
  while (used.has(`구역 ${suffix}`)) suffix++;
  return `구역 ${suffix}`;
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('이미지 파일을 읽지 못했습니다.'));
    reader.readAsDataURL(file);
  });
}

export default function BlueprintUpload({ siteId, initialImageId = '', initialZoneId = '', onChange = () => {}, onReady = () => {}, onZoneChange = () => {} }) {
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState('');
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [zoom, setZoom] = useState(1);
  const [zones, setZones] = useState([]);
  const [selectedZoneId, setSelectedZoneId] = useState('');
  const [zoneName, setZoneName] = useState('');
  const [drawMode, setDrawMode] = useState('');
  const [draftRect, setDraftRect] = useState(null);
  const [zoneBusy, setZoneBusy] = useState(false);
  const drawing = useRef(null);
  const input = useRef(null);

  useEffect(() => {
    onZoneChange({ zones: image && !pending ? zones : [], selected: image && !pending ? zones.find(zone => zone.zone_id === selectedZoneId) || null : null });
  }, [image, pending, zones, selectedZoneId]);

  async function fetchZones(imageId, signal) {
    const response = await api(`/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(imageId)}/zones`, undefined, signal);
    const next = response['작업구역'].map(zoneRecord);
    setZones(next);
    setSelectedZoneId(current => next.some(zone => zone.zone_id === current) ? current : next.some(zone => zone.zone_id === initialZoneId) ? initialZoneId : '');
    return next;
  }

  useEffect(() => {
    const controller = new AbortController();
    setImage(null); setPreview(''); setPending(null); setError(''); setZoom(1);
    const imagePath = initialImageId
      ? `/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(initialImageId)}`
      : `/sites/${encodeURIComponent(siteId)}/blueprint`;
    api(imagePath, undefined, controller.signal)
      .then(({ 조감도 }) => {
        const next = 조감도 || null;
        setImage(next);
        setPreview(next ? `data:${next['MIME형식']};base64,${next['이미지Base64']}` : '');
        setZones([]); setSelectedZoneId('');
        onChange(metadata(next));
        return next ? fetchZones(next['이미지ID'], controller.signal) : undefined;
      })
      .catch(e => { if (e.name !== 'AbortError') setError(`조감도 정보를 불러오지 못했습니다. ${e.message}`); })
      .finally(() => onReady());
    return () => controller.abort();
  }, [siteId, initialImageId]);

  async function choose(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setError('');
    const extension = file.name.split('.').pop()?.toLowerCase();
    const type = TYPES[extension];
    if (!type || (file.type && file.type !== type)) {
      setError('JPG, JPEG, PNG, WebP 이미지 파일만 등록할 수 있습니다.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('원본 이미지 크기는 3MB 이하만 등록할 수 있습니다.');
      return;
    }
    if (!file.size) {
      setError('빈 이미지 파일은 등록할 수 없습니다.');
      return;
    }
    try {
      const dataUrl = await readFile(file);
      setDrawMode(''); setDraftRect(null); drawing.current = null;
      setPending({ filename: file.name, media_type: type, data_base64: dataUrl.split(',')[1], dataUrl });
      setPreview(dataUrl); setZoom(1);
    } catch (e) { setError(e.message); }
  }

  async function upload() {
    if (!pending) return;
    setBusy(true); setError('');
    try {
      const response = await api(`/sites/${encodeURIComponent(siteId)}/blueprints`, {
        filename: pending.filename, media_type: pending.media_type, data_base64: pending.data_base64,
      });
      const next = response.조감도;
      setImage(next); setPending(null); setPreview(pending.dataUrl); setZoom(1);
      setZones([]); setSelectedZoneId(''); setDrawMode(''); setDraftRect(null); onChange(metadata(next));
      await fetchZones(next['이미지ID']);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (pending) {
      setPending(null);
      setPreview(image ? `data:${image['MIME형식']};base64,${image['이미지Base64']}` : '');
      setError(''); setZoom(1);
      return;
    }
    if (!image) return;
    setBusy(true); setError('');
    try {
      await api(`/sites/${encodeURIComponent(siteId)}/blueprint`, undefined, undefined, 'DELETE');
      setImage(null); setPreview(''); setZoom(1); setZones([]); setSelectedZoneId('');
      setDrawMode(''); setDraftRect(null); onChange(null);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function pointerPoint(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
  }

  function pointerDown(event) {
    if (!drawMode || pending || !image) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointerPoint(event);
    drawing.current = point;
    setDraftRect({ x: point.x, y: point.y, width: 0, height: 0 });
  }

  function pointerMove(event) {
    if (!drawing.current) return;
    setDraftRect(rectangleFromPoints(drawing.current, pointerPoint(event)));
  }

  function pointerUp(event) {
    if (!drawing.current) return;
    const next = rectangleFromPoints(drawing.current, pointerPoint(event));
    drawing.current = null;
    if (next.width < 0.006 || next.height < 0.006) {
      setDraftRect(null); setError('조감도에서 드래그하여 크기가 있는 사각형을 그려주세요.');
      return;
    }
    setDraftRect(next); setError('');
  }

  function cancelDrawing() {
    drawing.current = null; setDraftRect(null); setDrawMode(''); setError('');
  }

  function startEdit(zone) {
    setSelectedZoneId(zone.zone_id); setZoneName(zone.name); setDraftRect(zone.coordinates); setDrawMode('edit'); setError('');
  }

  async function saveZone() {
    if (!draftRect || !image) return;
    const selected = zones.find(zone => zone.zone_id === selectedZoneId);
    const name = (drawMode === 'edit' ? zoneName : nextZoneName(zones)).trim();
    if (!name) { setError('작업구역 이름을 입력하세요.'); return; }
    setZoneBusy(true); setError('');
    try {
      const path = `/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(image['이미지ID'])}/zones`;
      const payload = { name, coordinates: draftRect };
      const response = drawMode === 'edit' && selected
        ? await api(`${path}/${encodeURIComponent(selected.zone_id)}`, payload, undefined, 'PUT')
        : await api(path, payload);
      const saved = zoneRecord(response['작업구역']);
      setZones(current => drawMode === 'edit'
        ? current.map(zone => zone.zone_id === saved.zone_id ? saved : zone)
        : [...current, saved]);
      setSelectedZoneId(saved.zone_id); setZoneName(saved.name); setDraftRect(null); setDrawMode(''); drawing.current = null;
    } catch (e) { setError(e.message); }
    finally { setZoneBusy(false); }
  }

  async function renameSelected() {
    const selected = zones.find(zone => zone.zone_id === selectedZoneId);
    if (!selected || !image) return;
    const name = zoneName.trim();
    if (!name) { setError('작업구역 이름을 입력하세요.'); return; }
    setZoneBusy(true); setError('');
    try {
      const path = `/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(image['이미지ID'])}/zones/${encodeURIComponent(selected.zone_id)}`;
      const response = await api(path, { name, coordinates: selected.coordinates }, undefined, 'PUT');
      const saved = zoneRecord(response['작업구역']);
      setZones(current => current.map(zone => zone.zone_id === saved.zone_id ? saved : zone));
      setZoneName(saved.name);
    } catch (e) { setError(e.message); }
    finally { setZoneBusy(false); }
  }

  async function removeZone(zoneId) {
    if (!image) return;
    setZoneBusy(true); setError('');
    try {
      const path = `/sites/${encodeURIComponent(siteId)}/blueprints/${encodeURIComponent(image['이미지ID'])}/zones/${encodeURIComponent(zoneId)}`;
      await api(path, undefined, undefined, 'DELETE');
      setZones(current => current.filter(zone => zone.zone_id !== zoneId));
      if (selectedZoneId === zoneId) { setSelectedZoneId(''); setZoneName(''); }
    } catch (e) { setError(e.message); }
    finally { setZoneBusy(false); }
  }

  function selectZone(zone) {
    setSelectedZoneId(zone.zone_id); setZoneName(zone.name); setDrawMode(''); setDraftRect(null); drawing.current = null;
  }

  const shown = pending || image;
  return <section className="panel blueprint-card">
    <div className="step-title"><span>02</span><h3>현장 조감도 등록</h3></div>
    <p className="muted">원본 비율로 미리보기합니다. 등록본을 교체하면 이전 평가에서 사용한 이미지 버전은 보존됩니다.</p>
    {preview ? <div className="blueprint-frame" aria-label="현장 조감도 미리보기">
      <div className="blueprint-stage" style={{ width: `${zoom * 100}%` }} data-original-width={shown?.['원본너비'] || ''} data-original-height={shown?.['원본높이'] || ''}>
        <img src={preview} alt={shown?.filename || shown?.['파일명'] || '현장 조감도 미리보기'} />
        {image && !pending && <svg className={`zone-overlay${drawMode ? ' drawing' : ''}`} viewBox="0 0 1000 1000" preserveAspectRatio="none"
          role="application" aria-label="현장 작업구역 조감도" tabIndex="0"
          onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}
          onPointerCancel={pointerUp} onKeyDown={event=>{if(event.key==='Escape')cancelDrawing();}}>
          {zones.map(zone => {
            const {x,y,width,height}=zone.coordinates;
            return <g key={zone.zone_id} className={selectedZoneId===zone.zone_id?'zone-shape selected':'zone-shape'} onClick={()=>{if(!drawMode)selectZone(zone);}}>
              <rect x={x*1000} y={y*1000} width={width*1000} height={height*1000} />
              <text x={x*1000+8} y={Math.min(990,y*1000+24)}>{zone.name}</text>
            </g>;
          })}
          {draftRect && <rect className="zone-draft" x={draftRect.x*1000} y={draftRect.y*1000} width={draftRect.width*1000} height={draftRect.height*1000} />}
        </svg>}
      </div>
    </div> : <div className="blueprint-empty">조감도를 등록하면 이곳에서 미리 볼 수 있습니다.</div>}
    {shown && <div className="blueprint-meta">
      <span>{shown.filename || shown['파일명']}</span>
      {shown.width && <span>원본 {shown.width} × {shown.height}px</span>}
      {shown['원본너비'] && <span>원본 {shown['원본너비']} × {shown['원본높이']}px</span>}
      {!pending && image && <span>버전 {image['버전']} · {new Date(image['등록시각']).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}</span>}
    </div>}
    <div className="blueprint-controls">
      <div className="blueprint-zoom" aria-label="이미지 확대 축소">
        <button type="button" disabled={!preview || zoom <= 0.5 || busy} onClick={() => setZoom(z => Math.max(0.5, +(z - 0.25).toFixed(2)))}>−</button>
        <span>{Math.round(zoom * 100)}%</span>
        <button type="button" disabled={!preview || zoom >= 3 || busy} onClick={() => setZoom(z => Math.min(3, +(z + 0.25).toFixed(2)))}>+</button>
      </div>
      <div className="blueprint-actions">
        <input ref={input} className="blueprint-file-input" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={choose} />
        <button type="button" disabled={busy} onClick={() => input.current?.click()}>{image ? '이미지 교체' : '이미지 선택'}</button>
        {pending && <button type="button" className="primary" disabled={busy} onClick={upload}>{busy ? '저장 중…' : '업로드 및 저장'}</button>}
        {(pending || image) && <button type="button" disabled={busy} onClick={remove}>{pending ? '선택 취소' : '현재 이미지 삭제'}</button>}
      </div>
    </div>
    {image && !pending && <div className="work-zone-panel">
      <div className="work-zone-heading"><h4>작업구역</h4><span>{zones.length}개 · 이미지 버전 {image['버전']}</span></div>
      <p className="muted">조감도에서 드래그해 사각형을 지정하세요. 좌표는 이미지 기준 0–1로 저장됩니다.</p>
      <div className="work-zone-list" aria-label="작업구역 목록">
        {!zones.length && <p className="empty">등록된 작업구역이 없습니다.</p>}
        {zones.map(zone=><div key={zone.zone_id} className={selectedZoneId===zone.zone_id?'work-zone-row selected':'work-zone-row'}>
          <button type="button" className="work-zone-select" disabled={zoneBusy||!!drawMode} onClick={()=>selectZone(zone)}>{zone.name}</button>
          <button type="button" disabled={zoneBusy||!!drawMode} onClick={()=>startEdit(zone)}>위치·크기 수정</button>
          <button type="button" disabled={zoneBusy||!!drawMode} onClick={()=>removeZone(zone.zone_id)}>삭제</button>
        </div>)}
      </div>
      {selectedZoneId && !drawMode && <div className="work-zone-rename">
        <label className="field">선택한 구역 이름<input value={zoneName} maxLength={80} onChange={event=>setZoneName(event.target.value)} /></label>
        <button type="button" disabled={zoneBusy||!zoneName.trim()} onClick={renameSelected}>이름 변경 저장</button>
      </div>}
      <div className="work-zone-actions">
        {!drawMode && <button type="button" disabled={zoneBusy||!!pending} onClick={()=>{setSelectedZoneId('');setZoneName('');setDraftRect(null);setDrawMode('add');setError('');}}>사각형 구역 추가</button>}
        {drawMode && <><span>{drawMode==='edit'?'새 위치와 크기를 드래그하세요.':'조감도에서 드래그해 구역을 그리세요.'}</span>
          <button type="button" className="primary" disabled={zoneBusy||!draftRect} onClick={saveZone}>{zoneBusy?'저장 중…':drawMode==='edit'?'수정 저장':`${nextZoneName(zones)} 저장`}</button>
          <button type="button" disabled={zoneBusy} onClick={cancelDrawing}>취소/되돌리기</button></>}
      </div>
    </div>}
    {pending && <p className="info">새 이미지 미리보기입니다. 업로드를 마치면 해당 이미지 버전에서 구역을 지정할 수 있습니다.</p>}
    <p className="muted">JPG, JPEG, PNG, WebP · 원본 3MB 이하 · 비공개 평가 저장소</p>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
