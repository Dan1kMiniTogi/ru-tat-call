/**
 * Node self-test for RuTatPcm (invoked from pytest).
 *
 * Usage:
 *     node pcm_selftest.js /path/to/web_client/js/pcm.js
 */
require(process.argv[2]);
const pcm = globalThis.RuTatPcm;
const in48 = new Float32Array(48000);
for (let i = 0; i < in48.length; i++) {
  in48[i] = Math.sin(i / 10);
}
const out = pcm.downsampleTo16k(in48, 48000);
if (out.length !== 16000) {
  process.exit(2);
}
const buf = pcm.floatToS16le(out);
if (buf.byteLength !== 32000) {
  process.exit(3);
}
const b64 = pcm.arrayBufferToBase64(buf);
if (!b64.length) {
  process.exit(4);
}
const a = new Int16Array([1, 2]);
const b = new Int16Array([3]);
const c = pcm.concatInt16(a, b);
if (c.length !== 3 || c[2] !== 3) {
  process.exit(5);
}
