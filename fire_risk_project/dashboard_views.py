"""Streamlit 결과 시각화. 저장 당시 값을 사용하며 위험점수를 다시 산정하지 않습니다."""
import pandas as pd
import altair as alt
import streamlit as st

def contribution_table(record):
    detail = pd.DataFrame(record["응답상세"])
    columns = ["항목ID", "확인항목", "가중점수", "위험지수 기여점수"]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    selected = detail.loc[detail["집계대표여부"].eq(True)].copy()
    maximum = record["요약"]["최대가중점수"]
    selected["위험지수 기여점수"] = (
        selected["가중점수"] / maximum * 100 if maximum and maximum > 0 else None
    )
    return selected[columns].sort_values("가중점수", ascending=False).reset_index(drop=True)

def render_assessment(record, key_prefix):
    summary = record["요약"]
    st.caption(f"{record['현장명']} · {record['평가일시']} · {record['평가ID']}")
    cards = st.columns(4)
    value = summary.get("위험지수")
    cards[0].metric("위험지수", "미산정" if value is None else f"{value:.2f} / 100")
    cards[1].metric("잠정등급", summary.get("기본위험등급(잠정)", "미검증"))
    cards[2].metric("집계 항목", summary.get("집계항목수", 0))
    cards[3].metric("제외 질문", summary.get("제외질문수", 0))
    st.warning(summary["최종판정"])
    st.caption("사고 발생확률이 아닌 내부 규칙 점수입니다. 제외·0점 항목도 안전 확인 완료를 뜻하지 않습니다.")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### 점수에 기여한 위험요인")
        contribution = contribution_table(record)
        positive = contribution.loc[contribution["가중점수"].gt(0)]
        if positive.empty:
            st.info("양수로 집계된 위험요인이 없습니다. 적용조건과 미확인 항목은 별도로 확인하세요.")
        else:
            chart = alt.Chart(positive).mark_bar(color="#c56832", cornerRadiusEnd=3).encode(
                x=alt.X("위험지수 기여점수:Q", title="전체 위험지수에 더해진 점수", scale=alt.Scale(zero=True)),
                y=alt.Y("확인항목:N", sort="-x", title=None,
                        axis=alt.Axis(labelLimit=260)),
                tooltip=["항목ID:N", "확인항목:N", alt.Tooltip("가중점수:Q", format=".2f"),
                         alt.Tooltip("위험지수 기여점수:Q", format=".2f")],
            ).properties(height=max(180, len(positive)*45))
            st.altair_chart(chart, width="stretch", key=key_prefix+"_contribution")
        st.caption("중복집계 대표 항목만 표시합니다. 기여점수 합계는 전체 위험지수와 같습니다.")
    with right:
        st.markdown("#### 확인이 필요한 응답")
        rows = record["응답상세"]
        counts = {
            "확인불가": sum(r.get("사용자응답") == "확인불가" for r in rows if r.get("적용상태") == "적용"),
            "해당없음": sum(r.get("사용자응답") == "해당없음" for r in rows if r.get("적용상태") == "적용"),
            "추가질문 확인불가": sum(r.get("응답") == "확인불가" for r in record["화재감시자응답"] or []),
        }
        st.dataframe(pd.DataFrame(counts.items(), columns=["구분", "질문 수"]), hide_index=True)
        watcher = record.get("화재감시자검토")
        if watcher:
            st.info(watcher["확인메시지"])
            st.caption(watcher["검토결과"])
    with st.expander("집계·제외 내역"):
        table = pd.DataFrame(record["응답상세"])
        wanted = [c for c in ["항목ID", "확인항목", "사용자응답", "가중점수", "집계대표여부", "적용상태", "제외사유"] if c in table]
        display = table[wanted].copy()
        if "사용자응답" in display:
            display["사용자응답"] = display["사용자응답"].astype("string")
        st.dataframe(display, hide_index=True)

def history_frame(records):
    return pd.DataFrame([
        {"평가ID": r["평가ID"], "현장명": r["현장명"], "평가일시": r["평가일시"],
         "위험지수": r["요약"].get("위험지수"),
         "잠정등급": r["요약"].get("기본위험등급(잠정)", "미검증"),
         "최종판정": r["요약"].get("최종판정", "미검증"),
         "기준그룹": (r.get("계산데이터SHA256"), r.get("엔진SHA256"),
                      r["요약"].get("최대가중점수"))}
        for r in records
    ])

