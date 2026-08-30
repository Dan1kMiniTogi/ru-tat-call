/**
 * Capture microphone via AudioWorklet, fallback ScriptProcessor.
 *
 * @param {MediaStream} stream Local getUserMedia stream (audio track).
 * @param {function(Int16Array): void} onSamples 16 kHz s16le samples.
 * @returns {Promise<{stop: function(): void}>}
 * @example
 * const cap = await startPcmCapture(stream, (s16) => asr.pushSamples(s16));
 * cap.stop();
 */
async function startPcmCapture(stream, onSamples) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  await ctx.resume();
  const source = ctx.createMediaStreamSource(stream);
  const mute = ctx.createGain();
  mute.gain.value = 0;
  mute.connect(ctx.destination);

  function handleS16Buffer(buf) {
    onSamples(new Int16Array(buf));
  }

  try {
    await ctx.audioWorklet.addModule("/js/pcm-worklet.js");
    const node = new AudioWorkletNode(ctx, "pcm-capture");
    node.port.onmessage = function (ev) {
      handleS16Buffer(ev.data);
    };
    source.connect(node);
    node.connect(mute);
    return {
      stop: function () {
        try {
          node.disconnect();
          source.disconnect();
          mute.disconnect();
          ctx.close();
        } catch (e) {}
      },
    };
  } catch (e) {
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = function (ev) {
      const input = ev.inputBuffer.getChannelData(0);
      const f32 = window.RuTatPcm.downsampleTo16k(input, ctx.sampleRate);
      handleS16Buffer(window.RuTatPcm.floatToS16le(f32));
    };
    source.connect(proc);
    proc.connect(mute);
    return {
      stop: function () {
        try {
          proc.disconnect();
          source.disconnect();
          mute.disconnect();
          ctx.close();
        } catch (err) {}
      },
    };
  }
}

window.startPcmCapture = startPcmCapture;
