"""Pairwise schedule and blueprint geometry relationships for work zones."""
from datetime import datetime
from itertools import combinations
from math import isfinite

EPS = 1e-10


def _time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is None else None
    except ValueError:
        return None


def time_relation(first, second):
    a_start, a_end = (_time(first.get(key)) for key in ("시작일시", "종료일시"))
    b_start, b_end = (_time(second.get(key)) for key in ("시작일시", "종료일시"))
    result = {"작업시간중복": None, "시간관계": "시간정보 확인 필요", "중복시작일시": None,
              "중복종료일시": None, "중복시간_분": None}
    if not all((a_start, a_end, b_start, b_end)) or a_start >= a_end or b_start >= b_end:
        return result
    start, end = max(a_start, b_start), min(a_end, b_end)
    if start > end:
        return {**result, "작업시간중복": False, "시간관계": "작업시간 중복 없음", "중복시간_분": 0}
    minutes = (end - start).total_seconds() / 60
    return {**result, "작업시간중복": minutes > 0,
            "시간관계": "작업시간 중복" if minutes > 0 else "경계시각 일치",
            "중복시작일시": start.isoformat(timespec="minutes"),
            "중복종료일시": end.isoformat(timespec="minutes"), "중복시간_분": minutes}


def _point(value):
    if isinstance(value, dict):
        x, y = value.get("x"), value.get("y")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        x, y = value
    else:
        return None
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return (float(x), float(y)) if isfinite(x) and isfinite(y) else None


def polygon(zone):
    coordinates = zone.get("coordinates")
    kind = zone.get("geometry_type")
    if kind in ("rectangle", "사각형") and isinstance(coordinates, dict):
        try:
            x, y, w, h = (coordinates[name] for name in ("x", "y", "width", "height"))
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
                return None
            return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        except KeyError:
            return None
    if kind in ("polygon", "다각형"):
        raw = coordinates.get("points") if isinstance(coordinates, dict) else coordinates
        if not isinstance(raw, list) or len(raw) < 3:
            return None
        points = [_point(item) for item in raw]
        if any(point is None for point in points):
            return None
        if points[0] == points[-1]:
            points.pop()
        area2 = sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))
        return points if len(points) >= 3 and abs(area2) > EPS else None
    return None


def _edges(points):
    return list(zip(points, points[1:] + points[:1]))


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _touch(a, b, c, d):
    o1, o2, o3, o4 = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if o1 * o2 < -EPS and o3 * o4 < -EPS:
        return True
    for p, u, v, orientation in ((c, a, b, o1), (d, a, b, o2), (a, c, d, o3), (b, c, d, o4)):
        if abs(orientation) <= EPS and min(u[0], v[0]) - EPS <= p[0] <= max(u[0], v[0]) + EPS and min(u[1], v[1]) - EPS <= p[1] <= max(u[1], v[1]) + EPS:
            return True
    return False


def _interior_intervals(points, x):
    crossings = []
    for a, b in _edges(points):
        if min(a[0], b[0]) < x < max(a[0], b[0]):
            crossings.append(a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0]))
    crossings.sort()
    return list(zip(crossings[::2], crossings[1::2]))


def geometry_relation(first, second):
    a, b = polygon(first), polygon(second)
    if a is None or b is None:
        return "위치정보 확인 필요"
    a_edges, b_edges = _edges(a), _edges(b)
    xs = sorted({p[0] for p in a + b})
    for edge_a in a_edges:
        for edge_b in b_edges:
            p, q = edge_a
            r, s = edge_b
            denominator = (q[0] - p[0]) * (s[1] - r[1]) - (q[1] - p[1]) * (s[0] - r[0])
            if abs(denominator) > EPS:
                t = ((r[0] - p[0]) * (s[1] - r[1]) - (r[1] - p[1]) * (s[0] - r[0])) / denominator
                u = ((r[0] - p[0]) * (q[1] - p[1]) - (r[1] - p[1]) * (q[0] - p[0])) / denominator
                if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
                    xs.append(p[0] + t * (q[0] - p[0]))
    xs = sorted(set(xs))
    for left, right in zip(xs, xs[1:]):
        if right - left <= EPS:
            continue
        intervals_a = _interior_intervals(a, (left + right) / 2)
        intervals_b = _interior_intervals(b, (left + right) / 2)
        if any(min(ay2, by2) - max(ay1, by1) > EPS for ay1, ay2 in intervals_a for by1, by2 in intervals_b):
            return "겹침"
    if any(_touch(*edge_a, *edge_b) for edge_a in a_edges for edge_b in b_edges):
        return "경계 접함"
    return "분리"


def compare_zones(zones, schedules):
    """Compare each unordered pair once; zone IDs are the identity."""
    results = []
    for first, second in combinations(sorted(zones, key=lambda zone: zone["zone_id"]), 2):
        first_id, second_id = first["zone_id"], second["zone_id"]
        time = time_relation(schedules.get(first_id) or {}, schedules.get(second_id) or {})
        relation = geometry_relation(first, second)
        results.append({"작업구역ID_A": first_id, "작업구역ID_B": second_id, **time,
                        "조감도상영역관계": relation,
                        "시간정보확인필요": time["작업시간중복"] is None,
                        "위치정보확인필요": relation == "위치정보 확인 필요"})
    return results
