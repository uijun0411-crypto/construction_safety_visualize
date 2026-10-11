"""실행: python -m streamlit run fire_risk_project/app.py"""
from pathlib import Path
import hashlib
import os
import sqlite3
import pandas as pd
import streamlit as st
import risk_engine as engine
from dashboard_views import render_dashboard

ROOT = Path(__file__).resolve().parent
STORAGE = Path(os.environ.get("FIRE_RISK_STORAGE", str(ROOT / "outputs/evaluations_demo.sqlite3")))
st.set_page_config(page_title="건설현장 화재 위험도", page_icon="🏗️", layout="wide")
st.title("작업 시작 전 화재 위험도 평가")
st.caption("H05 용접·용단 · 규칙 기반 시험 평가")
st.warning("잠정 점수입니다. 법령·잔여 적용조건이 미검증되어 최종판정은 보류됩니다.")

def show_table(table, **kwargs):
    rendered = table.copy()
    for column in rendered.columns:
        if rendered[column].dtype == object:
            rendered[column] = rendered[column].astype('string')
    st.dataframe(rendered, **kwargs)

def clear_result():
    st.session_state.pop("current_evaluation", None)

try:
    engine.load_databases(ROOT / "data")
    version = hashlib.sha256(
        (ROOT / "risk_engine.py").read_bytes() +
        b"".join(f.read_bytes() for f in sorted((ROOT / "data").glob("*.csv")))
    ).hexdigest()
except (OSError, ValueError, KeyError) as error:
    st.error(f"데이터를 읽을 수 없습니다: {error}")
    st.stop()
if st.session_state.get("data_version") != version:
    clear_result()
    st.session_state["data_version"] = version

evaluate_tab, dashboard_tab, history_tab = st.tabs(["새 평가", "결과 대시보드", "저장 기록·비교"])
with evaluate_tab:
    st.subheader("1. 현장 정보와 작업 상태")
    with st.expander("거리 입력과 용접방화포 질문 안내"):
        st.markdown(
            "- 현재 거리 점수는 11m 미만/이상으로 구분합니다. "
            "화재감시자의 거리 관련 법령 조건은 11m 이내여서 정확히 11m를 포함합니다. "
            "거리만으로 배치 의무 전체를 판정하지 않습니다.\n"
            "- Q003은 불티 비산방지조치 실시 여부입니다. "
            "Q018은 용접방화포를 사용할 때 제품의 성능인증을 확인합니다. "
            "다른 방법을 쓴다면 미사용으로 응답하되 Q003의 실제 조치 상태도 확인하세요."
        )

    site_name = st.text_input("현장명", key="site_name", on_change=clear_result)
    st.caption("확인한 상태를 선택하세요. 선택하지 않은 항목은 미입력으로 남습니다.")
    raw_questions = engine.get_questions_for_task("H05")
    prior = {
        qid: st.session_state[f"answer_{qid}"]
        for qid in raw_questions["항목ID"]
        if st.session_state.get(f"answer_{qid}") is not None
    }
    question_table = engine.get_prework_questions("H05", prior)
    answers = {}
    columns = st.columns(2)
    visible = 0
    for _, question in question_table.iterrows():
        qid = question["항목ID"]
        status = question["적용상태"]
        if status != "적용":
            if status == "조건제외":
                st.caption(f"{qid}: {question['확인항목']} — 조건에 따라 제외")
            elif status == "선행응답필요":
                st.caption(f"{qid}: 먼저 주변 가연물 존재 여부를 선택하세요.")
            continue
        with columns[visible % 2]:
            label = f"{qid} · {question['확인항목']}"
            if question["입력형식"] == "선택":
                choices = [v.strip() for v in question["선택지·허용값"].split("/")]
                value = st.selectbox(label, choices, index=None, key=f"answer_{qid}",
                                     placeholder="선택하세요", on_change=clear_result,
                                     help=question["사전안내"])
            else:
                value = st.number_input(
                    f"{label} ({question['단위']})", min_value=0.0, value=None,
                    key=f"answer_{qid}", on_change=clear_result,
                )
            if value is not None:
                answers[qid] = value
        visible += 1

    st.subheader("2. 화재감시자 추가 조건")
    extras = {}
    for _, question in engine.watcher_questions.iterrows():
        qid = question["추가질문ID"]
        extras[qid] = st.selectbox(
            f"{qid} · {question['질문']}", ["확인불가", "예", "아니오"],
            key=f"extra_{qid}", on_change=clear_result,
        )

    if st.button("평가하기", type="primary", key="evaluate"):
        clear_result()
        try:
            if any(answers.get(qid) == "해당없음" for qid in ("Q003", "Q004")):
                raise ValueError(
                    "Q003·Q004의 해당없음 근거는 아직 자동 검증하지 않습니다. "
                    "이 화면에서는 계산을 보류합니다. 실제 상태와 다르게 응답을 바꾸지 마세요."
                )
            st.session_state["current_evaluation"] = engine.build_evaluation(
                site_name, "H05", answers, extras
            )
        except (ValueError, KeyError, NotImplementedError) as error:
            st.error(str(error))

    record = st.session_state.get("current_evaluation")
    if record is not None:
        st.subheader("3. 평가 결과")
        summary = record["요약"]
        left, right = st.columns(2)
        left.metric("위험지수 (0–100)", f"{summary['위험지수']:.2f}" if summary["위험지수"] is not None else "평가불가")
        right.metric("기본위험등급 · 잠정", summary["기본위험등급(잠정)"])
        st.warning(summary["최종판정"])
        st.info(record["화재감시자검토"]["확인메시지"])
        with st.expander("질문별 계산 결과"):
            show_table(pd.DataFrame(record["응답상세"]), hide_index=True)
        st.caption(f"시험용 저장소에 기록합니다. 평가ID: {record['평가ID']}")
        if st.button("이 평가 저장", key="save"):
            try:
                status = engine.save_evaluation(record, STORAGE)
                st.success(status["저장상태"])
            except (OSError, sqlite3.Error, ValueError) as error:
                st.error(f"저장하지 못했습니다: {error}")

