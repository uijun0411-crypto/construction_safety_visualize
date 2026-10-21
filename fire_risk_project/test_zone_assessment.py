"""Zone draft and independent scoring checks: python -m unittest fire_risk_project.test_zone_assessment."""
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from .api import create_app
from . import risk_engine as engine


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jv4kAAAAASUVORK5CYII="


def answers_for(task_id):
    return {row["항목ID"]: row["선택지·허용값"].split("/")[0].strip() if row["입력형식"] == "선택" else 5
            for row in engine.get_questions_for_task(task_id).to_dict("records")}


class ZoneAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.db = Path(self.directory.name) / "records.sqlite3"
        self.client = TestClient(create_app(self.db, access_key="test-key"))
        self.client.__enter__()
        self.client.headers["X-Access-Key"] = "test-key"
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

    def test_draft_switch_recalculation_versions_and_reload(self):
        first = self.payload("H05", Q002=3)
        url = self.url(0)
        self.assertEqual(self.client.put(url + "/assessment", json=first).status_code, 200)
        original = self.client.post(url + "/evaluate", json=first).json()["평가"]
        changed = self.payload("H05", Q002=7)
        update = self.client.put(url + "/assessment", json=changed)
        self.assertEqual(update.json()["입력상태"], "재계산 필요")
        self.assertEqual(self.client.get(url + "/assessment").json()["최근평가"]["평가ID"], original["평가ID"])
        with TestClient(create_app(self.db, access_key="test-key")) as restarted:
            record = restarted.get(url + "/assessment", headers={"X-Access-Key": "test-key"}).json()
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
        self.assertEqual(self.client.get(self.url(0) + "/assessment", headers={"X-Access-Key": "wrong"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
