const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
export async function api(path, body, signal, methodOverride) {
  if (import.meta.env.PROD && !base) throw new Error('API 주소가 설정되지 않았습니다. VITE_API_BASE_URL을 설정하고 다시 배포하세요.');
  let response;
  try {
    response = await fetch(`${base}/api${path}`, {
      method: methodOverride || (body === undefined ? 'GET' : 'POST'),
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('서버에 연결하지 못했습니다. API 실행 상태와 주소, CORS 설정을 확인하세요.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    if (response.status === 422 && Array.isArray(detail) && detail.some(item =>
      item?.type === 'extra_forbidden' && item?.loc?.includes('watcher_answers')
    )) {
      const error = new Error('화면과 API 서버의 버전이 맞지 않습니다. 현재 API가 watcher_answers 입력을 지원하지 않습니다. VITE_API_BASE_URL이 최신 API를 가리키는지, API 배포가 완료됐는지 확인하세요.');
      error.status = response.status;
      error.code = 'API_VERSION_MISMATCH';
      throw error;
    }
    const error = new Error(Array.isArray(detail) ? detail.map(x => `${x.loc.join('.')}: ${x.msg}`).join('\n') : detail || `요청 실패 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  if (data === null) throw new Error('API 응답 형식이 올바르지 않습니다. 서버 주소를 확인하세요.');
  return data;
}
