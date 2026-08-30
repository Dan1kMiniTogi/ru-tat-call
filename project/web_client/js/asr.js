/**
 * ASR WebSocket client: asr.start / asr.audio / asr.stop. Failures must not drop the call.
 */
(function (root) {
  const CHUNK_SAMPLES = 8000;

  /**
   * @param {object} opts
   * @param {string} opts.baseUrl ws://host:8001/v1/stream (no query)
   * @param {function(): string} opts.token
   * @param {function(): boolean} opts.micOn
   * @param {function(string): void} [opts.onError]
   */
  function AsrClient(opts) {
    this._opts = opts;
    this.ws = null;
    this.sessionId = "";
    this.roomId = "";
    this._chunk = 0;
    this._buf = new Int16Array(0);
    this._started = false;
  }

  AsrClient.prototype._send = function (obj) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    try {
      this.ws.send(JSON.stringify(obj));
    } catch (e) {}
  };

  /**
   * Open `/v1/stream` and send asr.start. Swallows errors (call stays up).
   *
   * @param {string} roomId
   * @returns {Promise<boolean>} true if the session started
   */
  AsrClient.prototype.start = function (roomId) {
    const self = this;
    this.stop();
    this.roomId = roomId;
    this.sessionId = "asr_" + Math.random().toString(36).slice(2, 10);
    this._chunk = 0;
    this._buf = new Int16Array(0);
    const url =
      this._opts.baseUrl.replace(/\/$/, "") +
      "?token=" +
      encodeURIComponent(this._opts.token());
    return new Promise(function (resolve) {
      let ws;
      try {
        ws = new WebSocket(url);
      } catch (e) {
        if (self._opts.onError) {
          self._opts.onError("Субтитры недоступны");
        }
        resolve(false);
        return;
      }
      self.ws = ws;
      let settled = false;
      const finish = function (ok) {
        if (settled) {
          return;
        }
        settled = true;
        resolve(ok);
      };
      const timer = setTimeout(function () {
        finish(false);
      }, 4000);
      ws.onopen = function () {
        self._send({
          type: "asr.start",
          session_id: self.sessionId,
          payload: {
            room_id: roomId,
            language_mode: "auto",
            return_partial: true,
            return_final: true,
            speaker_labels: true,
          },
        });
        self._started = true;
        clearTimeout(timer);
        finish(true);
      };
      ws.onerror = function () {
        clearTimeout(timer);
        if (self._opts.onError) {
          self._opts.onError("Субтитры недоступны");
        }
        finish(false);
      };
      ws.onclose = function () {
        self._started = false;
      };
      ws.onmessage = function () {};
    });
  };

  /**
   * Buffer s16le samples and flush ~500 ms frames as asr.audio.
   *
   * @param {Int16Array} samples
   */
  AsrClient.prototype.pushSamples = function (samples) {
    if (!this._started || !samples || !samples.length) {
      return;
    }
    if (this._opts.micOn && !this._opts.micOn()) {
      return;
    }
    this._buf = root.RuTatPcm.concatInt16(this._buf, samples);
    while (this._buf.length >= CHUNK_SAMPLES) {
      const frame = this._buf.subarray(0, CHUNK_SAMPLES);
      this._buf = this._buf.subarray(CHUNK_SAMPLES);
      this._chunk += 1;
      const copy = new Int16Array(frame.length);
      copy.set(frame);
      this._send({
        type: "asr.audio",
        session_id: this.sessionId,
        payload: {
          chunk_id: "chunk_" + this._chunk,
          timestamp: Math.floor(Date.now() / 1000),
          sample_rate: 16000,
          channels: 1,
          encoding: "pcm_s16le",
          audio_base64: root.RuTatPcm.arrayBufferToBase64(copy.buffer),
        },
      });
    }
  };

  /**
   * Send leftover PCM, asr.stop, close the socket.
   */
  AsrClient.prototype.stop = function () {
    if (this._started && this._buf.length) {
      const copy = new Int16Array(this._buf.length);
      copy.set(this._buf);
      this._chunk += 1;
      this._send({
        type: "asr.audio",
        session_id: this.sessionId,
        payload: {
          chunk_id: "chunk_" + this._chunk,
          timestamp: Math.floor(Date.now() / 1000),
          sample_rate: 16000,
          channels: 1,
          encoding: "pcm_s16le",
          audio_base64: root.RuTatPcm.arrayBufferToBase64(copy.buffer),
        },
      });
    }
    if (this._started) {
      this._send({
        type: "asr.stop",
        session_id: this.sessionId,
        payload: { room_id: this.roomId },
      });
    }
    this._started = false;
    this._buf = new Int16Array(0);
    if (this.ws) {
      try {
        this.ws.onclose = null;
        this.ws.close();
      } catch (e) {}
      this.ws = null;
    }
  };

  root.RuTatAsr = {
    CHUNK_SAMPLES: CHUNK_SAMPLES,
    AsrClient: AsrClient,
  };
})(typeof window !== "undefined" ? window : globalThis);
