# 로컬 평가 화면 실행

React UI + Python API 실행 및 Vercel/Render 배포는 [DEPLOYMENT.md](DEPLOYMENT.md)를 참고하세요.
아래는 기존 Streamlit 화면의 실행 방법입니다.

VS Code에서 터미널 > 새 터미널을 열고 PowerShell에서 실행합니다.

```powershell
cd "C:\Users\uijun\OneDrive\바탕 화면\Project"
.\.venv\Scripts\python.exe -m streamlit run .\fire_risk_project\app.py --server.address localhost
```

브라우저에서 http://localhost:8501 을 엽니다. 터미널을 유지하세요. 종료는 Ctrl+C입니다.

- H05 질문에 응답한 뒤 평가하기를 누릅니다.
- 입력을 변경하면 이전 결과가 지워집니다. 다시 평가하세요.
- 이 평가 저장 버튼으로 시험용 outputs/evaluations_demo.sqlite3에 저장합니다.
- 저장 기록·비교 탭에서 노트북으로 저장한 시험 기록도 볼 수 있습니다.
- Q003·Q004의 해당없음은 검증 전까지 화면에서 계산을 보류합니다.
- 잠정 점수이며 최종판정은 계속 보류입니다.

재설치가 필요한 경우 같은 터미널에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\fire_risk_project\requirements-app.txt
```

