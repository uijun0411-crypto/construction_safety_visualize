import React, { useEffect, useState } from 'react';
import { api } from './api';
const date=v=>v?new Date(v).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'자료 없음';
export function WeatherSummary({snapshot,location}) {
 if(!snapshot)return <p className="muted">{location?.name ? `${location.name} · ` : ''}평가 당시 저장된 기상정보가 없습니다.</p>;
 return <div className="weather-summary"><p><b>{snapshot.region.name}</b> · {snapshot.kind} (참고자료)</p>
   <dl className="weather-values">{[['기온',snapshot.temperature==null?null:`${snapshot.temperature} ℃`],['상대습도',snapshot.humidity==null?null:`${snapshot.humidity} %`],['강수형태',snapshot.precipitation],['1시간 강수량',snapshot.rainfall],['하늘 상태',snapshot.sky]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value??'미제공'}</dd></div>)}</dl>
   <p className="muted">예보 발표: {date(snapshot.base_at)}<br/>예보 대상: {date(snapshot.valid_at)}<br/>최근 자료 조회: {date(snapshot.fetched_at)} (한국시간)</p>
   <p className="muted">출처: <a href={snapshot.source_url} target="_blank" rel="noreferrer">{snapshot.source}</a> · 행정구역 대표 격자 기준이며 현장 실측값이 아닙니다. 위험점수에는 반영하지 않습니다.</p>
 </div>;
}
export function WeatherPicker({value,onChange,paused=false}) {
 const [catalogue,setCatalogue]=useState([]),[catalogueError,setCatalogueError]=useState('');
 const [province,setProvince]=useState(''),[retry,setRetry]=useState(0),[catalogueRetry,setCatalogueRetry]=useState(0);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();setCatalogueError('');
  api('/weather/regions',undefined,controller.signal).then(r=>setCatalogue(r.regions)).catch(e=>{if(e.name!=='AbortError')setCatalogueError(e.message);});
  return ()=>controller.abort();
 },[catalogueRetry]);
 useEffect(()=>{
  if(!value.region_id||paused){setBusy(false);setError('');return;}
  const controller=new AbortController();setBusy(true);setError('');
  api(`/weather?region_id=${encodeURIComponent(value.region_id)}`,undefined,controller.signal).then(result=>onChange({region_id:value.region_id,...result})).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return ()=>controller.abort();
 },[value.region_id,retry,paused]);
 return <div className="weather-card"><h4>현장 위치 · 기상정보</h4><div className="questions">
  <label className="field">시·도<select value={province} onChange={e=>{setProvince(e.target.value);onChange({region_id:'',snapshot:null,token:null});}}><option value="">지역 선택 (선택사항)</option>{[...new Set(catalogue.map(r=>r.province))].map(p=><option key={p}>{p}</option>)}</select></label>
  <label className="field">시·군·구<select value={value.region_id} disabled={!province} onChange={e=>onChange({region_id:e.target.value,snapshot:null,token:null})}><option value="">현장 위치 선택</option>{catalogue.filter(r=>r.province===province).map(r=><option key={r.id} value={r.id}>{r.district}</option>)}</select></label>
 </div>{catalogueError&&<p className="error" role="alert">지역 목록 조회 실패: {catalogueError} <button type="button" onClick={()=>setCatalogueRetry(n=>n+1)}>다시 불러오기</button></p>}
 <div aria-live="polite">{busy&&<p role="status">기상정보 조회 중…</p>}{error&&<p className="error" role="alert">{error}</p>}{value.snapshot&&<WeatherSummary snapshot={value.snapshot}/>}</div>
 <button type="button" disabled={!value.region_id||busy} onClick={()=>{onChange({...value,snapshot:null,token:null});setRetry(n=>n+1);}}>기상정보 다시 조회</button>
 <p className="muted">기상청 초단기예보를 참고자료로 조회합니다. 최대 10분간 조회 결과를 재사용합니다. 조회 실패 또는 조회 중에도 평가할 수 있으며, 완료된 조회값만 저장됩니다.</p></div>;
}
