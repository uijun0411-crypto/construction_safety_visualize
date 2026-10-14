# React + Python API 실행 및 배포

## 구성

```text
React + Vite (Vercel)
  └─ HTTPS 요청 → FastAPI (Vercel Functions)
                    ├─ risk_engine.py + data/*.csv: 계산·검증
                    └─ Supabase/Postgres: 평가 초안·저장 기록
```

Vercel 프로젝트 두 개가 같은 GitHub 저장소를 사용합니다. 하나는 화면,
하나는 API를 배포합니다. API 프로젝트는 Vercel의 임시 파일시스템을 DB로
사용하지 않으며 `DATABASE_URL`에 영구 Postgres 연결이 필요합니다.

React는 입력과 화면 표시를 담당합니다. 조건부 질문, 평가, 저장, 검색,
상세 조회, 비교, 현황 집계는 Python API를 사용합니다.
브라우저 localStorage나 브라우저 DB에 평가를 저장하지 않습니다.
지원 작업은 기존 화면과 같은 H05 용접·용단입니다.
기존 `app.py`와 노트북은 별도로 실행할 수 있습니다.
새 UI 진입점은 `frontend/src/main.jsx`, API 진입점은 `api.py`입니다.

## 로컬 실행

프로젝트 최상위 `Project`에서 터미널 1:

```powershell
.\.venv\Scripts\python.exe -m pip install -r fire_risk_project/requirements-api.txt
.\.venv\Scripts\python.exe -m uvicorn fire_risk_project.api:app --reload --host 127.0.0.1 --port 8000
```

Node.js 22.12 이상 설치 후 터미널 2:

```powershell
cd fire_risk_project/frontend
npm ci
npm run dev
```

http://127.0.0.1:5173 을 엽니다. 개발 서버가 `/api`를 Python 8000 포트로
프록시하므로 로컬에서는 `.env`가 필요 없습니다. API 명세는 http://127.0.0.1:8000/docs 입니다.

이번 작업 환경에는 Node가 PATH에 없어 `.tools/node-v22.23.3-win-x64`에 준비했습니다.
프로젝트 최상위에서 다음 명령으로 PATH에 추가한 뒤 위 프런트엔드 명령을 실행할 수 있습니다.

```powershell
$env:Path = (Resolve-Path '.tools/node-v22.23.3-win-x64').Path + ';' + $env:Path
```

새 API 저장 위치 기본값은 `fire_risk_project/outputs/api_evaluations.sqlite3`입니다.
기존 시험 기록을 함께 사용하려면 API 실행 전에 다음 값을 지정합니다.

```powershell
$env:FIRE_RISK_STORAGE = (Join-Path (Get-Location) 'fire_risk_project/outputs/evaluations_demo.sqlite3')
```

API는 시작 시 환경변수를 읽습니다. 변경 후 다시 실행하세요.
백엔드는 `.env`를 자동으로 읽지 않습니다. PowerShell 환경변수나 호스팅 환경변수를 사용하세요.
`DATABASE_URL`이 있으면 SQLite 파일 대신 Postgres(Supabase 등)에 저장합니다.

## Supabase 저장소 사용

Supabase 프로젝트에서 Postgres 연결 문자열을 만든 뒤 API를 실행하는 환경의 `DATABASE_URL`에 넣습니다.
연결 문자열에는 DB 비밀번호가 포함되므로 프런트엔드 `VITE_*` 변수에 넣지 마세요.

API가 시작할 때 아래 테이블을 자동으로 생성합니다. 직접 만들고 싶다면 SQL Editor에서
다음 SQL을 실행해도 됩니다.

```sql
create table if not exists evaluations (
  evaluation_id text primary key,
  payload jsonb not null
);

create table if not exists evaluation_drafts (
  evaluation_id text primary key,
  payload jsonb not null,
  created_at double precision not null
);
```

로컬에서 Supabase 연결을 시험하려면 macOS/Linux는 다음처럼 실행합니다.

```bash
DATABASE_URL='postgresql://...' ./.venv/bin/python -m uvicorn fire_risk_project.api:app --host 127.0.0.1 --port 8000
```

PowerShell은 다음처럼 실행합니다.

```powershell
$env:DATABASE_URL = 'postgresql://...'
.\.venv\Scripts\python.exe -m uvicorn fire_risk_project.api:app --reload --host 127.0.0.1 --port 8000
```

## GitHub 저장소에서 Vercel에 배포

FastAPI는 Vercel Python Functions에서 실행할 수 있습니다. 저장소에는 최상위
`index.py`, `requirements.txt`, `vercel.json`을 추가했습니다. 현재 Vercel 화면
프로젝트의 Root Directory가 `fire_risk_project/frontend`라면 그 프로젝트는
그대로 화면용으로 유지하고, 같은 GitHub 저장소를 다시 가져와 API용 Vercel
프로젝트를 하나 더 만듭니다.

API 프로젝트 설정:

