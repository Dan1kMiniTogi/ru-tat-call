/**
 * Exponential backoff for signaling / ASR reconnect (step 5.1).
 */
(function (root) {
  const BASE_MS = 500;
  const CAP_MS = 15000;

  /**
   * Delay before the next reconnect attempt.
   *
   * @param {number} attempt 0-based failed try count.
   * @returns {number} Milliseconds, capped at 15s.
   * @example
   * nextDelay(0) === 500
   * nextDelay(8) === 15000
   */
  function nextDelay(attempt) {
    const n = Math.max(0, attempt | 0);
    return Math.min(CAP_MS, BASE_MS * Math.pow(2, n));
  }

  root.RuTatReconnect = {
    BASE_MS: BASE_MS,
    CAP_MS: CAP_MS,
    nextDelay: nextDelay,
  };
})(typeof window !== "undefined" ? window : globalThis);
