"""Zone draft and independent scoring checks: python -m unittest fire_risk_project.test_zone_assessment."""
import base64
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from .api import create_app
from . import risk_engine as engine, storage as evaluation_storage, evaluation_history


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jv4kAAAAASUVORK5CYII="


def answers_for(task_id):
    return {row["항목ID"]: row["선택지·허용값"].split("/")[0].strip() if row["입력형식"] == "선택" else 5
            for row in engine.get_questions_for_task(task_id).to_dict("records")}


class ZoneAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.db = Path(self.directory.name) / "records.sqlite3"
        self.client = TestClient(create_app(self.db))
        self.client.__enter__()
        self.site = str(uuid4())
        image = self.client.post(f"/api/sites/{self.site}/blueprints", json={
            "filename": "site.png", "media_type": "image/png", "data_base64": PNG}).json()["조감도"]
        self.image = image["이미지ID"]
        self.base = f"/api/sites/{self.site}/blueprints/{self.image}/zones"
        self.zones = []
        for index, name in enumerate(("A구역", "B구역", "C구역")):
            response = self.client.post(self.base, json={"name": name, "coordinates": {
                "x": index * 0.3, "y": 0.1, "width": 0.2, "height": 0.2}})
            self.assertEqual(response.status_code, 200, response.text)
            self.zones.append(response.json()["작업구역"]["작업구역ID"])

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def url(self, index):
        return f"{self.base}/{self.zones[index]}"

    def payload(self, task_id, **changes):
        answers = answers_for(task_id)
        answers.update(changes)
        return {"site_name": "테스트 현장", "task_id": task_id, "answers": answers,
                "materials": {"ids": [], "custom_names": [], "unknown": True},
                "watcher_answers": {"W001": "아니오", "W004": "아니오"} if task_id == "H05" else {}}

    def test_repeat_mitigation_first_repeat_cap_completion_and_recurrence(self):
        url = self.url(0) + "/evaluate"
        missed = self.payload("H05", Q003="미실시", Q004="미배치")
        completed = self.payload("H05", Q003="실시", Q004="배치")
        records = []
        for payload in (missed, missed, missed, completed, missed):
            response = self.client.post(url, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            records.append(response.json()["평가"])

        expected = ((1, 1), (2, 2), (2, 2), (0, 0), (1, 1))
        maximum = records[0]["요약"]["최대가중점수"]
        for record, (spark, watcher) in zip(records, expected):
            details = {row["항목ID"]: row for row in record["응답상세"]}
            self.assertEqual((details["Q003"]["점수"], details["Q004"]["점수"]), (spark, watcher))
            self.assertEqual((details["Q003"]["가중점수"], details["Q004"]["가중점수"]), (spark, watcher))
            self.assertEqual((details["Q003"]["최대가중점수"], details["Q004"]["최대가중점수"]), (2, 2))
            self.assertEqual(record["요약"]["최대가중점수"], maximum)
            total = sum(row["가중점수"] for row in record["응답상세"] if row["집계대표여부"])
            self.assertEqual(record["요약"]["총가중위험점수"], total)
            self.assertAlmostEqual(record["요약"]["위험지수"], total / maximum * 100)
            self.assertEqual(record["요약"]["반복미조치기준버전"], "구역반복-v1")
        self.assertEqual([record["이전구역평가ID"] for record in records],
                         [None] + [record["평가ID"] for record in records[:-1]])
        self.assertLess(records[3]["요약"]["위험지수"], records[2]["요약"]["위험지수"])
        baseline = engine.build_evaluation(missed["site_name"], "H05", missed["answers"], missed["watcher_answers"])
        self.assertNotIn("반복미조치기준버전", baseline["요약"])
        base_rows = {row["항목ID"]: row for row in baseline["응답상세"]}
        for row in records[0]["응답상세"]:
            if row["항목ID"] not in ("Q003", "Q004"):
                self.assertEqual(row["가중점수"], base_rows[row["항목ID"]]["가중점수"])
        saved_first = self.client.get(f"/api/zone-assessments/{records[0]['평가ID']}").json()["평가"]
        self.assertEqual(saved_first["응답상세"], records[0]["응답상세"])
        saved_repeat = self.client.get(f"/api/zone-assessments/{records[1]['평가ID']}").json()["평가"]
        self.assertEqual(saved_repeat["반복미조치판정"], records[1]["반복미조치판정"])
        history = self.client.get("/api/zone-assessments", params={"site_id": self.site}).json()["평가이력"]
        self.assertTrue({record["평가ID"] for record in records}.issubset({row["평가ID"] for row in history}))
        other_zone = self.client.post(self.url(1) + "/evaluate", json=missed).json()["평가"]
        other_details = {row["항목ID"]: row for row in other_zone["응답상세"]}
        self.assertEqual((other_details["Q003"]["점수"], other_details["Q004"]["점수"]), (1, 1))
        with self.assertRaisesRegex(ValueError, "직전 구역 평가가 변경"):
            evaluation_storage.save_zone_assessment(
                self.db, self.site, self.image, self.zones[0], baseline,
                expected_previous_id=records[0]["평가ID"],
            )
        old_version = deepcopy(records[0])
        old_version["요약"].pop("반복미조치기준버전")
        comparison = evaluation_history.compare(old_version, records[1])
        self.assertFalse(comparison["비교안내"]["점수차이표시가능"])
        self.assertIn("반복 미조치 기준 버전 불일치", comparison["비교안내"]["비교제한사유"])

    def test_repeat_mitigation_respects_watcher_exception_and_unknown(self):
        url = self.url(0) + "/evaluate"
        missed = self.payload("H05", Q003="미실시", Q004="미배치")
        first = self.client.post(url, json=missed).json()["평가"]
        claimed_exception = {**missed, "watcher_answers": {"W001": "아니오", "W004": "예"}}
        response = self.client.post(url, json=claimed_exception)
        self.assertEqual(response.status_code, 200, response.text)
        exception_record = response.json()["평가"]
        exception_rows = {row["항목ID"]: row for row in exception_record["응답상세"]}
        self.assertEqual(exception_rows["Q003"]["점수"], 2)
        self.assertIsNone(exception_rows["Q004"]["점수"])
        self.assertIsNone(exception_record["요약"]["위험지수"])
        self.assertEqual(exception_record["반복미조치판정"]["직전평가ID"], first["평가ID"])
        self.assertEqual(exception_record["반복미조치판정"]["항목"][1]["상태"],
                         "화재감시자 적용·예외조건 확인 필요")
        unknown = self.payload("H05", Q003="미실시", Q004="확인불가")
        response = self.client.post(url, json=unknown)
        self.assertEqual(response.status_code, 200, response.text)
        held = response.json()["평가"]
        held_row = next(row for row in held["응답상세"] if row["항목ID"] == "Q004")
        self.assertIsNone(held_row["점수"])
        self.assertIsNone(held["요약"]["위험지수"])
        not_target = self.payload("H05", Q001="없음", Q003="미실시", Q004="미배치",
                                  Q019="없음", Q020="없음")
        response = self.client.post(url, json=not_target)
        self.assertEqual(response.status_code, 200, response.text)
        not_target_record = response.json()["평가"]
        self.assertIsNone(next(row["점수"] for row in not_target_record["응답상세"]
                               if row["항목ID"] == "Q004"))
        self.assertIsNone(not_target_record["요약"]["위험지수"])

    def test_repeat_mitigation_tracks_each_question_independently(self):
        url = self.url(0) + "/evaluate"
        inputs = (self.payload("H05", Q003="미실시", Q004="배치"),
                  self.payload("H05", Q003="실시", Q004="미배치"),
                  self.payload("H05", Q003="미실시", Q004="미배치"))
        records = []
        for payload in inputs:
            response = self.client.post(url, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            records.append(response.json()["평가"])
        scores = [tuple(next(row["점수"] for row in record["응답상세"] if row["항목ID"] == qid)
                        for qid in ("Q003", "Q004")) for record in records]
        self.assertEqual(scores, [(1, 0), (0, 1), (1, 2)])

    def test_distinct_tasks_answers_results_and_legacy_score_parity(self):
        catalogue = self.client.get("/api/zone-tasks")
        self.assertEqual(catalogue.status_code, 200)
        ids = {task["task_id"] for task in catalogue.json()["tasks"]}
        self.assertTrue({"H05", "H08", "H11"}.issubset(ids))
        self.assertNotIn("H01", ids)
        first = self.payload("H05", Q002=3)
        second = self.payload("H08", Q002=7)
        for index, payload in enumerate((first, second)):
            saved = self.client.put(self.url(index) + "/assessment", json=payload)
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(saved.json()["입력상태"], "작성 중")
        self.assertEqual(self.client.get(self.url(0) + "/assessment").json()["초안"]["answers"]["Q002"], 3)
        self.assertEqual(self.client.get(self.url(1) + "/assessment").json()["초안"]["answers"]["Q002"], 7)
        for index, payload in enumerate((first, second)):
            result = self.client.post(self.url(index) + "/evaluate", json=payload)
            self.assertEqual(result.status_code, 200, result.text)
            record = result.json()["평가"]
            self.assertEqual(record["요약"]["위험지수"], engine.calculate_task_risk(payload["task_id"], payload["answers"])[0]["위험지수"])
            self.assertEqual(record["작업구역ID"], self.zones[index])
            self.assertEqual(record["현장ID"], self.site)
            self.assertEqual(record["작업ID"], payload["task_id"])
            self.assertIn("계산데이터SHA256", record)
            self.assertIn("근거스냅샷", record)
            self.assertEqual(self.client.get(self.url(index) + "/assessment").json()["입력상태"], "완료")
        self.assertEqual(self.client.get("/api/dashboard").json()["count"], 0)
        self.assertEqual(self.client.get("/api/evaluations").json(), [])
        history = self.client.get("/api/zone-assessments", params={"site_id": self.site}).json()["\uD3C9\uAC00\uC774\uB825"]
        self.assertEqual({row["\uC791\uC5C5\uAD6C\uC5EDID"] for row in history}, set(self.zones[:2]))
        for record in (record for record in history if record["\uC791\uC5C5\uAD6C\uC5EDID"] in self.zones[:2]):
            detail = self.client.get(f"/api/zone-assessments/{record['\uD3C9\uAC00ID']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(record["\uACC4\uC0B0\uAE30\uC900"], [detail.json()["\uD3C9\uAC00"]["\uACC4\uC0B0\uB370\uC774\uD130SHA256"],
                                                                          detail.json()["\uD3C9\uAC00"]["\uC5D4\uC9C4SHA256"],
                                                                          detail.json()["\uD3C9\uAC00"]["\uC694\uC57D"]["\uCD5C\uB300\uAC00\uC911\uC810\uC218"]])
            self.assertEqual(detail.json()["\uD3C9\uAC00"]["\uC694\uC57D"]["\uC704\uD5D8\uC9C0\uC218"], record["\uC704\uD5D8\uC9C0\uC218"])
        self.assertNotEqual(first["answers"]["Q002"], second["answers"]["Q002"])

    def test_legacy_single_task_records_remain_readable(self):
        body = self.payload("H05")
        response = self.client.post("/api/evaluate", json={
            "site_id": self.site, "blueprint_image_id": self.image, "site_name": body["site_name"],
            "task_id": body["task_id"], "answers": body["answers"], "materials": body["materials"],
            "watcher_answers": body["watcher_answers"], "watcher_ui_version": "integrated-v1",
        })
        self.assertEqual(response.status_code, 200, response.text)
        legacy = response.json()
        rows = self.client.get("/api/evaluations").json()
        self.assertTrue(any(row["\uD3C9\uAC00ID"] == legacy["\uD3C9\uAC00ID"] for row in rows))
        loaded = self.client.get(f"/api/evaluations/{legacy['\uD3C9\uAC00ID']}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["\uC694\uC57D"]["\uC704\uD5D8\uC9C0\uC218"], legacy["\uC694\uC57D"]["\uC704\uD5D8\uC9C0\uC218"])

    def test_draft_switch_recalculation_versions_and_reload(self):
        first = self.payload("H05", Q002=3)
        url = self.url(0)
        self.assertEqual(self.client.put(url + "/assessment", json=first).status_code, 200)
        original = self.client.post(url + "/evaluate", json=first).json()["평가"]
        changed = self.payload("H05", Q002=7)
        update = self.client.put(url + "/assessment", json=changed)
        self.assertEqual(update.json()["입력상태"], "재계산 필요")
        self.assertEqual(self.client.get(url + "/assessment").json()["최근평가"]["평가ID"], original["평가ID"])
        with TestClient(create_app(self.db)) as restarted:
            record = restarted.get(url + "/assessment").json()
        self.assertEqual(record["입력상태"], "재계산 필요")
        self.assertEqual(record["초안"]["answers"]["Q002"], 7)
        newer = self.client.post(url + "/evaluate", json=changed).json()["평가"]
        self.assertNotEqual(newer["평가ID"], original["평가ID"])
        self.assertEqual(newer["이전구역평가ID"], original["평가ID"])
        self.assertEqual(self.client.get(url + "/assessment").json()["입력상태"], "완료")
        versions = self.client.get(url + "/assessments").json()["평가버전"]
        self.assertEqual([item["평가ID"] for item in versions], [newer["평가ID"], original["평가ID"]])
        self.assertEqual(self.client.get(url + "/assessments/" + original["평가ID"]).json()["평가"]["응답"]["Q002"], 3)
        self.assertEqual(self.client.get(self.url(1) + "/assessments/" + original["평가ID"]).status_code, 404)
        self.assertEqual(self.client.get(self.url(1) + "/assessment").json()["입력상태"], "미작성")

    def test_task_change_questions_and_image_scope(self):
        first = self.payload("H05")
        self.assertEqual(self.client.put(self.url(2) + "/assessment", json=first).status_code, 200)
        changed = self.payload("H11")
        schema = self.client.post("/api/zone-questions", json={key: changed[key] for key in ("task_id", "answers", "watcher_answers")})
        self.assertEqual(schema.status_code, 200, schema.text)
        self.assertEqual(schema.json()["watcher_questions"], [])
        self.assertEqual(self.client.put(self.url(2) + "/assessment", json=changed).status_code, 200)
        self.assertEqual(self.client.get(self.url(2) + "/assessment").json()["초안"]["task_id"], "H11")
        self.assertEqual(self.client.get(self.url(0) + "/assessment").json()["입력상태"], "미작성")
        self.assertEqual(self.client.get(self.url(1) + "/assessment").json()["입력상태"], "미작성")
        self.assertEqual(self.client.post("/api/zone-questions", json={"task_id": "invented", "answers": {}}).status_code, 422)
        image = self.client.post(f"/api/sites/{self.site}/blueprints", json={
            "filename": "replacement.png", "media_type": "image/png", "data_base64": PNG}).json()["조감도"]
        wrong = f"/api/sites/{self.site}/blueprints/{image['이미지ID']}/zones/{self.zones[2]}/assessment"
        self.assertEqual(self.client.get(wrong).status_code, 404)
        self.assertEqual(self.client.get(self.url(2) + "/assessment").json()["초안"]["task_id"], "H11")

    def test_watcher_unknown_holds_score_and_private_access(self):
        body = self.payload("H05")
        body["answers"]["Q004"] = "확인불가"
        response = self.client.post(self.url(0) + "/evaluate", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["평가"]["화재위험지수"])
        self.assertEqual(response.json()["평가"]["위험수준"], "확인필요")
        self.assertEqual(self.client.get(self.url(0) + "/assessment").status_code, 200)


if __name__ == "__main__":
    unittest.main()
