"""Provisional, transparent weather-context indicator; it does not alter the fire risk index."""


def assess(snapshot, task_group, answers, exposure):
    if not snapshot:
        return {"상태": "자료없음", "안내": "평가 당시 저장된 기상자료가 없어 기상조건을 검토하지 않았습니다."}
    if exposure not in {"실외", "실내"}:
        return {"상태": "현장확인필요", "안내": "작업장 실외 노출 여부를 확인해야 기상조건을 검토할 수 있습니다."}
    if exposure == "실내":
        return {"상태": "실내작업", "안내": "지역 기상값은 표시하지만 실내 작업의 기상 보정에는 사용하지 않았습니다.", "점수": 0, "최대점수": 3, "요인": []}

    groups = str(task_group)
    weather_relevant = any(term in groups for term in ("화기", "불티", "마찰·절삭", "가열·열원", "인화성물질"))
    if not weather_relevant:
        return {"상태": "비대상작업", "안내": "선택 작업은 이번 시범 기상검토 대상이 아닙니다.", "점수": 0, "최대점수": 3, "요인": []}
    if answers.get("Q001") != "있음":
        return {"상태": "가연물확인필요", "안내": "주변 가연물이 확인된 경우에만 시범 기상 가산요인을 검토합니다.", "점수": 0, "최대점수": 3, "요인": []}

    observed = snapshot.get("observed") or {}
    forecast = snapshot.get("forecast") or {}
    factors = []
    missing = []
    # The configured source is the village short-term forecast, not an
    # observation endpoint. Keep compatibility with older snapshots that have
    # observed values, while using forecast values for new snapshots.
    humidity = observed.get("humidity")
    if not isinstance(humidity, (int, float)):
        humidity = forecast.get("humidity")
    temperature = observed.get("temperature")
    if not isinstance(temperature, (int, float)):
        temperature = forecast.get("temperature")
    wind = forecast.get("wind_speed")

    # Draft thresholds for discussion only; they are not regulatory limits or validated predictors.
    if isinstance(humidity, (int, float)) and humidity <= 30:
        factors.append({"요인": "낮은 상대습도", "기상값": f"{humidity}%", "점수": 1,
                        "기준": "시범 기준: 상대습도 30% 이하"})
    elif not isinstance(humidity, (int, float)):
        missing.append("상대습도")
    if isinstance(temperature, (int, float)) and temperature >= 30 and (
        "인화성물질" in groups or "가열·열원" in groups
    ):
        factors.append({"요인": "높은 기온", "기상값": f"{temperature}℃", "점수": 1,
                        "기준": "시범 기준: 기온 30℃ 이상, 인화성물질·가열 작업군에만 적용"})
    elif not isinstance(temperature, (int, float)) and (
        "인화성물질" in groups or "가열·열원" in groups
    ):
        missing.append("기온")
    if isinstance(wind, (int, float)) and wind >= 5 and any(
        term in groups for term in ("화기", "불티", "마찰·절삭")
    ):
        factors.append({"요인": "강한 바람", "기상값": f"{wind}m/s", "점수": 1,
                        "기준": "시범 기준: 풍속 5m/s 이상, 야외 불티 작업군에만 적용"})
    elif not isinstance(wind, (int, float)) and any(
        term in groups for term in ("화기", "불티", "마찰·절삭")
    ):
        missing.append("풍속")

    return {
        "상태": "부분자료" if missing else "시범검토",
        "점수": len(factors),
        "최대점수": 1 + int("인화성물질" in groups or "가열·열원" in groups) + int(any(
            term in groups for term in ("화기", "불티", "마찰·절삭")
        )),
        "요인": factors,
        "자료누락": missing,
        "안내": "시범 기상조건 참고점수입니다. 화재위험지수·등급에는 합산하지 않았으며, 화재확률이나 작업중지 기준이 아닙니다. 강수는 현장 가연물이 실제로 젖었는지 확인할 수 없어 점수 감산에 사용하지 않았습니다.",
    }
