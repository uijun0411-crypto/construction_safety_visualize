"""Run: python -m unittest fire_risk_project.test_api -v"""
from pathlib import Path
from contextlib import closing
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from .api import create_app
from . import risk_engine as engine


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.storage = Path(self.directory.name) / "records.sqlite3"
        self.client = TestClient(create_app(self.storage, access_key="test-key"))
        self.client.__enter__()
        self.client.headers["X-Access-Key"] = "test-key"
        answers = {}
        for row in engine.get_questions_for_task("H05").to_dict("records"):
            answers[row["항목ID"]] = row["선택지·허용값"].split("/")[0].strip() if row["입력형식"] == "선택" else 5
        self.body = {"site_name": "테스트 현장", "answers": answers,
                     "watcher_answers": {f"W00{i}": "아니오" for i in range(1, 5)}}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def evaluate(self, body=None):
        response = self.client.post("/api/evaluate", json=body or self.body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_save_read_restart_and_idempotency(self):
        record = self.evaluate()
        self.assertEqual(self.client.get("/api/evaluations").json(), [])
        identifier = record["평가ID"]
        # Client-supplied result fields cannot change the server's draft.
        response = self.client.post(f"/api/evaluations/{identifier}/save", json={"요약": {"위험지수": 999}})
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.client.get(f"/api/evaluations/{identifier}").json()
        self.assertEqual(saved, record)
        self.assertEqual(self.client.post(f"/api/evaluations/{identifier}/save").json()["저장상태"], "이미 저장됨")
        with TestClient(create_app(self.storage, access_key="test-key")) as restarted:
            self.assertEqual(restarted.get(f"/api/evaluations/{identifier}", headers={"X-Access-Key": "test-key"}).json(), record)
        self.assertEqual(len(self.client.get("/api/evaluations?site_keyword=테스트").json()), 1)
        self.assertEqual(self.client.get("/api/dashboard").json()["count"], 1)
        self.assertEqual(self.client.get("/api/dashboard?site=없는현장").json()["count"], 0)

    def test_engine_parity_and_conditional_questions(self):
        self.body["answers"]["Q001"] = "없음"
        questions = self.client.post("/api/questions", json={"answers": self.body["answers"]}).json()["questions"]
        self.assertEqual(next(q for q in questions if q["항목ID"] == "Q002")["적용상태"], "조건제외")
        record = self.evaluate()
        active = {q["항목ID"] for q in questions if q["적용상태"] == "적용"}
        expected = engine.build_evaluation(self.body["site_name"], "H05",
                                          {k: v for k, v in self.body["answers"].items() if k in active},
                                          self.body["watcher_answers"])
        self.assertEqual(record["요약"], expected["요약"])
        self.assertEqual(record["응답상세"], expected["응답상세"])

    def test_invalid_input_and_na_hold(self):
        for qid in ("Q003", "Q004"):
            body = {**self.body, "answers": {**self.body["answers"], qid: "해당없음"}}
            self.assertEqual(self.client.post("/api/evaluate", json=body).status_code, 422)
        for answers in ({}, {"Q999": 1}, {"Q001": True}, {"Q002": -1}, {"Q001": [1]}):
            self.assertEqual(self.client.post("/api/evaluate", json={**self.body, "answers": answers}).status_code, 422)
        self.assertEqual(self.client.post("/api/evaluate", json={**self.body, "site_name": " "}).status_code, 422)

    def test_authorization_cors_and_missing_record(self):
        del self.client.headers["X-Access-Key"]
        self.assertEqual(self.client.get("/api/evaluations").status_code, 401)
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.client.headers["X-Access-Key"] = "test-key"
        headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-access-key"}
        self.assertEqual(self.client.options("/api/evaluate", headers=headers).status_code, 200)
        self.assertEqual(self.client.options("/api/evaluate", headers={**headers, "Origin": "https://untrusted.example"}).status_code, 400)
        self.assertEqual(self.client.get("/api/evaluations/missing").status_code, 404)
        self.assertEqual(self.client.post("/api/evaluations/missing/save").status_code, 404)

    def test_comparison_and_expired_draft(self):
        before = self.evaluate()
        self.client.post(f"/api/evaluations/{before['평가ID']}/save")
        self.body["answers"]["Q002"] = 15
        after = self.evaluate()
        self.client.post(f"/api/evaluations/{after['평가ID']}/save")
        compared = self.client.post("/api/compare", json={"before_id": before["평가ID"], "after_id": after["평가ID"]})
        self.assertEqual(compared.status_code, 200, compared.text)
        self.assertTrue(compared.json()["비교안내"]["점수차이표시가능"])
        self.assertTrue(compared.json()["변경항목"])
        self.assertEqual(self.client.post("/api/compare", json={"before_id": before["평가ID"], "after_id": before["평가ID"]}).status_code, 422)
        draft = self.evaluate()
        with closing(sqlite3.connect(self.storage)) as conn, conn:
            conn.execute("UPDATE evaluation_drafts SET created_at = 0")
        self.assertEqual(self.client.post(f"/api/evaluations/{draft['평가ID']}/save").status_code, 404)


if __name__ == "__main__":
    unittest.main()
