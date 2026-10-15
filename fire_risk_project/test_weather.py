"""Offline fixtures only; these are not live KMA observations."""
from copy import deepcopy
from datetime import datetime
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from .api import create_app
from . import weather

NOW = datetime(2026, 10, 15, 13, 50, tzinfo=weather.KST)
LOCATION = next(r for r in weather.REGIONS.values() if r['name'] == '서울특별시 강남구')
BASE = weather.base_time(NOW)


def items():
    return [dict(nx=LOCATION['nx'], ny=LOCATION['ny'], baseDate='20261015', baseTime='1330',
                 fcstDate='20261015', fcstTime='1400', category=k, fcstValue=v)
            for k, v in {'T1H': '19', 'REH': '55', 'PTY': '0', 'RN1': '강수없음', 'SKY': '3'}.items()]


class WeatherTests(unittest.TestCase):
    def setUp(self):
        weather._cache.clear()

    def test_region_mapping_and_kst_rollover(self):
        self.assertEqual((LOCATION['nx'], LOCATION['ny']), (61, 126))
        self.assertGreater(len(weather.REGIONS), 250)
        for minute, expected in [(44, '202610142330'), (45, '202610150030')]:
            self.assertEqual(weather.base_time(datetime(2026, 10, 15, 0, minute, tzinfo=weather.KST)).strftime('%Y%m%d%H%M'), expected)
        with self.assertRaises(ValueError):
            weather.region('not-a-region')

    def test_values_missing_and_wrong_grid(self):
        data = weather.parse_items(items(), LOCATION, BASE, NOW)
        self.assertEqual((data['temperature'], data['humidity'], data['sky'], data['precipitation']), (19, 55, '구름많음', '없음'))
        self.assertEqual(data['valid_at'], '2026-10-15T14:00:00+09:00')
        sparse = [r for r in items() if r['category'] != 'SKY']
        sparse[0]['fcstValue'] = '-999'
        result = weather.parse_items(sparse, LOCATION, BASE, NOW)
        self.assertIsNone(result['sky'])
        self.assertIsNone(result['temperature'])
        with self.assertRaises(weather.WeatherError):
            weather.parse_items([{**r, 'nx': 1} for r in items()], LOCATION, BASE, NOW)
        with self.assertRaises(weather.WeatherError):
            weather.parse_items(items(), LOCATION, BASE, NOW.replace(hour=20))

    @patch.dict(os.environ, {'KMA_SERVICE_KEY': 'test-secret'})
    def test_fetch_cache_and_signed_snapshot(self):
        payload = {'response': {'header': {'resultCode': '00'}, 'body': {'items': {'item': items()}}}}
        with patch.object(weather, 'datetime') as clock, patch.object(weather, 'urlopen') as upstream:
            clock.now.return_value = NOW
            clock.strptime.side_effect = datetime.strptime
            upstream.return_value = io.BytesIO(json.dumps(payload).encode())
            first = weather.fetch(LOCATION['id'])
            self.assertEqual(weather.fetch(LOCATION['id']), first)
            self.assertEqual(upstream.call_count, 1)
            url = upstream.call_args.args[0]
            self.assertIn('getUltraSrtFcst', url)
            self.assertIn('base_time=1330', url)
            self.assertNotIn('test-secret', json.dumps(first))
            self.assertEqual(weather.restore(first['token'], LOCATION['id']), first['snapshot'])
            self.assertIsNone(weather.restore(first['token'], 'other-region'))
            self.assertIsNone(weather.restore(first['token']+'x', LOCATION['id']))

    @patch.dict(os.environ, {'KMA_SERVICE_KEY': 'test-secret'})
    def test_failure_sanitization_and_throttle(self):
        with patch.object(weather, 'urlopen', side_effect=OSError('URL with test-secret')) as upstream:
            for _ in range(2):
                with self.assertRaises(weather.WeatherError) as caught:
                    weather.fetch(LOCATION['id'])
                self.assertNotIn('test-secret', str(caught.exception))
            self.assertEqual(upstream.call_count, 1)

    def test_api_snapshot_persistence_parity_and_legacy(self):
        with TemporaryDirectory() as temporary, patch.dict(os.environ, {'KMA_SERVICE_KEY': 'test-secret'}):
            with TestClient(create_app(Path(temporary)/'test.sqlite3', access_key='')) as client:
                answers = {'Q001':'없음','Q003':'실시','Q004':'배치','Q018':'용접방화포 미사용','Q019':'없음','Q020':'없음','Q025':'적정'}
                body = {'site_name':'기상 테스트 현장','answers':answers,'watcher_ui_version':'integrated-v1','watcher_answers':{'W001':'아니오'}}
                data = weather.parse_items(items(), LOCATION, BASE, NOW)
                token = weather._sign(data, 'test-secret')
                legacy = client.post('/api/evaluate', json=body)
                self.assertEqual(legacy.status_code, 200, legacy.text)
                result = client.post('/api/evaluate', json={**body,'region_id':LOCATION['id'],'weather_token':token})
                self.assertEqual(result.status_code, 200, result.text)
                record = result.json()
                self.assertEqual(record['요약'], legacy.json()['요약'])
                self.assertEqual(record['응답상세'], legacy.json()['응답상세'])
                with patch.object(weather, 'fetch', side_effect=AssertionError('History must not fetch live weather')):
                    saved = client.get('/api/evaluations/'+record['평가ID']).json()
                    self.assertEqual(saved['기상정보'], data)
                    self.assertNotIn('기상정보', client.get('/api/evaluations/'+legacy.json()['평가ID']).json())
                    self.assertIsNotNone(client.get('/api/evaluations/'+record['평가ID']+'/previous').json()['comparison'])
                invalid = client.post('/api/evaluate', json={**body,'region_id':LOCATION['id'],'weather_token':token+'x'})
                self.assertEqual(invalid.status_code, 200)
                self.assertIsNone(invalid.json()['기상정보'])
                self.assertEqual(invalid.json()['현장위치']['id'], LOCATION['id'])
                self.assertEqual(client.get('/api/weather?region_id=unknown').status_code, 422)
                with patch.dict(os.environ, {'KMA_SERVICE_KEY': ''}):
                    self.assertEqual(client.get('/api/weather?region_id='+LOCATION['id']).status_code, 503)
                    self.assertEqual(client.post('/api/evaluate', json={**body,'region_id':LOCATION['id']}).status_code, 200)
                self.assertEqual(len(client.get('/api/weather/regions').json()['regions']), 274)


if __name__ == '__main__':
    unittest.main()
