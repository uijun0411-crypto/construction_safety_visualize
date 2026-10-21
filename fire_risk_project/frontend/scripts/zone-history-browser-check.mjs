// Isolated API + headless Chrome coverage for immutable work-zone history and reassessment.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createServer } from 'vite';

const root = resolve('../..');
const temporary = await mkdtemp(join(tmpdir(), 'fire-risk-zone-history-'));
const sleep = ms => new Promise(resolveSleep => setTimeout(resolveSleep, ms));
const children = [];
const endpoint = 'http://127.0.0.1:18072';
const web = 'http://127.0.0.1:15174';
let server, socket;
async function until(fn, label) {
  for (let i = 0; i < 150; i++) { try { const value = await fn(); if (value) return value; } catch {} await sleep(100); }
  throw new Error(`Timeout: ${label}`);
}
function launch(command, args, options = {}) {
  const child = spawn(command, args, { cwd: root, windowsHide: true, stdio: 'ignore', ...options });
  children.push(child); return child;
}
async function request(path, body) {
  const response = await fetch(endpoint + '/api' + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  assert.equal(response.status, 200, await response.clone().text());
  return response.json();
}

try {
  launch(join(root, '.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'fire_risk_project.api:app', '--host', '127.0.0.1', '--port', '18072'], {
    stdio: 'inherit',
    env: { ...process.env, DATABASE_URL: '', APP_ACCESS_KEY: '', RENDER: '', FIRE_RISK_STORAGE: join(temporary, 'zone-history.sqlite3') },
  });
  await until(() => fetch(endpoint + '/health').then(response => response.ok), 'API startup');

  const siteId = randomUUID();
  const imageUpload = await request(`/sites/${siteId}/blueprints`, {
    filename: 'site-plan-v1.png', media_type: 'image/png',
    data_base64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/kXcAAAAASUVORK5CYII=',
  });
  const image = imageUpload['조감도'];
  const coordinates = {
    A구역: { x: .05, y: .12, width: .3, height: .4 },
    B구역: { x: .55, y: .12, width: .3, height: .4 },
    C구역: { x: .2, y: .66, width: .6, height: .2 },
  };
  const zones = {};
  for (const [name, rect] of Object.entries(coordinates)) {
    const result = await request(`/sites/${siteId}/blueprints/${image['이미지ID']}/zones`, { name, coordinates: rect });
    zones[name] = result['작업구역'];
  }
  const answers = { Q001: '있음', Q002: 5, Q003: '미실시', Q004: '미배치', Q018: '용접방화포 미사용', Q019: '없음', Q020: '없음', Q025: '적정' };
  const watcher = { W001: '아니오', W004: '아니오' };
  const zoneEval = async (name, values) => (await request(`/sites/${siteId}/blueprints/${image['이미지ID']}/zones/${zones[name]['작업구역ID']}/evaluate`, {
    site_name: '구역 이력 브라우저 검증', task_id: 'H05', answers: values, watcher_answers: watcher,
    materials: { ids: ['M008'], custom_names: [], unknown: false },
  }))['평가'];
  const a1 = await zoneEval('A구역', answers);
  const b1 = await zoneEval('B구역', { ...answers, Q002: 2 });
  const moved = { x: .1, y: .18, width: .35, height: .3 };
  const zoneEdit = await fetch(endpoint + `/api/sites/${siteId}/blueprints/${image['이미지ID']}/zones/${zones.A구역['작업구역ID']}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'A구역 수정명', coordinates: moved }),
  });
  assert.equal(zoneEdit.status, 200, await zoneEdit.text());
  const a2 = await zoneEval('A구역', { ...answers, Q002: 8 });
  const legacy = await request('/evaluate', { site_name: '구역정보 없는 기존 현장', answers, watcher_ui_version: 'integrated-v1', materials: { ids: ['M008'] }, watcher_answers: watcher });
  const linked = await request('/evaluate', { site_id: siteId, blueprint_image_id: image['이미지ID'], site_name: '구역 이력 브라우저 검증', answers, watcher_ui_version: 'integrated-v1', materials: { ids: ['M008'] }, watcher_answers: watcher });

  server = await createServer({ configLoader: 'runner', server: { host: '127.0.0.1', port: 15174, strictPort: true, proxy: { '/api': endpoint } } });
  await server.listen();
  launch(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=19228',
    `--user-data-dir=${join(temporary, 'chrome')}`, 'about:blank',
  ], { stdio: 'ignore' });
  const tabs = await until(() => fetch('http://127.0.0.1:19228/json').then(response => response.json()), 'Chrome startup');
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolveOpen, rejectOpen) => { socket.onopen = resolveOpen; socket.onerror = rejectOpen; });
  let serial = 0;
  const pending = new Map();
  const errors = [];
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
    if (message.id) {
      const task = pending.get(message.id); pending.delete(message.id);
      message.error ? task.reject(message.error) : task.resolve(message.result);
    }
  };
  const send = (method, params = {}) => new Promise((resolveMessage, rejectMessage) => {
    const id = ++serial; pending.set(id, { resolve: resolveMessage, reject: rejectMessage });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const click = label => evaluate(`(()=>{const b=Array.from(document.querySelectorAll('button')).find(x=>x.textContent.trim()===${JSON.stringify(label)});if(!b)throw Error('button missing: '+${JSON.stringify(label)});b.click()})()`);
  const setValue = (selector, value) => evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('control missing: '+${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(String(value))});el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
  const visible = () => evaluate("document.querySelector('main').innerText");
  await send('Runtime.enable'); await send('Page.enable');
  await send('Page.navigate', { url: web });
  await until(() => evaluate("!!document.querySelectorAll('nav button')[1]"), 'application');
  await evaluate("document.querySelectorAll('nav button')[1].click()");
  await until(() => evaluate("document.querySelectorAll('.zone-summary-table tbody tr').length===3"), 'three dashboard zones');
  const rows = await evaluate("Array.from(document.querySelectorAll('.zone-summary-table tbody tr')).map(row=>row.innerText)");
  assert.ok(rows.some(row => row.includes('A구역 수정명')));
  assert.ok(rows.some(row => row.includes('B구역')));
  assert.ok(rows.some(row => row.includes('C구역') && row.includes('미평가')));
  await evaluate("document.querySelector('g.dashboard-zone[aria-label^=\"A구역 수정명\"]').click()");
  await until(() => evaluate("document.querySelector('.zone-detail-heading h2')?.textContent.includes('A구역 수정명')"), 'A selection');
  assert.ok((await visible()).includes(a2['요약']['위험지수'].toFixed(2)));
  assert.ok((await visible()).includes('판단 근거'));
  await evaluate("document.querySelector('g.dashboard-zone[aria-label^=\"B구역\"]').click()");
  await until(() => evaluate("document.querySelector('.zone-detail-heading h2')?.textContent.includes('B구역')"), 'B selection');
  assert.ok((await visible()).includes(b1['요약']['위험지수'].toFixed(2)));
  const gradeColor = { 낮음: '#23786b', 주의: '#a98012', 높음: '#c66b24', 매우높음: '#bb4545', 확인필요: '#7d8993' };
  const bGrade = b1['요약']['기본위험등급(잠정)'];
  assert.equal(await evaluate("document.querySelector('g.dashboard-zone[aria-label^=\"B구역\"] rect').getAttribute('stroke')"), gradeColor[bGrade] || gradeColor.확인필요);
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true);
  await writeFile(join(temporary, 'dashboard-desktop.png'), Buffer.from((await send('Page.captureScreenshot', { captureBeyondViewport: true })).data, 'base64'));
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true);
  await writeFile(join(temporary, 'dashboard-mobile.png'), Buffer.from((await send('Page.captureScreenshot', { captureBeyondViewport: true })).data, 'base64'));
  await send('Emulation.clearDeviceMetricsOverride');

  await evaluate("document.querySelectorAll('nav button')[2].click()");
  await until(() => evaluate("document.querySelectorAll('.zone-history-table tbody tr').length===3"), 'zone history list');
  const zoneHistory = await request(`/zone-assessments?site_id=${siteId}`);
  assert.equal(zoneHistory['평가이력'].length, 3);
  await evaluate(`document.querySelector('[data-evaluation-id="${a1['평가ID']}"] button').click()`);
  await until(() => evaluate("!!document.querySelector('.zone-history-detail .zone-history-blueprint svg rect')"), 'historic blueprint and zone');
  assert.equal(await evaluate("document.querySelector('.zone-history-blueprint svg rect').getAttribute('x')"), String(coordinates.A구역.x * 1000));
  assert.ok((await visible()).includes('같은 구역의 직전 평가'));
  await click('이 조건으로 재평가 준비');
  await until(() => evaluate("document.querySelector('#zone-question-Q002')?.value==='5'"), 'historical condition restore');
  await setValue('#zone-question-Q002', 7);
  await until(() => evaluate("document.querySelector('.zone-assessment-panel')?.innerText.includes('재계산 필요')"), 'reassessment condition change');
  await click('수정 조건으로 재계산');
  await until(() => evaluate("document.querySelector('.zone-assessment-panel .success')?.textContent.includes('저장되었습니다')"), 'third A assessment');
  const latest = await request(`/sites/${siteId}/blueprints/${image['이미지ID']}/zones/${zones.A구역['작업구역ID']}/assessment`);
  assert.equal(latest['최근평가']['이전구역평가ID'], a2['평가ID']);
  assert.equal(latest['최근평가']['입력조건']['answers']['Q002'], 7);
  const previous = await request(`/zone-assessments/${latest['최근평가']['평가ID']}/previous`);
  assert.equal(previous['이전평가ID'], a2['평가ID']);
  assert.notEqual(previous['이전평가ID'], b1['평가ID']);
  assert.ok(previous.comparison['비교안내']['점수차이표시가능']);

  await evaluate("document.querySelectorAll('nav button')[2].click()");
  await until(() => evaluate("document.querySelectorAll('.record-list button').length===2"), 'legacy and linked single assessments');
  const legacyDetail = await request(`/evaluations/${legacy['평가ID']}`);
  assert.equal(legacyDetail['요약']['위험지수'], legacy['요약']['위험지수']);
  assert.equal(legacyDetail['현장조감도'], undefined);
  assert.deepEqual(errors, []);
  console.log('PASS: zone histories stay scoped across A/B; A/B dashboard selection and grade color; C unassessed; immutable coordinate/input snapshots; exact-image history view; reassessment creates a new linked record with automatic previous comparison; legacy record API compatibility; 1440px and 390px layouts.');
} finally {
  socket?.close(); await server?.close();
  for (const child of children.reverse()) child.kill();
  await sleep(500);
  assert.ok(resolve(temporary).startsWith(resolve(tmpdir()) + '\fire-risk-zone-history-'));
  await rm(temporary, { recursive: true, force: true, maxRetries: 10, retryDelay: 250 });
}
