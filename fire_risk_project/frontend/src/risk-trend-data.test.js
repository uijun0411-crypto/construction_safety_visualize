import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTrendPoints, formatRiskIndex, groupLegacySeries, groupZoneSeries, zoneRecordKey } from './risk-trend-data.js';

const key = (name) => name;
const ruleBasis = ['rules-a', 'engine-a', 30];
const zoneRecord = (id, zoneId, taskId, score, date) => ({
  [key('\uD3C9\uAC00ID')]: id, [key('\uD604\uC7A5ID')]: 'site-a', [key('\uD604\uC7A5\uBA85')]: '\uD604\uC7A5 A',
  [key('\uC870\uAC10\uB3C4ID')]: 'image-a', [key('\uC791\uC5C5\uAD6C\uC5EDID')]: zoneId,
  [key('\uC791\uC5C5ID')]: taskId, [key('\uC704\uD5D8\uC9C0\uC218')]: score,
  [key('\uC704\uD5D8\uC218\uC900')]: '\uC8FC\uC758', [key('\uD3C9\uAC00\uC77C\uC2DC')]: date,
  [key('\uACC4\uC0B0\uAE30\uC900')]: ruleBasis,
});

test('site and work-zone grouping keeps A and B in separate score series', () => {
  const records = [
    zoneRecord('a-new', 'zone-a', 'H05', 40, '2026-02-02T00:00:00Z'),
    zoneRecord('b-only', 'zone-b', 'H05', 80, '2026-02-02T00:00:00Z'),
    zoneRecord('a-old', 'zone-a', 'H05', 36.6666666667, '2026-02-01T00:00:00Z'),
    zoneRecord('a-other-task', 'zone-a', 'H08', 70, '2026-02-03T00:00:00Z'),
  ];
  const zoneA = groupZoneSeries(records, '\uD604\uC7A5 A', zoneRecordKey(records[0]));
  assert.equal(zoneA.length, 2);
  const h05Series = zoneA.find(series => series.records[0][key('\uC791\uC5C5ID')] === 'H05');
  assert.deepEqual(h05Series.records.map(record => record[key('\uD3C9\uAC00ID')]), ['a-new', 'a-old']);
  assert.equal(groupZoneSeries(records, '\uB2E4\uB978 \uD604\uC7A5', zoneRecordKey(records[0])).length, 0);
  assert.equal(groupZoneSeries(records, '\uD604\uC7A5 A', zoneRecordKey(records[1]))[0].records[0][key('\uD3C9\uAC00ID')], 'b-only');
  assert.equal(groupZoneSeries(records, '\uD604\uC7A5 A', zoneRecordKey(records[3])).some(series => series.records[0][key('\uC791\uC5C5ID')] === 'H08'), true);
});

test('trend points sort by evaluation time, retain raw scores, and show two decimals and delta', () => {
  const points = buildTrendPoints([
    zoneRecord('later', 'zone-a', 'H05', 40, '2026-02-02T00:00:00Z'),
    zoneRecord('earlier', 'zone-a', 'H05', 36.6666666667, '2026-02-01T00:00:00Z'),
  ], true);
  assert.deepEqual(points.map(point => point.id), ['earlier', 'later']);
  assert.equal(points[0].score, 36.6666666667);
  assert.equal(formatRiskIndex(points[0].score), '36.67\uC810');
  assert.equal(points[0].delta, null);
  assert.equal(points[1].delta, 40 - 36.6666666667);
});

test('legacy trend grouping requires a selected site and matching calculation basis', () => {
  const records = [
    { id: 'one', group: ['data-a', 'engine-a', 30] },
    { id: 'two', group: ['data-a', 'engine-a', 30] },
    { id: 'other-rules', group: ['data-b', 'engine-a', 30] },
  ];
  assert.equal(groupLegacySeries(records, '').length, 0);
  assert.equal(groupLegacySeries(records, '\uD604\uC7A5 A').length, 2);
});
