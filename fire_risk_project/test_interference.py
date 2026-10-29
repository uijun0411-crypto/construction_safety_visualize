"""Run with python -m unittest fire_risk_project.test_interference."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from . import interference, risk_engine as engine, storage, zone_relations
from .api import create_app
from .test_zone_relations import PNG, rect
from .test_zone_assessment import answers_for


class InterferenceLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine.load_databases()

    def pair(self, task_a="H05", task_b="H10", answers_a=None, answers_b=None,
             materials_b=None, schedule_b=None, geometry_b=None, confirmation=None):
        zones = [{"zone_id": "a", **rect(0, 0, .2, .2)},
                 {"zone_id": "b", **(geometry_b or rect(.4, 0, .2, .2))}]
        schedules = {"a": {"시작일시": "2026-10-29T09:00", "종료일시": "2026-10-29T12:00"},
                     "b": schedule_b if schedule_b is not None else {"시작일시": "2026-10-29T10:00", "종료일시": "2026-10-29T13:00"}}
        inputs = {"a": {"task_id": task_a, "answers": answers_a or {"Q001": "없음"}},
                  "b": {"task_id": task_b, "answers": answers_b or {"Q007": "사용"},
                        "materials": materials_b if materials_b is not None else {"ids": ["M008"]}}}
        relations = zone_relations.compare_zones(zones, schedules)
        confirmed = {("a", "b"): confirmation} if confirmation else {}
        return interference.analyze_pairs(relations, zones, inputs, confirmed)[0]

    def test_welding_and_confirmed_flammable_material(self):
        pending = self.pair()
        self.assertEqual(pending["분석상태"], "추가 확인 필요")
        self.assertIn("실제 구역 간 인접 여부 및 거리", pending["추가확인필요사항"])
        self.assertEqual(pending["기존DB근거"]["MSDS"][0]["물질ID"], "M008")
        with_ventilation = self.pair(answers_b={"Q007": "사용", "Q008": "양호"})
        self.assertNotIn("환기상태", with_ventilation["추가확인필요사항"])
        found = self.pair(confirmation={"actual_adjacent": True, "spark_reaches": True,
                                        "vapor_reaches": False, "barrier": "없음", "ventilation": "양호"})
        self.assertEqual(found["분석상태"], "동시작업 위험요인 발견")
        self.assertEqual(len(found["확인된위험요인"]), 1)

    def test_nonflammable_or_unused_material_is_not_confirmed_risk(self):
        result = self.pair(answers_b={"Q007": "미사용"}, materials_b={"ids": []})
        self.assertEqual(result["분석상태"], "확인된 간섭 위험요인 없음")

    def test_no_time_overlap_and_missing_location(self):
        no_overlap = self.pair(schedule_b={"시작일시": "2026-10-29T13:00", "종료일시": "2026-10-29T16:00"})
        self.assertEqual(no_overlap["분석상태"], "작업시간 중복 없음")
        self.assertIn("잔류 열원·인화성 증기 등 작업 전후 영향 여부", no_overlap["추가확인필요사항"])
        missing_position = self.pair(geometry_b={"geometry_type": "rectangle", "coordinates": None})
        self.assertEqual(missing_position["분석상태"], "추가 확인 필요")
        self.assertEqual(missing_position["조감도상영역관계"], "위치정보 확인 필요")

    def test_unknown_material_and_updated_answers(self):
        unknown = self.pair(materials_b={"ids": [], "unknown": True})
        self.assertEqual(unknown["분석상태"], "추가 확인 필요")
        unanswered = self.pair(answers_b={"Q008": "양호"}, materials_b={"ids": []})
        self.assertEqual(unanswered["분석상태"], "추가 확인 필요")
        changed = self.pair(answers_b={"Q007": "미사용"}, materials_b={"ids": []})
        self.assertEqual(changed["분석상태"], "확인된 간섭 위험요인 없음")
        changed_task = self.pair(task_b="H05", answers_b={"Q001": "없음"}, materials_b={"ids": []})
        self.assertEqual(changed_task["분석상태"], "확인된 간섭 위험요인 없음")

    def test_multiple_pairs(self):
        zones = [{"zone_id": str(i), **rect(i * .3, 0, .2, .2)} for i in range(3)]
        schedules = {zone["zone_id"]: {"시작일시": "2026-10-29T09:00", "종료일시": "2026-10-29T12:00"} for zone in zones}
        relations = zone_relations.compare_zones(zones, schedules)
        inputs = {zone["zone_id"]: {"task_id": "H05", "answers": {"Q001": "없음"}} for zone in zones}
        results = interference.analyze_pairs(relations, zones, inputs)
        self.assertEqual(len(results), 3)
        self.assertEqual(len({(r["작업구역ID_A"], r["작업구역ID_B"]) for r in results}), 3)


class InterferenceApiTests(unittest.TestCase):
    def test_saved_inputs_are_read_and_confirmation_changes_status(self):
        with TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / "data.sqlite")) as client:
                site = str(uuid4())
                image_response = client.post(f"/api/sites/{site}/blueprints", json={"filename": "site.png", "media_type": "image/png", "data_base64": PNG})
                self.assertEqual(image_response.status_code, 200, image_response.text)
                image = image_response.json()["조감도"]["이미지ID"]
                base = f"/api/sites/{site}/blueprints/{image}"
                ids = []
                for name, x in (("A", 0), ("B", .4)):
                    response = client.post(base + "/zones", json={"name": name, "coordinates": {"x": x, "y": 0, "width": .2, "height": .2}})
                    self.assertEqual(response.status_code, 200, response.text)
                    ids.append(response.json()["작업구역"]["작업구역ID"])
                for zid, start, end in ((ids[0], "09:00", "12:00"), (ids[1], "10:00", "13:00")):
                    self.assertEqual(client.put(f"{base}/zones/{zid}/schedule", json={"start_at": f"2026-10-29T{start}", "end_at": f"2026-10-29T{end}"}).status_code, 200)
                # The assessment draft API already validates these existing task answers.
                for zid, task, answers, material in ((ids[0], "H05", {"Q001": "없음"}, []),
                                                     (ids[1], "H10", {"Q007": "사용"}, ["M008"])):
                    response = client.put(f"{base}/zones/{zid}/assessment", json={
                        "site_name": "현장", "task_id": task, "answers": answers,
                        "materials": {"ids": material, "custom_names": [], "unknown": False}})
                    self.assertEqual(response.status_code, 200, response.text)
                pending = client.get(base + "/zone-interference")
                self.assertEqual(pending.status_code, 200, pending.text)
                self.assertEqual(pending.json()["동시작업분석"][0]["분석상태"], "추가 확인 필요")
                reviewed = client.post(base + "/zone-interference", json={"confirmations": [{
                    "zone_id_a": ids[1], "zone_id_b": ids[0], "actual_adjacent": True,
                    "spark_reaches": True, "vapor_reaches": False, "barrier": "없음", "ventilation": "양호"}]})
                self.assertEqual(reviewed.status_code, 200, reviewed.text)
                self.assertEqual(reviewed.json()["동시작업분석"][0]["분석상태"], "동시작업 위험요인 발견")
                self.assertEqual(client.get(base + "/zone-interference").json()["동시작업분석"][0]["분석상태"], "동시작업 위험요인 발견")

                hot_answers = answers_for("H08")
                hot_answers["Q001"] = "없음"
                evaluated = client.post(f"{base}/zones/{ids[0]}/evaluate", json={
                    "site_name": "현장", "task_id": "H08", "answers": hot_answers,
                    "materials": {"ids": [], "custom_names": [], "unknown": False}})
                self.assertEqual(evaluated.status_code, 200, evaluated.text)
                record = evaluated.json()["평가"]
                self.assertEqual(record["작업시간"]["시작일시"], "2026-10-29T09:00")
                self.assertEqual(record["동시작업분석"][0]["작업시간"]["중복시간_분"], 120)
                self.assertEqual(record["동시작업분석"][0]["분석상태"], "동시작업 위험요인 발견")
                self.assertEqual(record["요약"]["위험지수"], engine.calculate_task_risk("H08", hot_answers)[0]["위험지수"])

                self.assertEqual(client.put(f"{base}/zones/{ids[1]}/schedule", json={
                    "start_at": "2026-10-29T13:00", "end_at": "2026-10-29T16:00"}).status_code, 200)
                history = client.get(f"/api/zone-assessments/{record['평가ID']}")
                self.assertEqual(history.status_code, 200, history.text)
                saved = history.json()["평가"]
                self.assertEqual(saved["동시작업분석"][0]["작업시간"]["중복시간_분"], 120)
                self.assertEqual(saved["동시작업분석"][0]["작업시간"]["구역별"][ids[1]]["시작일시"], "2026-10-29T10:00")
                old_record = {key: value for key, value in saved.items() if key not in ("동시작업분석", "동시작업분석기준버전", "작업시간")}
                old_record["평가ID"] = str(uuid4())
                storage.save_zone_assessment(Path(directory) / "data.sqlite", site, image, ids[0], old_record)
                old_history = client.get(f"/api/zone-assessments/{old_record['평가ID']}")
                self.assertEqual(old_history.status_code, 200, old_history.text)
                self.assertNotIn("동시작업분석", old_history.json()["평가"])
                current = client.get(base + "/zone-interference").json()["동시작업분석"]
                self.assertEqual(current[0]["분석상태"], "작업시간 중복 없음")


if __name__ == "__main__":
    unittest.main()
