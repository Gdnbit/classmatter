import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';

// This test worker only; never changes the Windows/browser timezone.
process.env.TZ = 'America/New_York';
const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/local-time.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const bundle = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
// Keep failure stacks readable instead of dumping the compiled library's data URL.
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.code + '\n//# sourceURL=class-os-local-time.unit.mjs\n').toString('base64')}`);

test('ordinary local time keeps exact UTC and millisecond output across supported zones', () => {
  for (const [value, zone, expected] of [
    ['2026-10-08T09:01', 'Asia/Shanghai', '2026-10-08T01:01:00.000Z'],
    ['2026-10-08T09:01:02.123', 'Asia/Shanghai', '2026-10-08T01:01:02.123Z'],
    ['2026-10-08T09:01:02.1', 'UTC', '2026-10-08T09:01:02.100Z'],
    ['2026-07-01T12:00', 'America/New_York', '2026-07-01T16:00:00.000Z'],
    ['2026-01-01T12:00', 'America/New_York', '2026-01-01T17:00:00.000Z'],
  ]) assert.equal(api.localDateTimeToUtc(value, zone), expected);
  assert.equal(api.localDateTimeToUtc('2026-01-01T12:00'), '2026-01-01T17:00:00.000Z');
});

test('DST gap and fold reject instead of silently shifting or choosing an offset', () => {
  for (const [value, zone] of [
    ['2026-03-08T02:30', 'America/New_York'], ['2026-11-01T01:30', 'America/New_York'],
    ['2026-10-04T02:15', 'Australia/Lord_Howe'], ['2026-04-05T01:45', 'Australia/Lord_Howe'],
  ]) assert.throws(() => api.localDateTimeToUtc(value, zone), /时间无效、不存在或有歧义/);
  assert.throws(() => api.localDateTimeToUtc('2026-03-08T02:30'), /时间无效、不存在或有歧义/);
});

test('unchanged known UTC instant is reused without losing fold choice or server microseconds', () => {
  for (const known of ['2026-11-01T05:30:00+00:00', '2026-11-01T06:30:00+00:00']) {
    assert.equal(api.localDateTimeToUtc('2026-11-01T01:30', 'America/New_York', known), known);
    assert.throws(() => api.localDateTimeToUtc('2026-11-01T01:45', 'America/New_York', known), /时间无效、不存在或有歧义/);
  }
  const precise = '2026-10-08T01:01:02.123456+00:00';
  assert.equal(api.localDateTimeToUtc('2026-10-08T09:01:02.123', 'Asia/Shanghai', precise), precise);
  assert.throws(() => api.localDateTimeToUtc('2026-11-01T01:30', 'America/New_York', '2026-11-01T01:30'), /时间无效、不存在或有歧义/);
  assert.throws(() => api.localDateTimeToUtc('2026-11-01T01:30', 'America/New_York', '2026-11-01T05:30:00Z\n'), /时间无效、不存在或有歧义/);
});

test('invalid calendars, non-wall formats and unknown zones use one static non-echoed error', () => {
  for (const value of ['', 'synthetic-private-time-canary', '2026-02-30T09:00', '0000-01-01T00:00',
    '2026-10-08', '2026-10-08T24:00', '2026-10-08T09:00Z', '2026-10-08T09:00+08:00',
    '2026-10-08T09:00:00.1234', '2026-10-08T09:00[Asia/Shanghai]', '2026-10-08T09:00\n']) {
    assert.throws(() => api.localDateTimeToUtc(value, 'UTC'), error => {
      assert.equal(error.message, '时间无效、不存在或有歧义。请核对本机时区并选择明确时间后再预览。');
      assert(!error.stack.includes('data:'));
      return true;
    });
  }
  assert.throws(() => api.localDateTimeToUtc('2026-10-08T09:00', 'synthetic-private-zone-canary'), error => {
    assert.equal(error.message, '时间无效、不存在或有歧义。请核对本机时区并选择明确时间后再预览。');
    return true;
  });
});
