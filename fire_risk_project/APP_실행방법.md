# 로컬 웹앱 실행

현재 웹앱은 React 화면과 FastAPI API로 실행합니다. 두 터미널을 열고 저장소 폴더에서 각각 실행한 뒤 `http://127.0.0.1:5173`에 접속하세요. API 확인 주소는 `http://127.0.0.1:8000/health`입니다.

## 1. API 서버

저장소 폴더(`construction_safety_visualize`)의 PowerShell 터미널에서 실행합니다. 아래 설정은 로컬 SQLite를 사용하고 Render용 설정이 로컬 실행을 방해하지 않게 합니다.

```powershell
$env:RENDER = ""
$env:DATABASE_URL = ""
$env:APP_ACCESS_KEY = ""
.\.venv\Scripts\python.exe -m uvicorn fire_risk_project.api:app --reload --host 127.0.0.1 --port 8000
```

API가 시작되면 터미널을 켜 둡니다.

## 2. 화면 서버

두 번째 PowerShell 터미널에서 저장소 폴더 기준으로 실행합니다.

```powershell
$env:VITE_API_BASE_URL = ""
Set-Location .\fire_risk_project\frontend
$env:PATH = (Resolve-Path ..\..\.tools\node-v22.23.3-win-x64).Path + ";" + $env:PATH
..\..\.tools\node-v22.23.3-win-x64\node.exe .\node_modules\vite\bin\vite.js --configLoader runner --host 127.0.0.1 --port 5173
```

그 다음 브라우저에서 `http://127.0.0.1:5173`을 엽니다. Vite가 `/api` 요청을 로컬 API의 8000 포트로 전달합니다. 화면과 API 터미널을 모두 켜 두고, 종료할 때는 각 터미널에서 `Ctrl+C`를 누릅니다.

이 프로젝트는 로컬 실행 시 기본적으로 `fire_risk_project/outputs/api_evaluations.sqlite3`에 평가 기록을 저장합니다. `DATABASE_URL`을 비워 둬야 로컬 Postgres/원격 DB가 아닌 SQLite를 사용합니다. 기존 평가 데이터를 지우지 않도록 DB 파일을 삭제하지 마세요.

필요한 경우 Node.js `22.12` 이상과 npm을 설치한 환경에서는 화면 서버 명령 대신 `Set-Location .\fire_risk_project\frontend` 후 `npm run dev -- --host 127.0.0.1 --port 5173`을 실행할 수도 있습니다.

## 기존 Streamlit 시험 화면

기존 시험용 Streamlit 화면도 별도로 남아 있습니다. 웹앱과 다른 화면이며, 필요할 때만 저장소 폴더에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\fire_risk_project\app.py --server.address localhost
```

브라우저에서 `http://localhost:8501`을 엽니다. Streamlit 시험 데이터와 현재 웹앱의 평가 기록 저장소는 별개입니다. 배포 설정은 [DEPLOYMENT.md](DEPLOYMENT.md)를 참고하세요.