with history_tab:
    st.subheader("저장된 평가")
    keyword = st.text_input("현장명 검색", key="history_keyword")
    try:
        history = engine.search_evaluations(STORAGE, site_keyword=keyword, task_id="H05")
        if history.empty:
            st.info("저장된 평가가 없거나 검색 조건에 맞는 기록이 없습니다.")
        else:
            show_table(history, hide_index=True)
            ids = history["평가ID"].tolist()
            labels = history.set_index("평가ID")
            def label(identifier):
                row = labels.loc[identifier]
                return f"{row['평가일시']} · {row['현장명']} · {identifier[:8]}"
            selected = st.selectbox("상세 조회할 평가", ids, format_func=label, key="view_id")
            for title, table in engine.get_evaluation_tables(selected, STORAGE).items():
                with st.expander(title, expanded=title == "평가요약"):
                    if table.empty:
                        st.caption("기록 없음")
                    else:
                        show_table(table, hide_index=True)
            st.subheader("평가 두 건 비교")
            st.caption("같은 현장·작업을 선택하세요. 기준이 다르면 점수 차이는 표시하지 않습니다.")
            before_id = st.selectbox("이전 평가", ids, index=None, format_func=label, key="before_id")
            after_id = st.selectbox("이후 평가", ids, index=None, format_func=label, key="after_id")
            if st.button("비교하기", key="compare"):
                if not before_id or not after_id:
                    st.error("이전·이후 평가를 모두 선택하세요.")
                else:
                    try:
                        result = engine.compare_evaluations(before_id, after_id, STORAGE)
                        show_table(pd.DataFrame([result["비교안내"]]), hide_index=True)
                        for title in ("평가요약", "변경항목", "추가응답변경", "화재감시자검토"):
                            st.markdown(f"**{title}**")
                            show_table(result[title], hide_index=True)
                    except (ValueError, KeyError) as error:
                        st.error(str(error))
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        st.error(f"기록을 조회할 수 없습니다: {error}")



with dashboard_tab:
    try:
        render_dashboard(engine, STORAGE, st.session_state.get("current_evaluation"))
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        st.error(f"대시보드를 표시할 수 없습니다: {error}")
