"""KMA village short-term forecast, isolated from scoring and existing weather CSV.

Only the server calls KMA. Signed snapshots survive serverless instance changes.
"""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import math
import os
from pathlib import Path
from threading import Lock
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, unquote
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

KST = timezone(timedelta(hours=9))
SOURCE = "https://www.data.go.kr/data/15084084/openapi.do"
ENDPOINT = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
CATALOGUE = json.loads((Path(__file__).parent / "data/kma-regions.json").read_text(encoding="utf-8"))
REGIONS = {r["id"]: r for r in CATALOGUE["regions"]}
_cache = {}
_lock = Lock()


class WeatherError(Exception):
    pass


def region(identifier):
    if identifier not in REGIONS:
        raise ValueError("현장 위치를 지역 목록에서 선택하세요.")
    return deepcopy(REGIONS[identifier])


def base_time(now):
    return forecast_base_time(now)


def forecast_base_time(now):
    # Village forecasts are issued eight times daily at 02, 05, 08, 11,
    # 14, 17, 20, and 23 KST. They are available about 10 minutes later.
    available = (now.astimezone(KST) - timedelta(minutes=10)).replace(
        minute=0, second=0, microsecond=0
    )
    for hour in (23, 20, 17, 14, 11, 8, 5, 2):
        candidate = available.replace(hour=hour)
        if candidate <= available:
            return candidate
    return (available - timedelta(days=1)).replace(hour=23)


def _number(values, code, low, high):
    try:
        value = float(values.get(code, ""))
        return value if math.isfinite(value) and low <= value <= high else None
    except (TypeError, ValueError):
        return None


def _precipitation(value):
    return {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기",
            "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림"}.get(str(value))


def parse_items(items, location, base, now):
    matching = [r for r in items if isinstance(r, dict) and str(r.get("nx")) == str(location["nx"])
                and str(r.get("ny")) == str(location["ny"])
                and r.get("baseDate") == base.strftime("%Y%m%d") and r.get("baseTime") == base.strftime("%H%M")]
    times = sorted({str(r.get("fcstDate", "")) + str(r.get("fcstTime", "")) for r in matching})
    target = next((t for t in times if len(t) == 12 and t >= now.strftime("%Y%m%d%H%M")), None)
    if not target:
        raise WeatherError("현재 시각 이후의 기상예보가 없습니다. 잠시 후 다시 조회하세요.")
    valid = datetime.strptime(target, "%Y%m%d%H%M").replace(tzinfo=KST)
    if valid - now > timedelta(hours=6):
        raise WeatherError("기상예보의 대상시각을 확인할 수 없습니다.")
    values = {r["category"]: str(r.get("fcstValue", "")) for r in matching if r.get("fcstDate", "") + r.get("fcstTime", "") == target}
    precipitation = _precipitation(values.get("PTY"))
    sky = {"1": "맑음", "3": "구름많음", "4": "흐림"}.get(values.get("SKY"))
    rainfall = values.get("PCP")
    if rainfall == "강수없음":
        rainfall = "0 mm"
    data = {"kind": "단기예보", "temperature": _number(values, "TMP", -80, 60),
            "humidity": _number(values, "REH", 0, 100), "precipitation": precipitation,
            "rainfall": rainfall, "precipitation_probability": _number(values, "POP", 0, 100), "sky": sky,
            "wind_speed": _number(values, "WSD", 0, 100),
            "wind_direction": _number(values, "VEC", 0, 360),
            "base_at": base.isoformat(), "valid_at": valid.isoformat()}
    if all(data[k] is None for k in ("temperature", "humidity", "precipitation", "sky", "wind_speed")):
        raise WeatherError("기상청 응답에 표시 가능한 기상정보가 없습니다.")
    return data


def _sign(data, key):
    payload = base64.urlsafe_b64encode(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()).decode()
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def service_key():
    # KMA_API_KEY/KMA_SERVICE_KEY are data.go.kr serviceKey values.
    return os.environ.get("KMA_API_KEY", "").strip() or os.environ.get("KMA_SERVICE_KEY", "").strip()


