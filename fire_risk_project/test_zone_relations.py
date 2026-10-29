"""Run with python -m unittest fire_risk_project.test_zone_relations."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from .api import create_app
from . import storage, zone_relations


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jv4kAAAAASUVORK5CYII="


def rect(x, y, width, height):
    return {"geometry_type": "rectangle", "coordinates": {"x": x, "y": y, "width": width, "height": height}}


def poly(points):
    return {"geometry_type": "polygon", "coordinates": {"points": points}}


class RelationCalculationTests(unittest.TestCase):
    def schedule(self, a_start, a_end, b_start, b_end):
        return zone_relations.time_relation({"시작일시": a_start, "종료일시": a_end},
                                            {"시작일시": b_start, "종료일시": b_end})

    def test_time_cases(self):
        self.assertEqual(self.schedule("2026-10-29T09:00", "2026-10-29T12:00", "2026-10-29T10:00", "2026-10-29T13:00")["중복시간_분"], 120)
        self.assertEqual(self.schedule("2026-10-29T09:00", "2026-10-29T12:00", "2026-10-29T13:00", "2026-10-29T16:00")["시간관계"], "작업시간 중복 없음")
        boundary = self.schedule("2026-10-29T09:00", "2026-10-29T12:00", "2026-10-29T12:00", "2026-10-29T15:00")
        self.assertEqual((boundary["작업시간중복"], boundary["중복시간_분"]), (False, 0))
        self.assertEqual(self.schedule("2026-10-29T22:00", "2026-10-30T03:00", "2026-10-30T01:00", "2026-10-30T05:00")["중복시간_분"], 120)
        self.assertEqual(self.schedule("2026-10-29T09:00", "2026-10-29T12:00", "2026-10-30T09:00", "2026-10-30T12:00")["시간관계"], "작업시간 중복 없음")
        self.assertEqual(self.schedule("2026-10-29T09:00", "2026-10-31T12:00", "2026-10-30T10:00", "2026-10-30T11:00")["중복시간_분"], 60)
        self.assertEqual(self.schedule("2026-10-29T09:00", "2026-10-29T12:00", "2026-10-29T09:00", "2026-10-29T12:00")["중복시간_분"], 180)
        self.assertIsNone(zone_relations.time_relation({}, {"시작일시": "2026-10-29T09:00"})["작업시간중복"])

    def test_actual_areas_and_boundaries(self):
        self.assertEqual(zone_relations.geometry_relation(rect(0, 0, .5, .5), rect(.25, .25, .5, .5)), "겹침")
        self.assertEqual(zone_relations.geometry_relation(rect(0, 0, .5, .5), rect(.5, 0, .5, .5)), "경계 접함")
        self.assertEqual(zone_relations.geometry_relation(rect(0, 0, .5, .5), rect(.7, .7, .2, .2)), "분리")
        concave = poly([[0, 0], [1, 0], [1, .2], [.2, .2], [.2, 1], [0, 1]])
        self.assertEqual(zone_relations.geometry_relation(concave, rect(.4, .4, .2, .2)), "분리")
        self.assertEqual(zone_relations.geometry_relation(concave, rect(.1, .1, .2, .2)), "겹침")
        self.assertEqual(zone_relations.geometry_relation(concave, rect(.2, .4, .2, .2)), "경계 접함")
        vertical = poly([[.4, 0], [.6, 0], [.6, 1], [.4, 1]])
        horizontal = poly([[0, .4], [1, .4], [1, .6], [0, .6]])
        self.assertEqual(zone_relations.geometry_relation(vertical, horizontal), "겹침")
        self.assertEqual(zone_relations.geometry_relation(poly([[0, 0], [.2, 0], [.2, .2], [0, .2]]),
                                                          poly([[.2, .2], [.4, .2], [.4, .4], [.2, .4]])), "경계 접함")
        self.assertEqual(zone_relations.geometry_relation(rect(0, 0, .3, .3), {}), "위치정보 확인 필요")

    def test_three_zones_once_by_id(self):
        zones = [{"zone_id": str(i), **rect(i * .2, 0, .1, .1)} for i in range(3)]
        pairs = zone_relations.compare_zones(zones, {})
        self.assertEqual(len(pairs), 3)
        self.assertEqual({(p["작업구역ID_A"], p["작업구역ID_B"]) for p in pairs}, {("0", "1"), ("0", "2"), ("1", "2")})
        self.assertTrue(all(p["시간정보확인필요"] for p in pairs))


class RelationApiTests(unittest.TestCase):
    def test_saved_schedule_and_zone_edit_appear_in_analysis(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "records.sqlite3"
            with TestClient(create_app(db)) as client:
                site = str(uuid4())
                uploaded = client.post(f"/api/sites/{site}/blueprints", json={"filename": "site.png", "media_type": "image/png", "data_base64": PNG})
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                image = uploaded.json()["조감도"]["이미지ID"]
                base = f"/api/sites/{site}/blueprints/{image}"
                zones = []
                for name, x in (("A", 0), ("B", .4), ("C", .8)):
                    response = client.post(base + "/zones", json={"name": name, "coordinates": {"x": x, "y": 0, "width": .2, "height": .2}})
                    self.assertEqual(response.status_code, 200, response.text)
                    zones.append(response.json()["작업구역"]["작업구역ID"])
                for zid, start, end in ((zones[0], "2026-10-29T09:00", "2026-10-29T12:00"),
                                        (zones[1], "2026-10-29T10:00", "2026-10-29T13:00")):
                    response = client.put(f"{base}/zones/{zid}/schedule", json={"start_at": start, "end_at": end})
                    self.assertEqual(response.status_code, 200, response.text)
                result = client.get(base + "/zone-relations")
                self.assertEqual(result.status_code, 200, result.text)
                pairs = result.json()["구역쌍분석"]
                self.assertEqual(len(pairs), 3)
                pair = next(item for item in pairs if {item["작업구역ID_A"], item["작업구역ID_B"]} == set(zones[:2]))
                self.assertEqual(pair["중복시간_분"], 120)
                self.assertEqual(pair["조감도상영역관계"], "분리")
                self.assertTrue(any(item["시간정보확인필요"] for item in pairs))
                edited = client.put(f"{base}/zones/{zones[1]}", json={"name": "B", "coordinates": {"x": .2, "y": 0, "width": .2, "height": .2}})
                self.assertEqual(edited.status_code, 200, edited.text)
                updated = client.get(base + "/zone-relations").json()["구역쌍분석"]
                changed = next(item for item in updated if {item["작업구역ID_A"], item["작업구역ID_B"]} == set(zones[:2]))
                self.assertEqual(changed["조감도상영역관계"], "경계 접함")


if __name__ == "__main__":
    unittest.main()
