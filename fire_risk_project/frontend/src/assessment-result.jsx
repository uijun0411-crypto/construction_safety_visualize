import React from 'react';
import references from './reference-data.json';
export const colors={'낮음':'#23786b','주의':'#a98012','높음':'#c66b24','매우높음':'#bb4545','확인필요':'#7d8993'};
const txt=v=>v==null?'—':typeof v==='object'?JSON.stringify(v):String(v);
const fmt=v=>v==null?'미산정':Number(v).toFixed(2);
const split=v=>(v||'').split(';').filter(Boolean);
export function responseStatus(r){
 if(r['적용상태']!=='적용')return '평가제외';
 if(r['사용자응답']==null||['','확인불가','해당없음'].includes(r['사용자응답']))return '확인필요';
 return Number(r['점수'])>0?'점수 발생':'0점';
}
const statusColors={'0점':'#23786b','점수 발생':'#c66b24','확인필요':'#7d8993','평가제외':'#c8d0d5'};
export function Ring({segments,value,label,sub}) {
 const total=segments.reduce((a,s)=>a+s.value,0);let offset=0;
 return <div className="ring" role="img" aria-label={label+' '+value+' '+sub}><svg viewBox="0 0 180 180"><circle cx="90" cy="90" r="72" fill="none" stroke="#edf1f3" strokeWidth="17"/>{total>0&&segments.map((s,i)=>{const part=s.value/total*100,start=offset;offset+=part;return <circle key={i} cx="90" cy="90" r="72" fill="none" stroke={s.color} strokeWidth="17" pathLength="100" strokeDasharray={part+' '+(100-part)} strokeDashoffset={-start} transform="rotate(-90 90 90)"/>})}</svg><div><strong>{value}</strong><b>{label}</b><small>{sub}</small></div></div>
}
export function RiskGauge({summary}) {
 const v=summary['위험지수'];return <Ring value={fmt(v)} label={summary['기본위험등급(잠정)']} sub="화재위험지수 / 100" segments={v==null?[]:[{value:Math.max(0,Math.min(100,v)),color:colors[summary['기본위험등급(잠정)']]||colors['확인필요']},{value:100-Math.max(0,Math.min(100,v)),color:'#edf1f3'}]}/>
}
function RawTable({rows}){if(!rows?.length)return <p className="muted">자료 없음</p>;const keys=[...new Set(rows.flatMap(Object.keys))].filter(k=>!/(?:ID|아이디)$/i.test(k)&&k!=='적용상태');return <div className="table-wrap" tabIndex="0"><table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{keys.map(k=><td key={k}>{txt(r[k])}</td>)}</tr>)}</tbody></table></div>}
export function ResponseDistributionChart({rows}) {
 const counts=Object.fromEntries(Object.keys(statusColors).map(k=>[k,0]));rows.forEach(r=>counts[responseStatus(r)]++);
 return <div><h4>응답 상태 분포</h4><Ring value={rows.length} label="평가 항목" sub="전체 평가 항목 · 제외 포함" segments={Object.entries(counts).map(([k,v])=>({value:v,color:statusColors[k]}))}/><div className="legend">{Object.entries(counts).map(([k,v])=><span key={k}><i style={{background:statusColors[k]}}/>{k} <b>{v}</b></span>)}</div><p className="muted">0점은 안전 확정이 아닙니다. 개별 응답의 안전·주의·위험 분류 기준은 아직 제공되지 않습니다.</p></div>
}
export function TopRiskFactors({rows,maximum}) {
 const top=rows.filter(r=>r['집계대표여부']&&r['가중점수']>0).sort((a,b)=>b['가중점수']-a['가중점수']).slice(0,5);
 return <div><h4>위험기여도 TOP 5</h4>{top.length?top.map(r=>{const contribution=maximum>0?r['가중점수']/maximum*100:0;return <div className="bar-row" key={r['항목ID']}><span className="state-badge" style={{color:statusColors[responseStatus(r)]}}>{responseStatus(r)}</span><div><span>{r['확인항목']}<small className="answer-note">{txt(r['사용자응답'])}</small></span><b>{fmt(contribution)}</b></div><div className="bar-track"><div style={{width:Math.min(100,contribution)+'%'}}/></div></div>}):<p className="empty">양수로 집계된 위험요인이 없습니다.</p>}<p className="muted">전체 위험지수에 더해진 점수입니다. 상위 5개만 표시하며 중복 집계 항목은 제외합니다.</p></div>
}
function linked(row){return references.standards.filter(s=>split(row['관련기준ID']).includes(s['기준ID']))}
function Source({row}){return <><b>{row['법령_가이드명']}</b><p>{row['조문_문서번호']}</p>{/^https?:\/\//.test(row['출처URL']||'')&&<a href={row['출처URL']} target="_blank" rel="noreferrer">원문 확인</a>}</>}
export function RecommendedActions({record}) {
 const rows=record['응답상세'].filter(r=>r['적용상태']==='적용'&&(r['가중점수']>0||responseStatus(r)==='확인필요'));
 return <section className="panel"><h3>필요한 조치</h3><p className="muted">등록된 조치와 관련 근거입니다. 실제 적용·위반 여부나 조치 우선순위를 자동 확정하지 않습니다.</p><div className="questions">{rows.map(r=><article className="action-card" key={r['항목ID']}><span className="state-badge">{responseStatus(r)==='확인필요'?'확인필요':'조치 검토'}</span><h4>{r['확인항목']}</h4><small>현재 상태</small><p>{txt(r['사용자응답'])}</p>{linked(r).length?linked(r).map(s=><div key={s['기준ID']}><small>관련 조치</small><p>{s['필수조치']||'등록된 조치 내용 없음'}</p><details><summary>적용조건·근거 출처</summary><p>{s['적용조건']}</p><Source row={s}/></details></div>):<p className="muted">연결된 조치 자료가 없습니다.</p>}</article>)}</div>{!rows.length&&<p className="muted">점수 발생·미확인 응답에 연결된 조치가 없습니다. 안전조치 완료를 뜻하지 않습니다.</p>}{record['화재감시자검토']&&<div className="info"><b>화재감시자 조건 확인</b><p>{record['화재감시자검토']['확인메시지']}</p></div>}</section>
}
export function EvidencePanel({record}) {
 const ids=new Set(record['응답상세'].filter(r=>r['적용상태']==='적용').flatMap(r=>split(r['관련기준ID'])));
 const sources=references.standards.filter(r=>ids.has(r['기준ID']));
 const laws=sources.filter(r=>r['구분'].includes('법령')),kosha=sources.filter(r=>r['구분'].includes('KOSHA'));
 const accidents=references.accidents.filter(a=>split(a['작업ID']).includes(record['작업ID'])&&a['검수상태']==='검수완료');
 return <section className="panel"><h3>판단 근거</h3><p className="muted">연결 법령 {laws.length}건 · KOSHA {kosha.length}건 · 사용 MSDS 자료 없음 · 작업ID 연관 사고 {accidents.length}건</p><p className="muted">현재 ?? ??의 참고자료입니다. 저장 당시 적용·위반이 확정된 근거는 아닙니다.</p>{[['법령',laws],['KOSHA GUIDE',kosha],['기타 연결 근거',sources.filter(r=>!laws.includes(r)&&!kosha.includes(r))]].map(([title,items])=><details className="evidence-group" key={title}><summary>{title} · {items.length}건</summary>{items.length?items.map(s=><article key={s['기준ID']}><Source row={s}/><p>연결 질문: {record['응답상세'].filter(r=>split(r['관련기준ID']).includes(s['기준ID'])).map(r=>r['확인항목']).join(', ')}</p><p>{s['적용조건']}</p></article>):<p className="muted">현재 평가에 연결된 자료 없음</p>}</details>)}<details className="evidence-group"><summary>MSDS</summary><p>현재 평가 기록에는 사용물질 및 MSDS 파생값이 포함되어 있지 않습니다.</p></details><details className="evidence-group"><summary>유사 사고사례 · {accidents.length}건</summary>{accidents.map(a=><article key={a['사고ID']}><h4>{a['사고유형']} · {a['지역']}</h4><p>{a['사고경위_원문']}</p><p>{a['사고원인_원문']}</p><p className="muted">관련 이유: 현재 평가와 같은 작업ID로 연결된 사례입니다. 개별 위험요인 일치 여부는 미검증입니다.</p>{/^https?:\/\//.test(a['출처URL']||'')&&<a href={a['출처URL']} target="_blank" rel="noreferrer">사고자료 원문</a>}</article>)}</details></section>
}
export default function Assessment({record}) {
 if(!record)return <div className="empty panel">새 평가를 진행하거나 저장 기록에서 평가를 선택하세요.</div>;
 const summary=record['요약'],rows=record['응답상세'];
 const unknown=rows.filter(r=>responseStatus(r)==='확인필요').length+(record['화재감시자응답']||[]).filter(r=>r['응답']==='확인불가'||r['응답']==null).length;
 return <section className="assessment"><div className="section-heading"><div><p className="eyebrow">ASSESSMENT RESULT</p><h2>{record['현장명']}</h2><p className="muted">{new Date(record['평가일시']).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})} · {record['작업ID']} 용접·용단</p></div><span className="badge">잠정 평가</span></div><div className="panel result-hero"><RiskGauge summary={summary}/><div><h3>작업조건 기반 화재위험지수</h3><p className="muted">화재 발생확률이 아닙니다.</p><div className="metrics">{[['평가항목',summary['적용질문수']],['확인 필요',unknown],['평가 제외',summary['제외질문수']]].map(([label,value])=><div className="metric" key={label}><span>{label}</span><strong>{value}개</strong></div>)}</div><p className="notice"><b>확인 필요</b> · 법령 적용조건과 현장 확인이 남아 있어 최종판정을 보류합니다.</p></div></div><section className="panel"><h3>위험요인 분석</h3><div className="analysis-grid"><ResponseDistributionChart rows={rows}/><TopRiskFactors rows={rows} maximum={summary['최대가중점수']}/></div></section><RecommendedActions record={record}/><EvidencePanel record={record}/></section>
}

