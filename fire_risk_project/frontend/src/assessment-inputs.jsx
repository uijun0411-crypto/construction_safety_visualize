import React from 'react';
import { MaterialPicker } from './materials';
const groups = [
 ['기본 위험조건 확인', ['Q001','Q002','Q027','Q040','Q019','Q020']],
 ['불티·화염 통제조치', ['Q003','Q018','Q025']],
 ['화재감시자 배치 확인', ['Q004']],
 ['작업방식별 추가 확인', []],
];
export function AssessmentQuestionGroups({schema,answers,extras={},onExtraChange=()=>{},onChange,loading,materials,onMaterialsChange}) {
 const questions=schema?.questions || [];
 const available=questions.filter(q=>q['적용상태']!=='시점제외');
 const known=new Set(groups.flatMap(g=>g[1]));
 let number=0;
 return <><div aria-busy={loading}>{groups.map(([title,ids],i)=>{
 const rows=i===3 ? available.filter(q=>!known.has(q['항목ID'])) : ids.filter(id=>id!=='Q004').map(id=>available.find(q=>q['항목ID']===id)).filter(Boolean);
 if(!rows.length)return null;
 const startNumber=number;
 number+=rows.length+(i===0?(schema?.watcher_questions||[]).length:0);
 return <section className="question-group" key={title}><h4>{title}</h4><div className="questions">{rows.map((q,index)=><React.Fragment key={q['항목ID']}><ConditionalQuestion q={q} number={startNumber+index+1} value={answers[q['항목ID']]??''} onChange={onChange}/>{q['항목ID']==='Q002'&&materials&&<MaterialPicker enabled={answers.Q001==='있음'} value={materials} onChange={onMaterialsChange}/>}</React.Fragment>)}</div>{i===0&&<FireWatchConditions questions={schema?.watcher_questions} extras={extras} onChange={onExtraChange} startNumber={startNumber+rows.length} deployment={answers.Q004??''} onDeploymentChange={value=>onChange('Q004',value)} context={schema?.watcher_context}/>}</section>
 })}</div></>
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
export function FireWatchConditions({questions=[],extras,onChange,startNumber=0,deployment='',onDeploymentChange=()=>{},context}) {
 return <div className="questions">{questions.map((q,i)=>{
 const id=q['추가질문ID'];const [title,note]=watchLabels[id]||[q['질문'],''];
 if(id==='W004')return <IntegratedFireWatch key={id} number={startNumber+i+1} deployment={deployment} exception={extras.W004??''} onDeploymentChange={onDeploymentChange} onExceptionChange={value=>onChange('W004',value)} context={context} question={q}/>;
 const labels=id==='W004'?{'아니오':'적용하지 않음','예':'적용','확인불가':'확인 필요'}:{'예':'예','아니오':'아니오','확인불가':'확인불가'};
 return <div className="question-card" key={id}><label className="field question" htmlFor={'watch-'+id}><span><em>{String(startNumber+i+1).padStart(2,'0')}</em>{title}</span><small>{note}</small><select id={'watch-'+id} required value={extras[id]??''} onChange={e=>onChange(id,e.target.value)}><option value="">선택하세요</option>{Object.entries(labels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select><details className="id-help"><summary>판단 기준</summary><p>{id==='W001'?note:q['질문']}</p></details></label></div>
 })}</div>
}

export function IntegratedFireWatch({number,deployment,exception,onDeploymentChange,onExceptionChange,context,question}) {
 const showException=context?.exception_required !== false;
 return <div className="question-card integrated-watch" data-question="Q004-W004">
   <h5 className="integrated-watch-title"><em>{String(number).padStart(2,'0')}</em>화재감시자 배치 및 예외조건 확인</h5>
   <label className="field" htmlFor="question-Q004"><span>A. 화재감시자 배치 상태</span><select id="question-Q004" required value={deployment} onChange={e=>onDeploymentChange(e.target.value)}>
     <option value="">선택하세요</option><option value="배치">화재감시자 배치 완료</option><option value="미배치">화재감시자 미배치</option><option value="해당없음">화재감시자 배치 대상 아님</option><option value="확인불가">확인 필요</option>
   </select></label>
   {showException ? <label className="field watch-exception" htmlFor="watch-W004"><span>B. 배치 예외조건 적용 여부</span><small>같은 장소에서 상시·반복하는 용접·용단 및 법령상 설비 구비 등 예외요건을 확인하세요.</small><select id="watch-W004" required value={exception} onChange={e=>onExceptionChange(e.target.value)}>
     <option value="">선택하세요</option><option value="예">예외조건 충족 (근거 확인 필요)</option><option value="아니오">예외조건 미충족</option><option value="확인불가">확인 필요</option>
   </select><small>충족 응답만으로 예외가 승인되거나 미배치 점수가 낮아지지 않습니다.</small></label> : <p className="muted">입력상 장소조건이 모두 비해당이어서 예외조건 추가 질문은 생략합니다. 배치 대상 제외를 확정한 것은 아닙니다.</p>}
   {['해당없음','확인불가'].includes(deployment)&&<p className="notice">배치 대상 여부 또는 실제 배치 상태가 확인되지 않아 결과를 저장하되 위험지수는 미산정으로 표시합니다.</p>}
   <details className="id-help"><summary>판단 기준</summary><p>{question?.['질문']}</p><p>배치 대상 아님과 배치 예외는 별도로 검토합니다. 장소조건과 현장 근거가 확인되지 않으면 최종판정을 보류합니다.</p></details>
 </div>;
}

export function inputProgress(schema,answers,extras,materials) {
 const active=(schema?.questions||[]).filter(q=>q['적용상태']==='적용');
 const conditions=(schema?.watcher_questions||[]).filter(q=>q['추가질문ID']!=='W004'||schema?.watcher_context?.exception_required!==false);
 const values=[...active.map(q=>answers[q['항목ID']]),...conditions.map(q=>extras[q['추가질문ID']])];
 if(materials&&answers.Q001==='있음')values.push(materials.unknown||materials.custom_names.length?'확인불가':materials.ids.length?'선택됨':'');
 const answered=values.filter(v=>v!=null&&v!=='').length;
 return {total:values.length,answered,missing:values.length-answered,unknown:values.filter(v=>['확인불가','해당없음'].includes(v)).length,
   excluded:(schema?.questions||[]).filter(q=>['시점제외','조건제외'].includes(q['적용상태'])).length};
}

