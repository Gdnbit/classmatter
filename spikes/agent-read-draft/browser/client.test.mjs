import assert from 'node:assert/strict';
import test from 'node:test';
import { consumeEvents } from './client.mjs';

const event = (cursor, type, payload = {}, run_id = 'synthetic-run') => ({cursor, type, run_id, payload});
const frame = e => `id: ${e.cursor}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`;
function response(text, oneByte = false) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({start(c) {
    if (oneByte) for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
    else c.enqueue(bytes);
    c.close();
  }}), {headers: {'content-type': 'text/event-stream'}});
}

test('upstream parser preserves one-byte UTF-8 and publishes before EOF', async () => {
  const expected = [event(1, 'run.started'), event(2, 'message.delta', {text: '合成 🧪 中文'}),
    event(3, 'run.completed')];
  const seen = [];
  const result = await consumeEvents(response(expected.map(frame).join(''), true), e => seen.push(e));
  assert.deepEqual(result, expected);
  assert.deepEqual(seen, expected);
});

test('first event callback arrives before stream closes', async () => {
  let source;
  const body = new ReadableStream({start(c) {source = c;}});
  const seen = [];
  const pending = consumeEvents(new Response(body, {headers: {'content-type':'text/event-stream'}}), e => seen.push(e));
  source.enqueue(new TextEncoder().encode(frame(event(1, 'run.started'))));
  await new Promise(r => setImmediate(r));
  assert.equal(seen[0].type, 'run.started');
  source.enqueue(new TextEncoder().encode(frame(event(2, 'run.completed'))));
  source.close();
  await pending;
});

for (const [name, text] of Object.entries({
  missingTerminal: frame(event(1, 'run.started')),
  duplicateCursor: frame(event(1,'run.started')) + frame(event(1,'run.completed')),
  differentRun: frame(event(1,'run.started')) + frame(event(2,'run.completed',{},'other')),
  unknownType: frame(event(1,'run.started')) + frame(event(2,'sql.apply')),
  terminalTwice: frame(event(1,'run.started')) + frame(event(2,'run.completed')) + frame(event(3,'run.completed')),
  mismatchedFrame: frame(event(1,'run.started')).replace('event: run.started', 'event: run.completed'),
  truncated: frame(event(1,'run.started')) + frame(event(2,'run.completed')).slice(0,-2),
})) test(`reject ${name}`, async () => {
  await assert.rejects(consumeEvents(response(text), () => {}));
});

test('HTTP rejection and non-SSE body cannot become successful run', async () => {
  await assert.rejects(consumeEvents(new Response('{}',{status:403}), () => {}));
  await assert.rejects(consumeEvents(new Response('{}'), () => {}));
});

test('callback failure cancels reader and does not retry', async () => {
  let cancelled = false;
  const r = new Response(new ReadableStream({start(c) {
    c.enqueue(new TextEncoder().encode(frame(event(1,'run.started'))));
  }, cancel() {cancelled = true;}}), {headers:{'content-type':'text/event-stream'}});
  await assert.rejects(consumeEvents(r, () => {throw new Error('consumer closed');}));
  assert.equal(cancelled,true);
});

test('event, parser-buffer, aggregate-wire and count limits reject oversized peers', async () => {
  const excessive = [
    frame(event(1,'run.started')) + frame(event(2,'message.delta',{text:'x'.repeat(40000)})),
    'data: '+ 'x'.repeat(70000),
    frame(event(1,'run.started')) + Array.from({length:90},(_,i)=>frame(event(i+2,'message.delta',
      {text:'x'.repeat(5000)}))).join(''),
    frame(event(1,'run.started')) + Array.from({length:128},(_,i)=>frame(event(i+2,'tool.started'))).join(''),
  ];
  for(const text of excessive) await assert.rejects(consumeEvents(response(text),()=>{}));
});
