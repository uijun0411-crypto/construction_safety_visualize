import React from 'react';
const groups = [
 ['기본 위험조건 확인', ['Q001','Q002','Q027','Q040','Q019','Q020']],
 ['불티·화염 통제조치', ['Q003','Q018','Q025']],
 ['화재감시자 배치 확인', ['Q004']],
 ['작업방식별 추가 확인', []],
];
export function AssessmentQuestionGroups({schema,answers,extras={},onExtraChange=()=>{},onChange,loading}) {
 const questions=schema?.questions || [];
 const excluded=questions.filter(q=>q['적용상태']==='시점제외');
 const available=questions.filter(q=>q['적용상태']!=='시점제외');
 const known=new Set(groups.flatMap(g=>g[1]));
 let number=0;
 return <><div aria-busy={loading}>{groups.map(([title,ids],i)=>{
 const rows=i===3 ? available.filter(q=>!known.has(q['항목ID'])) : ids.map(id=>available.find(q=>q['항목ID']===id)).filter(Boolean);
 if(!rows.length)return null;
 const startNumber=number;
 number+=rows.length+(i===0?(schema?.watcher_questions||[]).length:0);
 return <section className="question-group" key={title}><h4>{title}</h4><div className="questions">{rows.map((q,index)=><ConditionalQuestion key={q['항목ID']} q={q} number={startNumber+index+1} value={answers[q['항목ID']]??''} onChange={onChange}/>)}</div>{i===0&&<FireWatchConditions questions={schema?.watcher_questions} extras={extras} onChange={onExtraChange} startNumber={startNumber+rows.length}/>}</section>
 })}</div>{excluded.length>0&&<details className="guide"><summary>평가 제외 · {excluded.length}개 항목</summary>{excluded.map(q=><div key={q['항목ID']}><b>{q['확인항목']}</b><p>{q['제외사유']||q['사전안내']}</p><small>작업 시작 전 점수 계산에서 제외됩니다.</small></div>)}</details>}</>
}
export function ConditionalQuestion({q,number,value,onChange}) {
 const id=q['항목ID'], disabled=q['적용상태']!=='적용';
 return <div className={'question-card'+(disabled?' inactive':'')}><label className="field question" htmlFor={'question-'+id}><span><em>{String(number).padStart(2,'0')}</em>{({'Q002':'주변 가연물까지의 거리','Q019':'작업점 아래쪽 가연물의 불티 착화 우려','Q020':'금속 구조물 반대편 가연물의 열전도·복사 착화 우려'}[id]||q['확인항목'])}</span>
 {q['입력형식']==='선택'?<select id={'question-'+id} disabled={disabled} value={value} onChange={e=>onChange(id,e.target.value)}><option value="">선택하세요</option>{q['선택지·허용값'].split('/').map(v=>v.trim()).map(v=><option key={v}>{v}</option>)}</select>:<input id={'question-'+id} type="number" min="0" step="any" disabled={disabled} value={value} placeholder={q['단위']} onChange={e=>onChange(id,e.target.value===''?'':Number(e.target.value))}/>}
 {disabled?<small className="conditional-message">{q['적용상태']==='선행응답필요'?'주변 가연물 존재 여부에 응답한 뒤 입력할 수 있습니다.':'주변 가연물이 없다는 응답에 따라 거리 질문은 이번 평가에서 제외됩니다.'}</small>:<small>{q['사전안내']}</small>}
 </label></div>
}
const watchLabels={
 W001:['거리 입력만으로 찾기 어려운 건물 내부·구조물의 가연물이 있습니까?','주변 거리 항목에 이미 입력한 가연물은 제외하고, 벽·천장·건물 내부나 개구부 안쪽에 숨겨져 따로 확인해야 하는 가연물만 답하세요.'],
 W002:['작업점 아래쪽 가연물의 불꽃 발화 우려가 있습니까?','아래 판단 기준의 거리·위치 조건을 함께 확인하세요.'],
 W003:['금속 벽 등의 반대편에 열로 발화할 우려가 있습니까?','열전도·열복사와 반대면에 인접한 가연물을 확인하세요.'],
 W004:['화재감시자 배치 예외조건을 적용하는 작업입니까?','예외조건 적용 여부는 관련 법령 및 현장 조건 확인이 필요합니다.'],
};
export function FireWatchConditions({questions=[],extras,onChange,startNumber=0}) {
 return <div className="questions">{questions.map((q,i)=>{
 const id=q['추가질문ID'];const [title,note]=watchLabels[id]||[q['질문'],''];
 const labels=id==='W004'?{'아니오':'적용하지 않음','예':'적용','확인불가':'확인 필요'}:{'예':'예','아니오':'아니오','확인불가':'확인불가'};
 return <div className="question-card" key={id}><label className="field question" htmlFor={'watch-'+id}><span><em>{String(startNumber+i+1).padStart(2,'0')}</em>{title}</span><small>{note}</small><select id={'watch-'+id} required value={extras[id]??''} onChange={e=>onChange(id,e.target.value)}><option value="">선택하세요</option>{Object.entries(labels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select><details className="id-help"><summary>판단 기준</summary><p>{id==='W001'?note:q['질문']}</p></details></label></div>
 })}</div>
}

