import React, { useEffect, useState } from 'react';
import { api } from './api';

const missing='DB에 정보 없음';
export const emptyMaterials=()=>({ids:[],custom_names:[],unknown:false});
export function MaterialDetails({row}) {
 const flash=row['인화점_원문']||(row['인화점_기준값℃']?`${row['인화점_연산자']||''}${row['인화점_기준값℃']}℃`:missing);
 const fields=[['등록 분류',row['GHS인화성구분']],['인화점',flash],['폭발하한(LEL)',row['LEL%']?`${row['LEL%']}%`:null],['폭발상한(UEL)',row['UEL%']?`${row['UEL%']}%`:null],['자연발화온도',row['자연발화온도℃']?`${row['자연발화온도℃']}℃`:null],['증기압',row['증기압']?`${row['증기압']} ${row['증기압단위']}`:null],['제조사',row['제조사']],['CAS',row.CAS_No],['용도',row['용도']],['주요 위험 특성·참고사항',row['비고']],['취급·저장 및 점화원 주의 (DB 등록)',row['점화원주의']],['추가 예방조치',null],['출처 유형',row['근거유형']],['DB 확인일자',row['확인일자_표시']||row['확인일자']]];
 return <details className="material-details"><summary>{row['제품명']} · 상세정보</summary><dl>{fields.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{value||missing}</dd></React.Fragment>)}</dl>{/^https?:\/\//.test(row['물성근거URL']||'')?<a href={row['물성근거URL']} target="_blank" rel="noreferrer">등록된 출처 확인</a>:<p className="muted">MSDS 출처: DB에 정보 없음</p>}{row['확인필요사유']?.length>0&&<p className="notice">{row['확인필요사유'].join(' · ')}</p>}</details>;
}

export function MaterialPicker({enabled,value,onChange,idPrefix=''}) {
 const [catalogue,setCatalogue]=useState(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [search,setSearch]=useState(''),[custom,setCustom]=useState(''),[inputError,setInputError]=useState('');
 useEffect(()=>{const controller=new AbortController();setError('');setCatalogue(null);api('/materials',undefined,controller.signal).then(setCatalogue).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[retry]);
 useEffect(()=>{if(!enabled){setSearch('');setCustom('');setInputError('');}},[enabled]);
 const rows=catalogue?.rows||[], selected=rows.filter(r=>value.ids.includes(r['물질ID']));
 const filtered=rows.filter(r=>[r['제품명'],r['제조사'],r.CAS_No].some(v=>(v||'').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))&&!value.ids.includes(r['물질ID']));
 function addCustom(){const name=custom.trim().replace(/\s+/g,' ');if(!name){setInputError('물질명을 입력하세요.');return;}if(value.custom_names.includes(name)){setInputError('이미 추가한 물질입니다.');return;}onChange({...value,custom_names:[...value.custom_names,name]});setCustom('');setInputError('');}
 return <div className="material-picker question-card"><h4>주변 가연물 종류</h4><p className="muted">현장에 있는 물질을 선택하세요. 물질별 가중점수는 추가하지 않습니다.</p>
   {!enabled&&<p className="conditional-message">주변 가연물이 ‘있음’일 때 입력할 수 있습니다.</p>}
   {error&&<div className="error" role="alert">MSDS 목록 조회 실패: {error}<p>다시 조회하거나, 정확한 종류를 모르면 확인 필요로 기록하세요. 등록 물질의 정보를 읽지 못한 상태로 저장하지 않습니다.</p><button type="button" onClick={()=>setRetry(n=>n+1)}>MSDS 다시 불러오기</button></div>}
   <fieldset disabled={!enabled}>
     <label className="field">물질명 검색<input id={idPrefix+'material-search'} type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="물질명·제조사·CAS 검색"/></label>
     <label className="field">등록 물질 선택<select id={idPrefix+'material-select'} value="" disabled={!catalogue} onChange={e=>{if(e.target.value)onChange({...value,ids:[...value.ids,e.target.value]});}}><option value="">{!catalogue?(error?'목록 조회 실패':'목록 불러오는 중…'):'물질을 선택하면 추가됩니다'}</option>{['분류 확인','분류 확인 필요','선택 제외'].map(group=><optgroup key={group} label={group}>{filtered.filter(r=>r['선택분류']===group).map(r=><option key={r['물질ID']} value={r['물질ID']} disabled={group==='선택 제외'}>{r['제품명']} · {r['GHS인화성구분']||'분류 정보 없음'}</option>)}</optgroup>)}</select></label>
     {catalogue&&!filtered.length&&<p role="status">검색 결과가 없거나 이미 선택한 물질입니다. 목록에 없으면 직접 입력하세요.</p>}
     <p className="muted">분류 확인 필요 물질은 구분하여 기록합니다. 비인화성으로 등록된 물질은 가연물 선택에서 제외하며, 별도 산화성 위험까지 없다는 뜻은 아닙니다.</p>
     <div className="material-selection">{value.ids.map(id=>{const row=selected.find(r=>r['물질ID']===id);return <article key={id}><div className="material-selected-heading"><b>{row?.['제품명']||id}</b><button type="button" aria-label={`${row?.['제품명']||id} 제거`} onClick={()=>onChange({...value,ids:value.ids.filter(v=>v!==id)})}>제거</button></div>{row?<><p>{row['GHS인화성구분']||missing} · {row['선택분류']}</p><MaterialDetails row={row}/></>:<p className="notice">선택한 물질 정보를 읽지 못했습니다. 다시 조회하거나 선택을 제거하세요.</p>}</article>;})}</div>
     <label className="field">목록에 없는 물질 직접 입력<input id={idPrefix+'material-custom'} value={custom} maxLength={200} onChange={e=>setCustom(e.target.value)} placeholder="현장 물질명" onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();addCustom();}}}/></label><button type="button" onClick={addCustom}>직접 입력 물질 추가</button>
     {inputError&&<p className="error" role="alert">{inputError}</p>}
     {value.custom_names.map(name=><div className="material-selected-heading" key={name}><span>{name} · MSDS 미확인</span><button type="button" aria-label={`${name} 제거`} onClick={()=>onChange({...value,custom_names:value.custom_names.filter(n=>n!==name)})}>제거</button></div>)}
     <label className="material-unknown"><input id={idPrefix+'material-unknown'} type="checkbox" checked={value.unknown} onChange={e=>onChange({...value,unknown:e.target.checked})}/>가연물 종류 확인 필요</label>
     {value.unknown&&<p className="notice">가연물 존재는 ‘있음’으로 유지됩니다. 정확한 종류 및 MSDS 확인이 필요합니다.</p>}
   </fieldset>
 </div>;
}

