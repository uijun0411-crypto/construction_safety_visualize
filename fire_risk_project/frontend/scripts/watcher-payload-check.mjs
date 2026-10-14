import assert from 'node:assert/strict';
import { buildWatcherAnswers } from '../src/watcher-payload.js';

const allowed = ['W001', 'W004'];
assert.deepEqual(buildWatcherAnswers({ W001: '예', W004: '확인불가' }, allowed), {
  W001: '예', W004: '확인불가',
});
assert.deepEqual(buildWatcherAnswers({ W001: true, W004: [], W099: '예' }, allowed), {});
assert.deepEqual(buildWatcherAnswers({ W001: '아니오', W004: '예' }, allowed, false), {
  W001: '아니오',
});
console.log('watcher payload checks passed');
