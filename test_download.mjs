import assert from 'node:assert/strict';
import './static/download.js';

let passed = 0;
async function check(name, fn) { await fn(); console.log(`${++passed}. ${name} OK`); }
const read = globalThis.SDDownload.readResponse;
const bytes = new TextEncoder();
await check('Top-level storage errors remain visible', async () => {
  await assert.rejects(read(new Response(JSON.stringify({message: 'Seafile error'}), {status: 502})), /Seafile error/);
});
await check('Nested authentication errors remain visible', async () => {
  await assert.rejects(read(new Response(JSON.stringify({detail: {message: 'Login expired'}}), {status: 401})), /Login expired/);
});
await check('Proxy HTML error includes HTTP status', async () => {
  await assert.rejects(read(new Response('<html>bad gateway</html>', {status: 502})), /HTTP 502/);
});
await check('Stream reports progress and preserves bytes', async () => {
  const stream = new ReadableStream({start(c) { c.enqueue(bytes.encode('abc')); c.enqueue(bytes.encode('def')); c.close(); }});
  const progress = [];
  const blob = await read(new Response(stream, {headers: {'content-length': '6'}}), p => progress.push(p.loaded));
  assert.equal(await blob.text(), 'abcdef');
  assert.deepEqual(progress, [0, 3, 6]);
});
await check('Unknown length does not imply empty file', async () => {
  let latest;
  assert.equal(await (await read(new Response('abc'), p => latest = p)).text(), 'abc');
  assert.deepEqual(latest, {loaded: 3, total: null});
});
await check('Truncated body never becomes a successful download', async () => {
  await assert.rejects(read(new Response('abc', {headers: {'content-length': '9'}})), /传输不完整/);
});
await check('Aborted stream propagates cancellation', async () => {
  const stream = new ReadableStream({start(c) { c.error(new DOMException('cancel', 'AbortError')); }});
  await assert.rejects(read(new Response(stream)), e => e.name === 'AbortError');
});
console.log(`All ${passed} download checks passed.`);
