/**
 * Node self-test for RuTatReconnect backoff.
 *
 * Usage:
 *     node reconnect_selftest.js /path/to/web_client/js/reconnect.js
 */
require(process.argv[2]);
const R = globalThis.RuTatReconnect;
if (R.nextDelay(0) !== 500) {
  process.exit(2);
}
if (R.nextDelay(1) !== 1000) {
  process.exit(3);
}
if (R.nextDelay(8) !== 15000) {
  process.exit(4);
}
if (R.nextDelay(-1) !== 500) {
  process.exit(5);
}
