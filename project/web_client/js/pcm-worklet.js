/**
 * AudioWorklet: capture input, downsample to 16 kHz s16le, post ArrayBuffer.
 *
 * Params (implicit): `inputs[0][0]` Float32 samples at `sampleRate`.
 * Posts: transferable ArrayBuffer of little-endian int16 PCM.
 */
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || !channel.length) {
      return true;
    }
    const inRate = sampleRate;
    const target = 16000;
    let f32 = channel;
    if (inRate !== target) {
      const ratio = inRate / target;
      const outLen = Math.max(1, Math.floor(channel.length / ratio));
      f32 = new Float32Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const pos = i * ratio;
        const i0 = Math.min(Math.floor(pos), channel.length - 1);
        const i1 = Math.min(i0 + 1, channel.length - 1);
        const frac = pos - i0;
        f32[i] = channel[i0] * (1 - frac) + channel[i1] * frac;
      }
    }
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
    this.port.postMessage(buf, [buf]);
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
