// Similarity only: these weights never enter the fire-risk calculation.
export function selectAccidents(record, limit=5) {
 const answers=record['응답'] || {};
 const rows=record['응답상세'] || [];
 const value=id=>rows.find(r=>r['항목ID']===id&&r['적용상태']==='적용')?.['사용자응답'] ?? answers[id];
 const taskName=record['작업명'] || record['요약']?.['작업명'] || '';
 const welding=/용접/.test(taskName)||record['작업ID']==='H05';
 const cutting=/용단|절단/.test(taskName);
 const materialNames=(record['가연물정보']?.['선택물질']||[]).map(m=>Object.values(m).filter(v=>typeof v==='string').join(' ')).join(' ');
 const seen=new Set();
 return (record['근거스냅샷']?.accidents||[]).flatMap(a=>{
   if(a['검수상태']!=='검수완료'||!a['사고ID']||seen.has(a['사고ID']))return [];
   seen.add(a['사고ID']);
   const source=['점화원','가연_인화물','주요위험조건','미흡한안전조치','사고원인_원문'].map(k=>a[k]||'').join(' ');
   let score=0; const reasons=[];
   const add=(points,reason)=>{score+=points;reasons.push(reason);};
   if((a['작업ID']||'').split(';').includes(record['작업ID']))add(4,'같은 세부 작업의 사례');
   const ignition=(welding&&/용접/.test(a['점화원']||''))||(cutting&&/절단|용단/.test(a['점화원']||''));
   if(ignition)add(2,'작업의 점화원 유형이 유사');
   if(value('Q001')==='있음'&&/가연|인화|우레탄|단열|시너/.test(source))add(2,'주변 가연물 존재 응답과 관련');
   if(value('Q019')==='있음'&&/아래|하부|떨어/.test(source+' '+a['사고경위_원문']))add(5,'작업점 아래 가연물 착화 우려와 관련');
   if(value('Q020')==='있음'&&/열전도|복사|반대/.test(source))add(5,'반대편 가연물의 열전도·복사 우려와 관련');
   if(value('Q003')==='미실시'&&/비산방지.*미흡|방화포.*미흡|용접포 미설치/.test(source))add(4,'불티 비산방지조치 미실시 응답과 관련');
   if(value('Q004')==='미배치'&&/감시자 미배치/.test(source))add(5,'화재감시자 미배치 응답과 관련');
   for(const term of ['우레탄','시너','페인트','LPG','보온재','단열재'])if(materialNames.includes(term)&&(a['가연_인화물']||'').includes(term))add(3,`선택 가연물과 ${term} 관련성이 있음`);
   // Cross-task cases require a shared ignition mechanism AND a current hazard.
   if(!reasons.includes('같은 세부 작업의 사례')&&(!ignition||score<=2))return [];
   return score?[{...a, relevance:score, reasons}]:[];
 }).sort((a,b)=>b.relevance-a.relevance||a['사고ID'].localeCompare(b['사고ID'])).slice(0,limit);
}