def render_dashboard(engine, storage, current_record):
    st.subheader("결과 대시보드")
    available = engine.search_evaluations(storage, task_id="H05")
    views = ["현재 평가"] + (["저장된 평가"] if not available.empty else [])
    view = st.radio("상세 결과 기준", views, horizontal=True, key="dashboard_view")
    if view == "현재 평가":
        if current_record is None:
            st.info("새 평가 탭에서 평가하기를 누르면 현재 결과가 표시됩니다.")
        else:
            render_assessment(current_record, "dashboard_current")
    else:
        labels = available.set_index("평가ID")
        chosen = st.selectbox(
            "대시보드에서 볼 평가", available["평가ID"].tolist(),
            format_func=lambda x: f"{labels.loc[x, '현장명']} · {labels.loc[x, '평가일시']} · {x[:8]}",
            key="dashboard_record",
        )
        render_assessment(engine.load_evaluation(chosen, storage), "dashboard_saved")

    st.divider()
    st.subheader("저장된 평가 현황")
    if available.empty:
        st.info("평가를 저장하면 현장별 현황이 표시됩니다.")
        return
    site = st.selectbox("현장 필터", ["전체 현장"] + sorted(available["현장명"].unique()),
                        key="dashboard_site")
    subset = available if site == "전체 현장" else available.loc[available["현장명"] == site]
    records = [engine.load_evaluation(x, storage) for x in subset["평가ID"]]
    frame = history_frame(records)
    cards = st.columns(3)
    cards[0].metric("저장 평가", len(frame))
    cards[1].metric("현장", frame["현장명"].nunique())
    cards[2].metric("판정 보류", frame["최종판정"].str.startswith("보류").sum())
    st.caption("같은 현장의 반복 평가도 각각 한 건입니다. 저장 당시의 잠정등급이며 사고 건수나 확률이 아닙니다.")
    counts = frame.groupby("잠정등급").size().reset_index(name="평가 건수")
    st.altair_chart(alt.Chart(counts).mark_bar(color="#3b7284").encode(
        x=alt.X("잠정등급:N", sort=["낮음", "주의", "높음", "매우높음", "평가불가"]),
        y=alt.Y("평가 건수:Q", axis=alt.Axis(tickMinStep=1)),
        tooltip=["잠정등급", "평가 건수"],
    ).properties(height=220), width="stretch", key="dashboard_grades")

    st.markdown("#### 현장별 점수 기록")
    if site == "전체 현장":
        st.caption("시간에 따른 점수를 보려면 위 현장 필터에서 한 현장을 선택하세요.")
        return
    valid_groups = [g for g in dict.fromkeys(frame["기준그룹"]) if g[0] and g[1]]
    if not valid_groups:
        st.info("계산 기준 정보가 없어 추이를 표시하지 않습니다.")
        return
    group_index = st.selectbox(
        "동일 기준으로 묶은 평가", list(range(len(valid_groups))),
        format_func=lambda x: f"기준 그룹 {x+1} · 분모 {valid_groups[x][2]}",
        key="dashboard_group",
    )
    group = valid_groups[group_index]
    trend = frame.loc[frame["기준그룹"].map(lambda x: x == group)].copy()
    trend["평가일시"] = pd.to_datetime(trend["평가일시"], utc=True).dt.tz_convert("Asia/Seoul")
    trend = trend.sort_values(["평가일시", "평가ID"])
    st.caption(f"같은 데이터·엔진·분모를 사용한 {len(trend)}건만 표시합니다. 점수 하락을 안전성 개선으로 단정하지 않습니다.")
    st.altair_chart(alt.Chart(trend.drop(columns="기준그룹")).mark_line(
        point=True, color="#3b7284"
    ).encode(
        x=alt.X("평가일시:T", title="평가일시"),
        y=alt.Y("위험지수:Q", scale=alt.Scale(domain=[0, 100])),
        tooltip=["평가ID", "평가일시:T", "위험지수:Q", "잠정등급"],
    ).properties(height=260), width="stretch", key="dashboard_trend")