export function MaterialOverview({record}) {
 const info=record['가연물정보'];
 if(!info)return <div className="material-overview"><h4>현장 가연물 정보</h4><p className="muted">당시 물질 종류 정보 미기록</p></div>;
 return <div className="material-overview"><h4>현장 가연물 정보</h4><p>가연물 존재: {info['존재여부']} · 거리: {info['존재여부']==='있음'?`${info['거리m']}m`:'평가 제외'}</p>
   {info['선택물질'].map(r=><article key={r['물질ID']}><b>{r['제품명']}</b><p>{r['GHS인화성구분']||missing} · {r['선택분류']}</p><p>{r['비고']||'화재·폭발 위험 특성: DB에 정보 없음'}</p>{r['확인필요사유'].length>0&&<p className="muted">{r['확인필요사유'].join(' · ')}</p>}</article>)}
   {info['직접입력'].map(r=><p key={r['물질명']}>{r['물질명']} · 직접 입력 · MSDS 미확인</p>)}
   {info['종류확인필요']&&<p className="notice">가연물의 정확한 종류 및 MSDS 확인이 필요합니다.</p>}
   {info['DB상태'].includes('실패')&&<p className="error">{info['DB상태']}</p>}
   <p className="muted">물질 정보는 추가 점수로 합산하지 않습니다.</p>
 </div>;
}

export function MaterialActions({record}) {
 const info=record['가연물정보'];
 if(!info||info['존재여부']!=='있음')return null;
 return <div className="material-actions"><h4>가연물별 취급·저장 주의사항</h4>{info['선택물질'].map(r=><article className="action-card" key={r['물질ID']}><b>{r['제품명']}</b><p>{r['점화원주의']||'DB에 등록된 조치 정보 없음'}</p><small>DB 등록 내용 · 출처: {r['근거유형']||'미등록'}</small>{r['확인필요사유'].length>0&&<p>{r['확인필요사유'].join(' · ')}</p>}</article>)}{info['직접입력'].map(r=><p key={r['물질명']}>{r['물질명']}: 공급사 MSDS 확인이 필요합니다. 등록된 물성·조치 정보 없음.</p>)}{info['종류확인필요']&&<p className="notice">가연물의 정확한 종류 및 MSDS 확인이 필요합니다.</p>}</div>;
}

export function MaterialEvidence({record}) {
 const info=record['가연물정보'];
 if(!info)return <p className="muted">당시 물질 종류 정보 미기록</p>;
 return <>{info['선택물질'].map(r=><MaterialDetails key={r['물질ID']} row={r}/>)}{info['직접입력'].map(r=><p key={r['물질명']}>{r['물질명']}: 직접 입력 · MSDS 미확인</p>)}{info['종류확인필요']&&<p>가연물의 정확한 종류 및 MSDS 확인이 필요합니다.</p>}{info['존재여부']==='없음'&&<p>주변 가연물 없음으로 기록되어 물질 선택은 제외되었습니다.</p>}<p className="muted">{info['DB상태']} · {info['DB출처']}</p>{info['DB_SHA256']&&<p className="material-version">저장 당시 DB SHA256: {info['DB_SHA256']}</p>}<p className="muted">저장 당시 등록 자료입니다. 공급사 SDS, 제품자료, 참고자료를 구분하여 확인하세요.</p></>;
}

export function MaterialChange({value}) {
 if(!value)return null;
 return <details className="evidence-group"><summary>가연물 선택·확인 상태 변화</summary>{['이전','현재'].map(label=>{const info=value[label];return <div key={label}><h4>{label}</h4>{info['기록상태']==='기록됨'?<><p>존재: {info['존재여부']} · 거리: {info['거리m']==null?'평가 제외':`${info['거리m']}m`}</p><p>{info['물질명'].join(', ')||'선택된 물질명 없음'}{info['종류확인필요']?' · 종류 확인 필요':''}</p><p>확인 필요: {info['확인필요수']}건</p></>:<p>{info['기록상태']}</p>}</div>;})}{value['확인완료변경']&&<p>이전 확인 필요 상태에서 물질·자료가 확인된 상태로 변경되었습니다.</p>}<p className="muted">{value['안내']}</p></details>;
}
