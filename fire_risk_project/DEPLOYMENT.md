# React + Python API 실행 및 배포

## 구성

```text
React + Vite (Vercel)
  └─ HTTPS /api 요청 → FastAPI + Uvicorn (Render)
                         ├─ risk_engine.py + data/*.csv: 계산·검증
                         └─ SQLite: 평가 초안·저장 기록 (영구 디스크)
```

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

Supabase 프로젝트에서 Postgres 연결 문자열을 만든 뒤 Render의 `DATABASE_URL`에 넣습니다.
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

## 1. Python API를 Render에 배포

저장소를 GitHub에 올린 다음 Render에서 **New → Blueprint**로 연결하고
최상위 `render.yaml`을 사용합니다. 현재 설정은 **Free Web Service + Supabase Postgres**를
전제로 합니다. 이 작업에서는 호스팅 리소스를 생성하지 않았습니다.

Blueprint의 `CORS_ORIGINS`에 실제 Vercel 주소를 입력합니다.
예: `https://my-fire-risk.vercel.app` (경로와 마지막 `/` 없이).
접속 키 `APP_ACCESS_KEY`는 Render가 생성합니다.

New Web Service로 수동 생성한다면 아래 설정을 사용합니다.

| 설정 | 값 |
| --- | --- |
| Runtime | Python 3 |
| Root Directory | 비움 (저장소 최상위) |
| Build Command | `pip install -r fire_risk_project/requirements-api.txt` |
| Start Command | `uvicorn fire_risk_project.api:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health Check Path | `/health` |
| `PYTHON_VERSION` | `3.13.5` |
| `DATABASE_URL` | Supabase Postgres 연결 문자열 |
| `CORS_ORIGINS` | 실제 Vercel Origin |
| `APP_ACCESS_KEY` | 관리자가 생성한 긴 무작위 접속 키 |

배포 후 `https://서비스이름.onrender.com/health`에서 `{"status":"ok"}`를 확인합니다.
Render 환경에서 접속 키가 없으면 API 시작을 거부합니다.

`DATABASE_URL`을 설정하지 않으면 API는 SQLite 파일 저장으로 돌아갑니다. Render Free에서
SQLite 파일을 쓰면 재배포·재시작 시 기록 보존을 기대하기 어렵습니다.
기존 `evaluations_demo.sqlite3`는 자동으로 Supabase에 복사하지 않아 새 서버는 빈 기록으로 시작합니다.
중요한 기록은 Supabase 백업 또는 별도 내보내기를 유지하세요.

현재 접속 키는 팀 공용이며 키를 가진 사람은 저장 기록 전체를 볼 수 있습니다.
사용자별 데이터 분리가 필요하면 사용자 인증과 권한을 추가해야 합니다.

공식 문서: [FastAPI 배포](https://render.com/docs/deploy-fastapi),
[영구 디스크](https://render.com/docs/disks), [Blueprint 설정](https://render.com/docs/blueprint-spec).

## 2. React를 Vercel에 배포

기존 Vercel 프로젝트를 아래처럼 설정하고 새 코드를 push한 뒤 재배포합니다.

| 설정 | 값 |
| --- | --- |
| Root Directory | `fire_risk_project/frontend` |
| Framework Preset | Vite |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Node.js | 22.x 또는 그 이상 지원 버전 |
| Environment Variable | `VITE_API_BASE_URL=https://서비스이름.onrender.com` |

`VITE_API_BASE_URL`에는 `/api`를 붙이지 않습니다. Production 환경에 지정하고,
Preview를 사용하면 해당 환경에도 지정합니다. Vite 변수는 빌드 시 반영되므로
주소 변경 후 다시 배포합니다. Production에서 주소가 빠지면 화면에서 설정 오류를 안내합니다.

Vercel 앱을 열고 Render의 `APP_ACCESS_KEY`를 접속 화면에 입력합니다.
키는 메모리에만 두며 새로고침하면 다시 입력합니다.
**키를 `VITE_*` 변수에 넣지 마세요. 해당 값은 공개 JS에 포함됩니다.**

Vercel 도메인 변경 시 Render의 `CORS_ORIGINS`도 변경합니다.
여러 Origin은 쉼표로 구분합니다. 실제 사용하는 Production·Preview 주소만 추가합니다.

공식 문서: [Vercel Vite](https://vercel.com/docs/frameworks/frontend/vite),
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
- 서버 연결 실패: `/health`, API 주소, Render 상태, CORS Origin을 확인합니다.
- 접속 키 오류: Render의 키와 입력한 키가 같은지 확인합니다.
- 재배포 후 기록 없음: 저장 경로가 영구 디스크 아래인지 확인합니다.
- Streamlit이 열림: React 주소(로컬 5173 또는 Vercel)를 엽니다. 8501은 기존 화면입니다.
