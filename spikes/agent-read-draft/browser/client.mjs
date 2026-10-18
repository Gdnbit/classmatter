import {createParser} from 'eventsource-parser';

const types = new Set(['run.started','tool.proposed','tool.started','tool.completed',
  'clarification.required','draft.available','message.delta','run.completed','run.failed','run.cancelled']);
const terminals = new Set(['run.completed','run.failed','run.cancelled']);

// Project envelope validation only; upstream owns SSE parsing and UTF-8 is native.
export async function consumeEvents(response, onEvent) {
  if (!response.ok || !response.headers.get('content-type')?.startsWith('text/event-stream') || !response.body)
    throw new Error('stream_not_available');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', {fatal:true});
  const events = [];
  let run, terminal = false, wireBytes = 0;
  const parser = createParser({maxBufferSize:65536,
    onError(error) {throw error;},
    onRetry() {throw new Error('replay_not_supported');},
    onEvent(frame) {
      const e = JSON.parse(frame.data);
      if (terminal || events.length >= 128 || !e || Object.keys(e).sort().join(',') !== 'cursor,payload,run_id,type'
          || !Number.isInteger(e.cursor) || e.cursor !== events.length + 1
          || typeof e.run_id !== 'string' || !e.run_id || e.run_id.length > 128
          || (run && e.run_id !== run) || !types.has(e.type)
          || !e.payload || typeof e.payload !== 'object' || Array.isArray(e.payload)
          || frame.id !== String(e.cursor) || frame.event !== e.type
          || (!events.length && e.type !== 'run.started')
          || (events.length && e.type === 'run.started')
          || new TextEncoder().encode(frame.data).length > 32768)
        throw new Error('invalid_runtime_event');
      run = e.run_id;
      terminal = terminals.has(e.type);
      events.push(e);
      onEvent(e);
    },
  });
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      wireBytes += value.byteLength;
      if (wireBytes > 300000) throw new Error('stream_limit');
      parser.feed(decoder.decode(value, {stream:true}));
    }
    parser.feed(decoder.decode());
    parser.reset({consume:true});
    if (!terminal) throw new Error('connection_ended_without_terminal');
    return events;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
