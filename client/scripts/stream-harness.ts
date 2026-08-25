// Does apiStream survive a real network's framing? (Phase 8)
//
// The frontend has no test runner, and this is the one piece of Phase 8 that a
// type checker cannot vouch for: SSE arrives in chunks chosen by the network,
// not by the sender, so every boundary bug hides until a slow connection finds
// it. This drives the REAL client.ts export — not a copy of its logic, which
// would encode the same assumption and agree with the bug.
//
//   cd client
//   ./node_modules/.bin/rolldown scripts/stream-harness.ts -o /tmp/h.mjs -f esm \
//     -p node --transform.define 'import.meta.env.VITE_API_URL:"http://x"' && node /tmp/h.mjs
//
// All four guards below have been watched to fail: dropping the partial-frame
// buffer, decoding without { stream: true }, skipping the EOF flush, and letting
// a 429 through as a stream each turn one of these red.
import { apiStream, ApiError } from '../src/api/client';

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i >= chunks.length) { controller.close(); return; }
      controller.enqueue(encoder.encode(chunks[i++]));
    },
  });
}

function fakeResponse(chunks: string[], status = 200, body?: string): any {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'x',
    body: status === 200 ? streamOf(chunks) : null,
    json: async () => JSON.parse(body ?? '{}'),
    text: async () => chunks.join(''),
  };
}

async function collect(chunks: string[]): Promise<any[]> {
  const seen: any[] = [];
  (globalThis as any).fetch = async () => fakeResponse(chunks);
  await apiStream('/chat', { body: {}, onEvent: (e) => seen.push(e) });
  return seen;
}

const wire =
  'data: {"type": "tool_start", "name": "list_my_pets", "label": "Looking up your pets..."}\n\n' +
  'data: {"type": "tool_end", "name": "list_my_pets"}\n\n' +
  'data: {"type": "token", "text": "Luna is "}\n\n' +
  'data: {"type": "token", "text": "due for her booster. \\u00e9"}\n\n' +
  'data: {"type": "proposal", "kind": "appointment", "proposal": {"pet_id": 1, "starts_at": "2026-08-25T06:00:00Z"}}\n\n' +
  'data: {"type": "done", "conversation_id": 12, "message_id": 48}\n\n';

function chop(text: string, size: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size));
  return out;
}

let failures = 0;
function check(name: string, condition: boolean, extra?: unknown) {
  if (condition) { console.log(`  ok   ${name}`); }
  else { failures++; console.log(`  FAIL ${name}`, extra ?? ''); }
}

(async () => {
  console.log('1. whole body in one chunk');
  let events = await collect([wire]);
  check('6 events', events.length === 6, events.length);
  check('done carries the conversation id', events[5].conversation_id === 12);

  console.log('2. one byte at a time (frames split everywhere)');
  events = await collect(chop(wire, 1));
  check('still 6 events', events.length === 6, events.length);
  check('token text intact', events[2].text === 'Luna is ');
  check('escaped non-ascii survives', events[3].text.endsWith('\u00e9'));
  check('proposal nested object intact', events[4].proposal.starts_at === '2026-08-25T06:00:00Z');

  console.log('3. split exactly between the two newlines of a frame terminator');
  const cut = wire.indexOf('\n\n') + 1;
  events = await collect([wire.slice(0, cut), wire.slice(cut)]);
  check('no frame lost or merged', events.length === 6, events.length);

  console.log('4. multibyte character split across chunk boundary');
  const utf8 = 'data: {"type": "token", "text": "caf\u00e9 \u2615"}\n\n';
  const bytes = new TextEncoder().encode(utf8);
  // Split INSIDE the three bytes of the coffee cup, not merely near it: the
  // whole point is that one read() ends mid-code-point.
  const cup = bytes.indexOf(0xe2);
  check('the split really is mid-character', cup > 0 && bytes[cup + 1] === 0x98, cup);
  (globalThis as any).fetch = async () => ({
    ok: true, status: 200,
    body: new ReadableStream({ start(c) { c.enqueue(bytes.slice(0, cup + 1)); c.enqueue(bytes.slice(cup + 1)); c.close(); } }),
  });
  const seen: any[] = [];
  await apiStream('/chat', { body: {}, onEvent: (e) => seen.push(e) });
  check('decoder stitched the code point', seen.length === 1 && seen[0].text === 'caf\u00e9 \u2615', seen);

  console.log('5. keep-alive comments, CRLF framing, and a trailing frame with no blank line');
  events = await collect([
    ': keep-alive\n\n',
    'data: {"type": "token", "text": "a"}\r\n\r\n',
    'data: {"type": "done", "conversation_id": 3, "message_id": 9}',
  ]);
  check('comment ignored, CRLF parsed, EOF flushed', events.length === 2 && events[1].message_id === 9, events);

  console.log('6. malformed frame does not take the reply down');
  events = await collect(['data: {oops\n\n', 'data: {"type": "token", "text": "b"}\n\n']);
  check('bad frame dropped, good frame kept', events.length === 1 && events[0].text === 'b', events);

  console.log('7. errors raised before the stream arrive as ApiError');
  (globalThis as any).fetch = async () =>
    fakeResponse([], 429, '{"detail":"Too many messages. Please wait a moment."}');
  try {
    await apiStream('/chat', { body: {}, onEvent: () => {} });
    check('429 throws', false);
  } catch (error: any) {
    check('429 is an ApiError with the server sentence',
      error instanceof ApiError && error.status === 429 && error.detail.startsWith('Too many messages'), error);
  }

  console.log('8. a dead server is the offline sentence, not a crash');
  (globalThis as any).fetch = async () => { throw new TypeError('fetch failed'); };
  try {
    await apiStream('/chat', { body: {}, onEvent: () => {} });
    check('network failure throws', false);
  } catch (error: any) {
    check('ApiError(0)', error instanceof ApiError && error.status === 0, error);
  }

  console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILURE(S)`);
  process.exit(failures === 0 ? 0 : 1);
})();
