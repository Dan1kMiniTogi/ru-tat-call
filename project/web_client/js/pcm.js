/**
 * PCM helpers: downsample to 16 kHz and pack little-endian s16.
 */
(function (root) {
  const TARGET_RATE = 16000;

  /**
   * Linear-resample Float32 mono to 16 kHz.
   *
   * @param {Float32Array} input Native-rate samples in [-1, 1].
   * @param {number} inputRate AudioContext.sampleRate.
   * @returns {Float32Array}
   * @example
   * downsampleTo16k(new Float32Array(48000), 48000).length === 16000
   */
  function downsampleTo16k(input, inputRate) {
    if (!input.length) {
      return new Float32Array(0);
    }
    if (inputRate === TARGET_RATE) {
      return input;
    }
    const ratio = inputRate / TARGET_RATE;
    const outLen = Math.max(1, Math.floor(input.length / ratio));
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio;
      const i0 = Math.min(Math.floor(pos), input.length - 1);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const frac = pos - i0;
      out[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    return out;
  }

  /**
   * Convert Float32 [-1, 1] to interleaved s16le ArrayBuffer.
   *
   * @param {Float32Array} f32
   * @returns {ArrayBuffer}
   */
  function floatToS16le(f32) {
    const buf = new ArrayBuffer(f32.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < f32.length; i++) {
      let s = f32[i];
      if (s > 1) {
        s = 1;
      } else if (s < -1) {
        s = -1;
      }
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buf;
  }

  /**
   * Base64-encode an ArrayBuffer (MVP ASR JSON frames).
   *
   * @param {ArrayBuffer} buf
   * @returns {string}
   */
  function arrayBufferToBase64(buf) {
    const bytes = new Uint8Array(buf);
    const chunk = 0x8000;
    let bin = "";
    for (let i = 0; i < bytes.length; i += chunk) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(bin);
  }

  /**
   * Concatenate Int16 chunks.
   *
   * @param {Int16Array} a
   * @param {Int16Array} b
   * @returns {Int16Array}
   */
  function concatInt16(a, b) {
    const out = new Int16Array(a.length + b.length);
    out.set(a, 0);
    out.set(b, a.length);
    return out;
  }

  root.RuTatPcm = {
    TARGET_RATE: TARGET_RATE,
    downsampleTo16k: downsampleTo16k,
    floatToS16le: floatToS16le,
    arrayBufferToBase64: arrayBufferToBase64,
    concatInt16: concatInt16,
  };
})(typeof window !== "undefined" ? window : globalThis);
