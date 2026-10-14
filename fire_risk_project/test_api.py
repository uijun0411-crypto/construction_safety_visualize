"""Run: python -m unittest fire_risk_project.test_api -v"""
from pathlib import Path
from contextlib import closing
import os
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from copy import deepcopy
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from .api import create_app
from . import risk_engine as engine
from . import storage as evaluation_storage


class StorageConfigurationTests(unittest.TestCase):
    def test_vercel_requires_persistent_postgres(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": ""}):
            with self.assertRaisesRegex(evaluation_storage.StorageError, "persistent Postgres"):
                evaluation_storage.configured_storage()
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "postgresql://db.example/app"}):
            self.assertEqual(evaluation_storage.configured_storage(), "postgresql://db.example/app")


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
        self.assertEqual(len(self.client.get("/api/evaluations").json()), 1)
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

    def test_watcher_reuses_current_q_responses(self):
        schema = self.client.post("/api/questions", json={"answers": {}}).json()
        self.assertEqual([r["추가질문ID"] for r in schema["watcher_questions"]], ["W001", "W004"])
        for value, expected in (("있음", "예"), ("없음", "아니오"), ("확인불가", "확인불가")):
            self.body["answers"].update(Q019=value, Q020=value)
            self.body["watcher_answers"].update(W001="예", W002="아니오", W003="아니오", W004="예")
            record = self.evaluate()
            responses = {r["추가질문ID"]: r["응답"] for r in record["화재감시자응답"]}
            self.assertEqual(responses, {"W001": "예", "W002": expected, "W003": expected, "W004": "예"})

    def test_comparison_exclusion_is_not_zero(self):
        self.body["answers"].update(Q001="있음", Q002=5)
        before = self.evaluate()
        self.client.post(f"/api/evaluations/{before['평가ID']}/save")
        self.body["answers"]["Q001"] = "없음"
        after = self.evaluate()
        self.client.post(f"/api/evaluations/{after['평가ID']}/save")
        result = self.client.post("/api/compare", json={"before_id": before["평가ID"], "after_id": after["평가ID"]}).json()
        distance = next(r for r in result["변경항목"] if r["항목ID"] == "Q002")
        self.assertGreater(distance["이전_가중점수"], 0)
        self.assertEqual(distance["이후_적용상태"], "조건제외")
        self.assertIsNone(distance["이후_가중점수"])

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
        draft = engine.build_evaluation('만료 초안', 'H05', self.body['answers'], self.body['watcher_answers'])
        from . import storage
        storage.save_draft(self.storage, draft)
        with closing(sqlite3.connect(self.storage)) as conn, conn:
            conn.execute("UPDATE evaluation_drafts SET created_at = 0")
        self.assertEqual(self.client.post(f"/api/evaluations/{draft['평가ID']}/save").status_code, 404)

    def previous(self, record):
        response = self.client.get(f"/api/evaluations/{record['평가ID']}/previous")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['comparison']

    def test_automatic_previous_and_normalized_site(self):
        first = self.evaluate({**self.body, 'site_name': '  A   현장  '})
        self.assertIsNone(self.previous(first))
        other = self.evaluate({**self.body, 'site_name': '다른 현장'})
        second = self.evaluate({**self.body, 'site_name': 'A 현장', 'answers': {**self.body['answers'], 'Q002': 15}})
        third = self.evaluate({**self.body, 'site_name': 'A  현장'})
        self.assertEqual(self.previous(second)['평가요약'][0]['평가ID'], first['평가ID'])
        self.assertEqual(self.previous(third)['평가요약'][0]['평가ID'], second['평가ID'])
        self.assertEqual(self.previous(second)['비교안내']['변화상태'], '개선')
        self.assertIsNone(self.previous(other))
        self.assertIsNone(self.previous(first))

    def test_other_task_and_incompatible_nearest_not_skipped(self):
        first = self.evaluate()
        foreign = deepcopy(first)
        foreign.update(평가ID=str(uuid4()), 작업ID='H99', 평가일시='2020-01-01T00:00:00+09:00', 작업명='다른 작업')
        engine.save_evaluation(foreign, self.storage)
        self.assertIsNone(self.previous(first))
        incompatible = deepcopy(first)
        incompatible.update(평가ID=str(uuid4()), 평가일시='2020-02-01T00:00:00+09:00', 엔진SHA256='old-engine')
        engine.save_evaluation(incompatible, self.storage)
        result = self.previous(first)
        self.assertEqual(result['평가요약'][0]['평가ID'], incompatible['평가ID'])
        self.assertFalse(result['비교안내']['점수차이표시가능'])
        self.assertIsNone(result['비교안내']['위험지수차이(이후-이전)'])
        self.assertIn('엔진SHA256', result['비교안내']['비교제한사유'])
        self.assertTrue(all(r['변화분류'] == '비교 불가·확인 필요' for r in result['전체항목']))
        self.assertIn('H99', [r['작업ID'] for r in self.client.get('/api/evaluations').json()])

    def test_request_retry_and_legacy_snapshot_preservation(self):
        body = {**self.body, 'request_id': str(uuid4())}
        record = self.evaluate(body)
        self.assertEqual(self.evaluate(body), record)
        self.assertEqual(len(self.client.get('/api/evaluations').json()), 1)
        changed = {**body, 'site_name': '다른 입력'}
        self.assertEqual(self.client.post('/api/evaluate', json=changed).status_code, 409)
        self.assertTrue(record['근거스냅샷']['standards'])
        legacy = engine.build_evaluation('기존 현장', 'H05', self.body['answers'], self.body['watcher_answers'])
        engine.save_evaluation(legacy, self.storage)
        self.assertEqual(self.client.get(f"/api/evaluations/{legacy['평가ID']}").json(), legacy)
        # A changed in-memory reference cannot mutate an already saved snapshot.
        engine.standards.loc[0, '필수조치'] = '새 기준'
        self.assertEqual(self.client.get(f"/api/evaluations/{record['평가ID']}").json(), record)

    def test_factor_rules_unknown_exclusion_and_remaining(self):
        from .evaluation_history import compare
        before = self.evaluate()
        after = deepcopy(before)
        after['평가ID'] = str(uuid4())
        old = before['응답상세'][0]
        new = after['응답상세'][0]
        old.update(적용상태='적용', 집계대표여부=True, 사용자응답='없음', 가중점수=0)
        new.update(적용상태='적용', 집계대표여부=True, 사용자응답='있음', 가중점수=3)
        def row():
            return next(r for r in compare(before, after)['전체항목'] if r['항목ID'] == old['항목ID'])
        self.assertEqual(row()['변화분류'], '새롭게 발생')
        self.assertTrue(row()['추가개선필요'])
        old['가중점수'] = 1
        self.assertEqual(row()['변화분류'], '악화')
        old['가중점수'] = 3
        self.assertEqual(row()['변화분류'], '변화 없음')
        old['가중점수'] = 4
        self.assertEqual(row()['변화분류'], '개선')
        new['사용자응답'] = '확인불가'
        self.assertEqual(row()['변화분류'], '비교 불가·확인 필요')
        new['적용상태'] = '조건제외'
        self.assertIsNone(row()['이후_가중점수'])
        self.assertIsNone(row()['기여도차이'])

    def test_legacy_manual_save_and_missing_criteria(self):
        from . import storage
        from .evaluation_history import compare, site_key
        draft = engine.build_evaluation('기존 초안', 'H05', self.body['answers'], self.body['watcher_answers'])
        storage.save_draft(self.storage, draft)
        response = self.client.post(f"/api/evaluations/{draft['평가ID']}/save")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f"/api/evaluations/{draft['평가ID']}").json(), draft)
        after = deepcopy(draft)
        after['평가ID'] = str(uuid4())
        del after['요약']['최대가중점수']
        self.assertFalse(compare(draft, after)['비교안내']['점수차이표시가능'])
        self.assertNotEqual(site_key({**draft, '현장ID': 'a'}), site_key({**draft, '현장ID': 'b'}))
        self.assertEqual(site_key({**draft, '현장ID': 'a'}), site_key({**draft, '현장ID': 'a', '현장명': '새 이름'}))

    def test_integrated_watcher_score_parity_and_independent_answers(self):
        for deployment in ('배치', '미배치'):
            for exception in ('예', '아니오', '확인불가'):
                body = {**self.body, 'answers': {**self.body['answers'], 'Q004': deployment},
                        'watcher_answers': {**self.body['watcher_answers'], 'W004': exception}}
                legacy = self.evaluate(body)
                merged = self.evaluate({**body, 'watcher_ui_version': 'integrated-v1'})
                self.assertEqual(merged['요약'], legacy['요약'])
                self.assertEqual(merged['응답상세'], legacy['응답상세'])
                self.assertEqual(merged['엔진SHA256'], legacy['엔진SHA256'])
                self.assertEqual(merged['화재감시자입력']['예외조건응답'], exception)
                rows = [r for r in merged['응답상세'] if r['항목ID'] == 'Q004']
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['가중점수'], 6 if deployment == '미배치' else 0)
                self.assertFalse(merged['화재감시자검토']['예외조건검증완료'])
                self.assertTrue(self.previous(merged)['비교안내']['점수차이표시가능'])

    def test_integrated_watcher_unverified_deployment_is_saved_without_score(self):
        self.evaluate()
        for deployment in ('해당없음', '확인불가'):
            record = self.evaluate({**self.body, 'watcher_ui_version': 'integrated-v1',
                                    'answers': {**self.body['answers'], 'Q004': deployment}})
            self.assertIsNone(record['요약']['위험지수'])
            self.assertIsNone(record['요약']['총가중위험점수'])
            row = next(r for r in record['응답상세'] if r['항목ID'] == 'Q004')
            self.assertIsNone(row['가중점수'])
            self.assertEqual(row['사용자응답'], deployment)
            self.assertEqual(self.client.get(f"/api/evaluations/{record['평가ID']}").json(), record)
        self.assertFalse(self.previous(record)['비교안내']['점수차이표시가능'])
        response = self.client.get('/api/evaluations')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 3)
        self.assertIsNone(response.json()[0]['위험지수'])
        self.assertEqual(self.client.get('/api/dashboard').status_code, 200)

    def test_integrated_watcher_conditional_exception_and_distance_boundary(self):
        body = {**self.body, 'watcher_ui_version': 'integrated-v1',
                'answers': {**self.body['answers'], 'Q001': '없음', 'Q019': '없음', 'Q020': '없음'},
                'watcher_answers': {'W001': '아니오', 'W004': '예'}}
        record = self.evaluate(body)
        self.assertFalse(record['화재감시자입력']['예외질문표시'])
        self.assertIsNone(record['화재감시자입력']['예외조건응답'])
        self.assertIsNone(next(r for r in record['화재감시자응답'] if r['추가질문ID']=='W004')['응답'])
        for distance, expected in ((11, True), (11.1, False)):
            answers = {**body['answers'], 'Q001': '있음', 'Q002': distance}
            schema = self.client.post('/api/questions', json={'answers': answers, 'watcher_answers': {'W001': '아니오'}}).json()
            self.assertEqual(schema['watcher_context']['exception_required'], expected)
        invalid = {**self.body, 'watcher_ui_version': 'integrated-v1', 'watcher_answers': {'W001': '아니오'}}
        self.assertEqual(self.client.post('/api/evaluate', json=invalid).status_code, 422)

    def test_material_catalogue_classification_and_auth(self):
        data = self.client.get('/api/materials').json()
        self.assertEqual(len(data['rows']), 16)
        lookup = {r['물질ID']: r for r in data['rows']}
        self.assertEqual(lookup['M001']['선택분류'], '선택 제외')
        self.assertEqual(lookup['M002']['선택분류'], '분류 확인')
        self.assertEqual(lookup['M013']['선택분류'], '분류 확인 필요')
        self.assertEqual(lookup['M008']['인화점_원문'], '≤4℃')
        self.assertEqual(lookup['M006']['인화점_기준값℃'], '')
        del self.client.headers['X-Access-Key']
        self.assertEqual(self.client.get('/api/materials').status_code, 401)

    def test_material_multiple_snapshot_and_score_parity(self):
        baseline = self.evaluate({**self.body, 'watcher_ui_version': 'integrated-v1'})
        selection = {'ids': ['M008', 'M002'], 'custom_names': [' 현장  보온재 '], 'unknown': True}
        record = self.evaluate({**self.body, 'watcher_ui_version': 'integrated-v1', 'materials': selection})
        info = record['가연물정보']
        self.assertEqual(record['요약'], baseline['요약'])
        self.assertEqual(record['응답상세'], baseline['응답상세'])
        self.assertEqual(record['계산데이터SHA256'], baseline['계산데이터SHA256'])
        self.assertEqual([r['물질ID'] for r in info['선택물질']], ['M008', 'M002'])
        self.assertEqual(info['직접입력'], [{'물질명': '현장 보온재', 'MSDS확인': '미확인'}])
        self.assertEqual(info['확인필요수'], 3)
        self.assertFalse(info['점수반영'])
        self.assertEqual(self.client.get(f"/api/evaluations/{record['평가ID']}").json(), record)
        compared = self.previous(record)
        self.assertTrue(compared['비교안내']['점수차이표시가능'])
        self.assertEqual(compared['비교안내']['위험지수차이(이후-이전)'], 0)
        self.assertEqual(compared['가연물변화']['이전']['기록상태'], '당시 물질 종류 정보 미기록')
        with patch('fire_risk_project.materials.MSDS_PATH', Path(self.directory.name)/'missing.csv'):
            self.assertEqual(self.client.get(f"/api/evaluations/{record['평가ID']}").json(), record)

    def test_material_none_clears_stale_data_and_unknown_keeps_presence(self):
        stale = {'ids': ['M008'], 'custom_names': ['기존 물질'], 'unknown': True}
        absent = self.evaluate({**self.body, 'answers': {**self.body['answers'], 'Q001': '없음'}, 'materials': stale})
        info = absent['가연물정보']
        self.assertEqual(info['선택물질'], [])
        self.assertEqual(info['직접입력'], [])
        self.assertFalse(info['종류확인필요'])
        self.assertIsNone(info['거리m'])
        self.assertNotIn('Q002', absent['응답'])
        unknown = self.evaluate({**self.body, 'materials': {'unknown': True}})
        self.assertEqual(unknown['가연물정보']['존재여부'], '있음')
        self.assertEqual(unknown['가연물정보']['거리m'], self.body['answers']['Q002'])
        self.assertEqual(unknown['가연물정보']['확인필요수'], 1)

    def test_material_invalid_inputs_do_not_save(self):
        for selection in ({}, {'ids': ['not-real']}, {'ids': ['M001']}, {'ids': ['M008','M008']},
                          {'custom_names': [' ']}, {'custom_names': ['a', ' a ']}, {'unknown': 'yes'}, {'ids': ['M008'], 'score': 0}):
            with self.subTest(selection=selection):
                self.assertEqual(self.client.post('/api/evaluate', json={**self.body, 'materials': selection}).status_code, 422)
        for distance in (-1, None):
            self.assertEqual(self.client.post('/api/evaluate', json={**self.body, 'answers': {**self.body['answers'], 'Q002': distance}, 'materials': {'unknown': True}}).status_code, 422)
        self.assertEqual(self.client.get('/api/evaluations').json(), [])

    def test_material_db_failure_does_not_break_assessment(self):
        missing = Path(self.directory.name)/'missing.csv'
        with patch('fire_risk_project.materials.MSDS_PATH', missing):
            self.assertEqual(self.client.get('/api/materials').status_code, 503)
            self.assertEqual(self.client.post('/api/questions', json={'answers': self.body['answers']}).status_code, 200)
            self.assertEqual(self.client.post('/api/evaluate', json={**self.body, 'materials': {'ids': ['M008']}}).status_code, 503)
            record = self.evaluate({**self.body, 'materials': {'unknown': True}})
            self.assertIn('조회 실패', record['가연물정보']['DB상태'])
            self.assertEqual(record['가연물정보']['존재여부'], '있음')
        malformed = Path(self.directory.name)/'bad.csv'
        malformed.write_text('물질ID,제품명\nM001,잘못된 DB\n', encoding='utf-8')
        with patch('fire_risk_project.materials.MSDS_PATH', malformed):
            self.assertEqual(self.client.get('/api/materials').status_code, 503)

    def test_material_changes_never_imply_numeric_improvement(self):
        first = self.evaluate({**self.body, 'materials': {'unknown': True}})
        second = self.evaluate({**self.body, 'materials': {'ids': ['M008']}})
        compared = self.previous(second)
        self.assertEqual(compared['평가요약'][0]['평가ID'], first['평가ID'])
        self.assertEqual(compared['비교안내']['변화상태'], '변화 없음')
        self.assertTrue(compared['가연물변화']['확인완료변경'])
        third = self.evaluate({**self.body, 'materials': {'ids': ['M011']}})
        compared = self.previous(third)
        self.assertEqual(compared['평가요약'][0]['평가ID'], second['평가ID'])
        self.assertEqual(compared['비교안내']['위험지수차이(이후-이전)'], 0)
        self.assertTrue(compared['가연물변화']['종류변경'])


if __name__ == "__main__":
    unittest.main()
