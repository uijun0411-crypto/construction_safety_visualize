import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';
const date=v=>v?new Date(v).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'자료 없음';
export function WeatherSummary({snapshot,location}) {
 if(!snapshot)return <p className="muted">{location?.name ? `${location.name} · ` : ''}평가 당시 저장된 기상정보가 없습니다.</p>;
 const observed=snapshot.observed,forecast=snapshot.forecast;
 return <div className="weather-summary"><p><b>{snapshot.region.name}</b> · 기상청 초단기실황·초단기예보 (참고자료)</p>
   <h5>관측 실황 · {observed?.kind || '조회 자료 없음'}</h5>
   <dl className="weather-values">{[['기온',observed?.temperature==null?null:`${observed.temperature} ℃`],['상대습도',observed?.humidity==null?null:`${observed.humidity} %`],['강수형태',observed?.precipitation],['1시간 강수량',observed?.rainfall]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value??'미제공'}</dd></div>)}</dl>
   <p className="muted">관측 기준시각: {date(observed?.valid_at)} (한국시간)</p>
   <h5>초단기예보 · {forecast?.kind || '조회 자료 없음'}</h5>
   <dl className="weather-values">{[['예보 강수형태',forecast?.precipitation],['하늘 상태',forecast?.sky],['풍속',forecast?.wind_speed==null?null:`${forecast.wind_speed} m/s`]]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value??'미제공'}</dd></div>)}</dl>
   <p className="muted">예보 발표시각: {date(forecast?.base_at)}<br/>예보 대상시각: {date(forecast?.valid_at)}<br/>조회 시각: {date(snapshot.fetched_at)} (한국시간)</p>
   {snapshot.warnings&&Object.keys(snapshot.warnings).length>0&&<p className="muted">일부 관측·예보 자료를 불러오지 못했습니다.</p>}
   <p className="muted">출처: <a href={snapshot.source_url} target="_blank" rel="noreferrer">{snapshot.source}</a> · 행정구역 대표 격자 기준이며 현장 실측값이 아닙니다.</p>
 </div>;
}
export function WeatherPicker({value,onChange,paused=false}) {
 const [catalogue,setCatalogue]=useState([]),[catalogueError,setCatalogueError]=useState('');
 const [province,setProvince]=useState(''),[retry,setRetry]=useState(0),[catalogueRetry,setCatalogueRetry]=useState(0);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const valueRef=useRef(value);valueRef.current=value;
 useEffect(()=>{
  const controller=new AbortController();setCatalogueError('');
  api('/weather/regions',undefined,controller.signal).then(r=>setCatalogue(r.regions)).catch(e=>{if(e.name!=='AbortError')setCatalogueError(e.message);});
  return ()=>controller.abort();
 },[catalogueRetry]);
 useEffect(()=>{
  if(!value.region_id||paused){setBusy(false);setError('');return;}
  const controller=new AbortController();setBusy(true);setError('');
  api(`/weather?region_id=${encodeURIComponent(value.region_id)}`,undefined,controller.signal).then(result=>onChange({...valueRef.current,region_id:value.region_id,...result})).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return ()=>controller.abort();
 },[value.region_id,retry,paused]);
 return <div className="weather-card"><h4>현장 위치 · 기상정보</h4><div className="questions">
  <label className="field">시·도<select value={province} onChange={e=>{setProvince(e.target.value);onChange({...value,region_id:'',snapshot:null,token:null});}}><option value="">지역 선택 (선택사항)</option>{[...new Set(catalogue.map(r=>r.province))].map(p=><option key={p}>{p}</option>)}</select></label>
  <label className="field">시·군·구<select value={value.region_id} disabled={!province} onChange={e=>onChange({...value,region_id:e.target.value,snapshot:null,token:null})}><option value="">현장 위치 선택</option>{catalogue.filter(r=>r.province===province).map(r=><option key={r.id} value={r.id}>{r.district}</option>)}</select></label>
  <label className="field">작업장 외부 기상 노출<select value={value.exposure||'확인불가'} onChange={e=>onChange({...value,exposure:e.target.value})}><option value="확인불가">확인 필요</option><option value="실외">실외 노출</option><option value="실내">실내 작업</option></select><small>실외 작업은 지역 기상조건 검토에 사용합니다. 지붕·개구부 등으로 외기에 노출된 작업도 실외 노출로 선택하세요.</small></label>
 </div>{catalogueError&&<p className="error" role="alert">지역 목록 조회 실패: {catalogueError} <button type="button" onClick={()=>setCatalogueRetry(n=>n+1)}>다시 불러오기</button></p>}
  <div aria-live="polite">{busy&&<p role="status">기상정보 조회 중…</p>}{error&&<p className="error" role="alert">기상정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.<br/><small>{error}</small></p>}{value.snapshot&&<WeatherSummary snapshot={value.snapshot}/>}</div>
 <button type="button" disabled={!value.region_id||busy} onClick={()=>{onChange({...value,snapshot:null,token:null});setRetry(n=>n+1);}}>기상정보 다시 조회</button>
 <p className="muted">기상청 초단기실황과 초단기예보를 참고자료로 조회합니다. 관측과 예보의 기준시각을 따로 표시하며, 최대 10분간 조회 결과를 재사용합니다. 조회 실패 또는 조회 중에도 평가할 수 있고 완료된 자료만 저장됩니다.</p></div>;
}
