"""KMA ultra-short forecast, isolated from scoring and existing weather CSV.

Only the server calls KMA. Signed snapshots survive serverless instance changes.
"""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
from threading import Lock
import time
from urllib.parse import urlencode, unquote
from urllib.request import urlopen

KST = timezone(timedelta(hours=9))
SOURCE = "https://www.data.go.kr/data/15084084/openapi.do"
ENDPOINT = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"
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
    # Official guide: hourly :30 issue is callable after :45 (KST).
    return (now.astimezone(KST) - timedelta(minutes=45)).replace(minute=30, second=0, microsecond=0)


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
    def number(code, low, high):
        try:
            v = float(values.get(code, ""))
            return v if math.isfinite(v) and low <= v <= high else None
        except ValueError:
            return None
    precipitation = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기", "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림"}.get(values.get("PTY"))
    sky = {"1": "맑음", "3": "구름많음", "4": "흐림"}.get(values.get("SKY"))
    rain = values.get("RN1")
    if rain in (None, "", "-999", "-998", "-999.0", "-998.0"):
        rain = None
    elif rain.replace(".", "", 1).isdigit():
        rain += " mm"
    data = {"region": location, "kind": "초단기예보", "temperature": number("T1H", -80, 60),
            "humidity": number("REH", 0, 100), "precipitation": precipitation, "rainfall": rain, "sky": sky,
            "base_at": base.isoformat(), "valid_at": valid.isoformat(), "fetched_at": now.isoformat(),
            "source": "기상청 단기예보 조회서비스", "source_url": SOURCE}
    if all(data[k] is None for k in ("temperature", "humidity", "precipitation", "rainfall", "sky")):
        raise WeatherError("기상청 응답에 표시 가능한 기상정보가 없습니다.")
    return data


def _sign(data, key):
    payload = base64.urlsafe_b64encode(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()).decode()
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def restore(token, identifier):
    """Accept only a server-issued snapshot for the selected region; no live lookup."""
    key = os.environ.get("KMA_SERVICE_KEY", "")
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
    key = os.environ.get("KMA_SERVICE_KEY", "")
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
            base = base_time(now)
            params = {"serviceKey": unquote(key), "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
                      "base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H%M"),
                      "nx": location["nx"], "ny": location["ny"]}
            try:
                with urlopen(ENDPOINT + "?" + urlencode(params), timeout=8) as response:
                    result = json.loads(response.read(2_000_000))["response"]
                if str(result["header"]["resultCode"]) != "00":
                    raise WeatherError("기상청에서 자료를 제공하지 못했습니다. 인증키·호출한도 또는 자료 발표시각을 확인하세요.")
                data = parse_items(result["body"]["items"]["item"], location, base, now)
            except Exception as error:
                # Never propagate upstream errors/URLs: they may contain the key.
                message = str(error) if isinstance(error, WeatherError) else "기상정보 조회에 실패했습니다. 잠시 후 다시 조회하세요. 평가는 계속할 수 있습니다."
                _cache[identifier] = (time.monotonic(), 30, message)
                raise WeatherError(message) from None
            _cache[identifier] = (time.monotonic(), 600, deepcopy(data))
    return {"snapshot": data, "token": _sign(data, key)}