| 설정 | 값 |
| --- | --- |
| Root Directory | 저장소 최상위 (`.`) |
| Framework | FastAPI 자동 감지 |
| Build Command / Output Directory | 자동 감지 기본값 |
| `DATABASE_URL` | 기존 평가 기록이 있는 영구 Postgres 연결 문자열 |
| `APP_ACCESS_KEY` | 접속 키로 사용할 긴 임의 문자열 |
| `CORS_ORIGINS` | `https://constructionsafetyvisualize.vercel.app` |

`DATABASE_URL`은 Vercel API 프로젝트의 Environment Variables에만 입력합니다.
프런트엔드 변수(`VITE_*`)에는 DB 주소나 접속 키를 넣지 마세요. 기존 기록을
유지하려면 이전 API가 사용하던 것과 **동일한 Postgres 데이터베이스**를 연결해야
합니다. 이전 저장소가 SQLite였다면 기존 기록은 별도로 내보내고 가져와야 합니다.
Vercel 실행 환경에서 Postgres가 설정되지 않으면 SQLite로 조용히 넘어가지 않고
API 시작을 거부합니다.

API 프로젝트를 배포한 다음 해당 프로젝트의 Vercel 도메인을 확인합니다. `/health`
에서 `{"status":"ok"}`가 나오면 API가 준비된 것입니다.

화면 프로젝트 설정:

| 설정 | 값 |
| --- | --- |
| Root Directory | `fire_risk_project/frontend` |
| Framework Preset | Vite |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Node.js | 22.x 또는 그 이상 지원 버전 |
| Environment Variable | `VITE_API_BASE_URL=https://API-프로젝트-도메인.vercel.app` |

`VITE_API_BASE_URL`에는 `/api`를 붙이지 않습니다. Production 환경에 지정하고,
Preview를 사용하면 해당 환경에도 지정합니다. Vite 변수는 빌드 시 반영되므로
주소 변경 후 다시 배포합니다. Production에서 주소가 빠지면 화면에서 설정 오류를 안내합니다.

화면을 열고 API 프로젝트에 설정한 `APP_ACCESS_KEY`를 접속 화면에 입력합니다.
키는 메모리에만 두며 새로고침하면 다시 입력합니다.
**키를 `VITE_*` 변수에 넣지 마세요. 해당 값은 공개 JS에 포함됩니다.**

화면 주소가 바뀌면 API 프로젝트의 `CORS_ORIGINS`도 실제 Origin에 맞춰 수정합니다.
`VITE_API_BASE_URL`을 바꾸거나 환경변수를 추가한 경우 화면 프로젝트를 다시 배포합니다.

공식 문서: [Vercel Python Functions](https://vercel.com/docs/functions/runtimes/python),
[FastAPI on Vercel](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel),
[Vercel Vite](https://vercel.com/docs/frameworks/frontend/vite),
[Vite 환경변수](https://vite.dev/guide/env-and-mode).

## API 요청 흐름

| 요청 | 용도 |
| --- | --- |
| `GET /health` | 서버 상태 (인증 없이) |
| `GET /api/session` | 접속 키 검증 |
| `POST /api/questions` | 응답에 따른 질문 적용·제외 여부 |
| `POST /api/evaluate` | 계산 후 서버에 24시간짜리 임시 결과 보관 |
| `POST /api/evaluations/{id}/save` | 서버 결과를 저장 기록으로 확정 |
| `GET /api/evaluations?site_keyword=...` | 현장명 검색 |
| `GET /api/evaluations/{id}` | 저장 당시 결과 조회 |
| `POST /api/compare` | 이전·이후 평가 비교 |
| `GET /api/dashboard?site=...` | 현장별 현황·동일 기준 추이 |

키가 설정되면 `/api/*`에 `X-Access-Key` 헤더가 필요합니다.
평가 요청에는 `site_name`, `task_id`(기본 H05), `answers`, `watcher_answers`를 보냅니다.
저장은 ID만 사용하고 브라우저가 전달하는 점수는 반영하지 않습니다.
같은 ID 재저장은 중복 기록을 만들지 않습니다.
미저장 초안은 목록에 나오지 않으며 24시간 후 저장할 수 없습니다.
만료 초안은 다음 평가 요청 시 정리됩니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r fire_risk_project/requirements-api-dev.txt
.\.venv\Scripts\python.exe -m unittest fire_risk_project.test_api -v
cd fire_risk_project/frontend
npm ci
npm run build
```

테스트는 임시 DB에서 기존 엔진과 결과 일치, 조건부 질문, 계산 보류,
접속 키·CORS, 저장·재저장·재시작 후 조회, 비교·초안 만료를 확인합니다.

## 문제 확인

- Vercel `NOT_FOUND`: Root Directory, `dist` 출력 설정, 배포 브랜치의 frontend 파일을 확인합니다.
- 서버 연결 실패: API Vercel 프로젝트의 `/health`, `VITE_API_BASE_URL`, `CORS_ORIGINS`를 확인합니다.
- 접속 키 오류: API Vercel 프로젝트의 `APP_ACCESS_KEY`와 입력한 키가 같은지 확인합니다.
- 재배포 후 기록 없음: API Vercel 프로젝트가 기존 `DATABASE_URL`의 Postgres를 사용하는지 확인합니다.
- Streamlit이 열림: React 주소(로컬 5173 또는 Vercel)를 엽니다. 8501은 기존 화면입니다.
