/**
 * Signaling WebSocket + RTCPeerConnection mesh (step 3.2).
 *
 * Existing members send webrtc.offer to a joiner; the joiner only answers.
 * ICE uses sdpMid / sdpMLineIndex aliases expected by the server.
 */
(function (root) {
  const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];

  /**
   * Build the signaling WebSocket URL for the current page origin.
   *
   * @param {string} token Access token from login.
   * @returns {string}
   * @example
   * signalingWsUrl("abc");
   */
  function signalingWsUrl(token) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws/signaling?token=" + encodeURIComponent(token);
  }

  /**
   * Map RTCIceCandidate to the signaling payload (camelCase aliases).
   *
   * @param {RTCIceCandidate} cand
   * @returns {{candidate: string, sdpMid: string|null, sdpMLineIndex: number|null}}
   */
  function iceCandidatePayload(cand) {
    return {
      candidate: cand.candidate,
      sdpMid: cand.sdpMid,
      sdpMLineIndex: cand.sdpMLineIndex,
    };
  }

  /**
   * @param {object} hooks
   * @param {function(): string} hooks.token
   * @param {function(): {user_id: string}} hooks.me
   * @param {function(): MediaStream|null} hooks.localStream
   * @param {function(object): void} hooks.onInvite
   * @param {function(string): void} hooks.onPeerJoined
   * @param {function(string): void} hooks.onPeerLeft
   * @param {function(string, MediaStream): void} hooks.onRemoteStream
   * @param {function(string): void} hooks.onError
   * @param {function(string): void} [hooks.onRoomReady] Room id after create or accept.
   * @param {function(object): void} [hooks.onSubtitle] subtitle.update payload.
   * @param {function(string): void} [hooks.onStatus] Reconnect / ICE hint (empty clears).
   */
  function MeshClient(hooks) {
    this._hooks = hooks;
    this.ws = null;
    this.roomId = null;
    this.peers = {};
    this._req = 0;
    this._intentionalClose = false;
    this._reconnectTimer = null;
    this._attempt = 0;
    this._restarting = {};
  }

  MeshClient.prototype._nextId = function () {
    this._req += 1;
    return "req_" + this._req;
  };

  MeshClient.prototype.send = function (type, payload) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    this.ws.send(
      JSON.stringify({
        type: type,
        request_id: this._nextId(),
        timestamp: Math.floor(Date.now() / 1000),
        payload: payload,
      })
    );
  };

  /**
   * Open `/ws/signaling`. Keeps existing RTCPeerConnections on reconnect.
   *
   * @returns {Promise<void>}
   */
  MeshClient.prototype.connect = function () {
    const self = this;
    this._clearReconnectTimer();
    this._dropSocket();
    this._intentionalClose = false;
    return new Promise(function (resolve, reject) {
      const ws = new WebSocket(signalingWsUrl(self._hooks.token()));
      self.ws = ws;
      let settled = false;
      ws.onopen = function () {
        self._attempt = 0;
        settled = true;
        resolve();
      };
      ws.onerror = function () {
        if (!settled) {
          settled = true;
          reject(new Error("Signaling WebSocket error"));
        }
      };
      ws.onclose = function () {
        self.ws = null;
        if (!settled) {
          settled = true;
          reject(new Error("Signaling WebSocket closed"));
        }
        if (self._intentionalClose) {
          return;
        }
        if (self._hooks.onStatus) {
          self._hooks.onStatus("Переподключение сигнализации…");
        }
        self._scheduleReconnect();
      };
      ws.onmessage = function (ev) {
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch (e) {
          return;
        }
        self._onMessage(msg);
      };
    });
  };

  /**
   * Close the signaling socket without tearing down RTCPeerConnections.
   */
  MeshClient.prototype._dropSocket = function () {
    if (!this.ws) {
      return;
    }
    this.ws.onclose = null;
    this.ws.onmessage = null;
    this.ws.onerror = null;
    try {
      this.ws.close();
    } catch (e) {}
    this.ws = null;
  };

  MeshClient.prototype._clearReconnectTimer = function () {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  };

  /**
   * Retry `connect()` with exponential backoff, then ICE-restart all peers.
   */
  MeshClient.prototype._scheduleReconnect = function () {
    const self = this;
    if (this._intentionalClose || this._reconnectTimer) {
      return;
    }
    const delay = (root.RuTatReconnect && root.RuTatReconnect.nextDelay
      ? root.RuTatReconnect.nextDelay(this._attempt)
      : 500);
    this._attempt += 1;
    this._reconnectTimer = setTimeout(function () {
      self._reconnectTimer = null;
      self.connect()
        .then(function () {
          if (self._hooks.onStatus) {
            self._hooks.onStatus("");
          }
          return self.restartIceAll();
        })
        .catch(function () {
          self._scheduleReconnect();
        });
    }, delay);
  };

  MeshClient.prototype.disconnect = function () {
    this._intentionalClose = true;
    this._clearReconnectTimer();
    this._dropSocket();
    this.closePeers();
    this.roomId = null;
    this._attempt = 0;
  };

  MeshClient.prototype.closePeers = function () {
    const self = this;
    Object.keys(this.peers).forEach(function (id) {
      try {
        self.peers[id].pc.close();
      } catch (e) {}
    });
    this.peers = {};
  };

  MeshClient.prototype.closePeer = function (peerId) {
    const slot = this.peers[peerId];
    if (!slot) {
      return;
    }
    try {
      slot.pc.close();
    } catch (e) {}
    delete this.peers[peerId];
  };

  /**
   * Create a room and invite each selected user (must already be online).
   *
   * @param {string[]} participantIds Including self.
   * @param {string[]} inviteIds Contacts to call.invite.
   */
  MeshClient.prototype.startCall = function (participantIds, inviteIds) {
    this.send("room.create", { participant_ids: participantIds });
    this._pendingInvites = inviteIds.slice();
  };

  MeshClient.prototype.accept = function (roomId) {
    this.roomId = roomId;
    this.send("call.accept", { room_id: roomId });
    if (this._hooks.onRoomReady) {
      this._hooks.onRoomReady(roomId);
    }
  };

  MeshClient.prototype.reject = function (roomId, reason) {
    this.send("call.reject", { room_id: roomId, reason: reason || "declined" });
  };

  /**
   * Get or create a peer connection to `peerId` and attach local tracks.
   *
   * @param {string} peerId
   * @returns {{pc: RTCPeerConnection, pendingIce: object[]}}
   */
  MeshClient.prototype.ensurePeer = function (peerId) {
    const self = this;
    if (this.peers[peerId]) {
      return this.peers[peerId];
    }
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
    const slot = { pc: pc, pendingIce: [] };
    const stream = this._hooks.localStream();
    if (stream) {
      stream.getTracks().forEach(function (track) {
        pc.addTrack(track, stream);
      });
    }
    pc.onicecandidate = function (ev) {
      if (!ev.candidate || !self.roomId) {
        return;
      }
      self.send("webrtc.ice", {
        room_id: self.roomId,
        from_user_id: self._hooks.me().user_id,
        to_user_id: peerId,
        candidate: iceCandidatePayload(ev.candidate),
      });
    };
    pc.ontrack = function (ev) {
      const remote =
        ev.streams && ev.streams[0]
          ? ev.streams[0]
          : new MediaStream([ev.track]);
      self._hooks.onRemoteStream(peerId, remote);
    };
    pc.oniceconnectionstatechange = function () {
      if (pc.iceConnectionState === "failed") {
        self.restartIce(peerId);
      }
    };
    this.peers[peerId] = slot;
    return slot;
  };

  /**
   * ICE restart toward one peer (after signaling reconnect or ICE failed).
   *
   * @param {string} peerId
   * @returns {Promise<void>}
   */
  MeshClient.prototype.restartIce = async function (peerId) {
    const me = this._hooks.me();
    if (!this.roomId || !me || peerId === me.user_id) {
      return;
    }
    if (this._restarting[peerId]) {
      return;
    }
    const slot = this.peers[peerId];
    if (!slot) {
      return;
    }
    this._restarting[peerId] = true;
    try {
      const offer = await slot.pc.createOffer({ iceRestart: true });
      await slot.pc.setLocalDescription(offer);
      this.send("webrtc.offer", {
        room_id: this.roomId,
        from_user_id: me.user_id,
        to_user_id: peerId,
        sdp: slot.pc.localDescription.sdp,
      });
    } catch (e) {
    } finally {
      delete this._restarting[peerId];
    }
  };

  /**
   * ICE restart for every live peer.
   *
   * @returns {Promise<void>}
   */
  MeshClient.prototype.restartIceAll = async function () {
    const self = this;
    const ids = Object.keys(this.peers);
    for (let i = 0; i < ids.length; i++) {
      await self.restartIce(ids[i]);
    }
  };

  /**
   * Caller / existing member: offer toward a joiner.
   *
   * @param {string} peerId
   * @returns {Promise<void>}
   */
  MeshClient.prototype.offerTo = async function (peerId) {
    const me = this._hooks.me();
    if (!this.roomId || peerId === me.user_id) {
      return;
    }
    const slot = this.ensurePeer(peerId);
    const offer = await slot.pc.createOffer();
    await slot.pc.setLocalDescription(offer);
    this.send("webrtc.offer", {
      room_id: this.roomId,
      from_user_id: me.user_id,
      to_user_id: peerId,
      sdp: slot.pc.localDescription.sdp,
    });
  };

  MeshClient.prototype._flushIce = async function (slot) {
    while (slot.pendingIce.length) {
      const cand = slot.pendingIce.shift();
      try {
        await slot.pc.addIceCandidate(cand);
      } catch (e) {}
    }
  };

  MeshClient.prototype._onMessage = async function (msg) {
    const type = msg.type;
    const payload = msg.payload || {};
    const me = this._hooks.me();
    if (type === "error") {
      this._hooks.onError((payload && payload.message) || "Ошибка сигнализации");
      return;
    }
    if (type === "room.created") {
      this.roomId = payload.room_id;
      const invites = this._pendingInvites || [];
      this._pendingInvites = [];
      const self = this;
      invites.forEach(function (uid) {
        self.send("call.invite", { room_id: self.roomId, target_user_id: uid });
      });
      if (this._hooks.onRoomReady) {
        this._hooks.onRoomReady(this.roomId);
      }
      return;
    }
    if (type === "call.invite") {
      this._hooks.onInvite(payload);
      return;
    }
    if (type === "call.reject") {
      this._hooks.onError("Звонок отклонён");
      return;
    }
    if (type === "participant.joined") {
      if (payload.user_id === me.user_id) {
        return;
      }
      this._hooks.onPeerJoined(payload.user_id);
      await this.offerTo(payload.user_id);
      return;
    }
    if (type === "participant.left") {
      this.closePeer(payload.user_id);
      this._hooks.onPeerLeft(payload.user_id);
      return;
    }
    if (type === "webrtc.offer") {
      if (payload.to_user_id !== me.user_id) {
        return;
      }
      this.roomId = payload.room_id;
      const slot = this.ensurePeer(payload.from_user_id);
      await slot.pc.setRemoteDescription({ type: "offer", sdp: payload.sdp });
      await this._flushIce(slot);
      const answer = await slot.pc.createAnswer();
      await slot.pc.setLocalDescription(answer);
      this.send("webrtc.answer", {
        room_id: this.roomId,
        from_user_id: me.user_id,
        to_user_id: payload.from_user_id,
        sdp: slot.pc.localDescription.sdp,
      });
      this._hooks.onPeerJoined(payload.from_user_id);
      return;
    }
    if (type === "webrtc.answer") {
      if (payload.to_user_id !== me.user_id) {
        return;
      }
      const slot = this.peers[payload.from_user_id];
      if (!slot) {
        return;
      }
      await slot.pc.setRemoteDescription({ type: "answer", sdp: payload.sdp });
      await this._flushIce(slot);
      return;
    }
    if (type === "webrtc.ice") {
      if (payload.to_user_id !== me.user_id) {
        return;
      }
      const slot = this.ensurePeer(payload.from_user_id);
      const init = payload.candidate || {};
      const ice = {
        candidate: init.candidate,
        sdpMid: init.sdpMid || init.sdp_mid || null,
        sdpMLineIndex:
          init.sdpMLineIndex != null ? init.sdpMLineIndex : init.sdp_m_line_index,
      };
      if (!slot.pc.remoteDescription) {
        slot.pendingIce.push(ice);
        return;
      }
      try {
        await slot.pc.addIceCandidate(ice);
      } catch (e) {}
      return;
    }
    if (type === "subtitle.update") {
      if (this._hooks.onSubtitle) {
        this._hooks.onSubtitle(payload);
      }
    }
  };

  root.RuTatMesh = {
    ICE_SERVERS: ICE_SERVERS,
    signalingWsUrl: signalingWsUrl,
    iceCandidatePayload: iceCandidatePayload,
    MeshClient: MeshClient,
  };
})(window);