def _api_items(endpoint, key, location, base):
    params = {"serviceKey": unquote(key), "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
              "base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H%M"),
              "nx": location["nx"], "ny": location["ny"]}
    try:
        with urlopen(endpoint + "?" + urlencode(params), timeout=8) as response:
            payload = response.read(2_000_000)
    except HTTPError as error:
        # Do not include the URL or exception text: urllib's HTTPError URL contains
        # the serviceKey query parameter.
        api_code = None
        try:
            error_payload = error.read(64_000)
            try:
                error_data = json.loads(error_payload)
                # KMA can return a normal response envelope, while the data.go.kr
                # gateway wraps authentication failures in OpenAPI_ServiceResponse.
                # Parse both so a gateway error such as reason code 30 is not
                # collapsed into an unhelpful generic HTTP 403.
                response_header = (error_data.get("response") or {}).get("header") or {}
                gateway_header = ((error_data.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader") or {})
                api_code = (str(response_header.get("resultCode", ""))
                            or str(gateway_header.get("returnReasonCode", ""))
                            or str(gateway_header.get("errMsg", ""))
                            or None)
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
                root = ET.fromstring(error_payload)
                # data.go.kr gateway errors use returnReasonCode/returnAuthMsg;
                # normal API replies use response/header/resultCode.
                api_code = (root.findtext(".//resultCode")
                            or root.findtext(".//returnReasonCode")
                            or root.findtext(".//returnAuthMsg"))
        except Exception:
            # The gateway may return an HTML or empty error page.
            pass
        api_errors = {
            "20": "공공데이터포털에서 이 서비스의 이용 권한을 확인하지 못했습니다. 활용 신청 상태를 확인하세요.",
            "30": "공공데이터포털 오류 30: 요청에 포함된 serviceKey를 등록된 키로 인식하지 못했습니다.",
            "31": "서비스키 사용 기한이 만료됐습니다. 공공데이터포털에서 갱신하세요.",
            "SERVICE_ACCESS_DENIED_ERROR": "공공데이터포털에서 이 서비스의 이용 권한을 거부했습니다. 활용 신청 상태를 확인하세요.",
            "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "공공데이터포털 오류 30: 요청에 포함된 serviceKey를 등록된 키로 인식하지 못했습니다.",
            "DEADLINE_HAS_EXPIRED_ERROR": "serviceKey 사용 기한이 만료됐습니다. 공공데이터포털에서 이용 기간을 갱신하세요.",
            "29": "공공데이터포털이 Render 서버 IP를 차단했습니다. 활용지원센터에 문의하세요.",
            "BLACKLIST_IP_ACCESS_ERROR": "공공데이터포털이 Render 서버 IP를 차단했습니다. 활용지원센터에 문의하세요.",
        }
        if api_code in api_errors:
            raise WeatherError(api_errors[api_code]) from None
        if error.code in (401, 403):
            raise WeatherError(f"공공데이터포털이 요청을 거부했습니다 (HTTP {error.code}). serviceKey와 서비스 이용 권한을 확인하세요.") from None
        if error.code == 429:
            raise WeatherError("기상청 API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.") from None
        raise WeatherError(f"기상청 서버가 HTTP {error.code} 오류를 반환했습니다. 잠시 후 다시 시도하세요.") from None
    except (URLError, TimeoutError, OSError):
        raise WeatherError("기상청 서버에 연결하지 못했습니다. Render 로그와 네트워크 상태를 확인하세요.") from None
    try:
        response = json.loads(payload)
        result = response["response"]
        header = result["header"]
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
        raise WeatherError("기상청 응답 형식이 올바르지 않습니다. 인증키와 서비스 상태를 확인하세요.") from None
    # Accept both documented KMA response success code forms.
    if str(header.get("resultCode")) not in {"0", "00"}:
        code = str(header.get("resultCode", ""))
        message = str(header.get("resultMsg", ""))
        if code in {"30", "31"} or "AUTH" in message.upper() or "KEY" in message.upper():
            raise WeatherError("공공데이터포털이 serviceKey를 거부했습니다. Render의 KMA_API_KEY에 해당 서비스의 일반 인증키가 설정됐는지 확인하세요.")
        raise WeatherError("공공데이터포털 응답 오류입니다. 발표시각, 호출한도 또는 API 응답을 확인하세요.")
    try:
        return result["body"]["items"]["item"]
    except (KeyError, TypeError):
        raise WeatherError("공공데이터포털 응답에 예보 자료가 없습니다. 자료 발표시각을 확인하세요.") from None


def restore(token, identifier):
    """Accept only a server-issued snapshot for the selected region; no live lookup."""
    key = service_key()
    if not token or not key:
        return None
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data if data["region"]["id"] == identifier else None
    except (ValueError, KeyError, TypeError):
        return None


def fetch(identifier):
    location = region(identifier)
    key = service_key()
    if not key:
        raise WeatherError("기상정보 연동이 설정되지 않았습니다. 관리자에게 연동 설정을 요청하세요. 평가는 계속할 수 있습니다.")
    # Cache is per warm instance, bounded by the finite region catalogue.
    with _lock:
        cached = _cache.get(identifier)
        if cached and time.monotonic() - cached[0] < cached[1]:
            if isinstance(cached[2], str):
                raise WeatherError(cached[2])
            data = deepcopy(cached[2])
        else:
            now = datetime.now(KST)
            base = forecast_base_time(now)
            try:
                rows = _api_items(ENDPOINT, key, location, base)
                forecast = parse_items(rows, location, base, now)
            except Exception as error:
                # Never log the request URL or exception text: either may contain
                # credentials. Keep enough metadata to diagnose upstream failures.
                logging.warning(
                    "KMA village forecast request failed: error_type=%s http_status=%s",
                    type(error).__name__, getattr(error, "code", None),
                )
                message = str(error) if isinstance(error, WeatherError) else "조회 실패"
                _cache[identifier] = (time.monotonic(), 30, message)
                raise WeatherError(message)
            data = {"region": location, "observed": None, "forecast": forecast,
                    "fetched_at": now.isoformat(), "source": "기상청 단기예보 조회서비스 (getVilageFcst)", "source_url": SOURCE,
                    "warnings": {}}
            _cache[identifier] = (time.monotonic(), 600, deepcopy(data))
    return {"snapshot": data, "token": _sign(data, key)}
