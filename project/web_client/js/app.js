/**
 * Mobile-first call UI: login, contacts, 2x2 room, WebRTC, ASR PCM, live subtitles (step 3.4).
 */
(function () {
  const DEMO_USERS = [
    { id: "you", label: "Ты" },
    { id: "mama", label: "Mama" },
    { id: "sister", label: "Сестра" },
  ];
  const TOKEN_KEY = "ru_tat_call_token";
  const MAX_TILES = 4;

  const views = {
    login: document.getElementById("view-login"),
    home: document.getElementById("view-home"),
    room: document.getElementById("view-room"),
  };

  const state = {
    token: sessionStorage.getItem(TOKEN_KEY) || "",
    me: null,
    contacts: [],
    selectedIds: new Set(),
    remoteIds: [],
    remoteStreams: {},
    localStream: null,
    micOn: true,
    camOn: true,
    pendingInvite: null,
    mesh: null,
    asrWsUrl: "",
    asr: null,
    pcmCapture: null,
    subtitles: null,
  };

  /**
   * POST /v1/auth/login and return tokens.
   *
   * @param {string} identifier Login (`you`, `mama`, `sister`).
   * @param {string} password Demo password is `family`.
   * @returns {Promise<{access_token: string, user_id: string}>}
   */
  async function apiLogin(identifier, password) {
    const res = await fetch("/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, password }),
    });
    const body = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      const detail = body.detail;
      const msg =
        detail && typeof detail === "object" && detail.message
          ? detail.message
          : "Неверный логин или пароль";
      throw new Error(msg);
    }
    return body;
  }

  /**
   * Authenticated GET helper.
   *
   * @param {string} path Absolute API path.
   * @returns {Promise<object>}
   */
  async function apiGet(path) {
    const res = await fetch(path, {
      headers: { Authorization: "Bearer " + state.token },
    });
    if (res.status === 401) {
      logout();
      throw new Error("Сессия истекла");
    }
    if (!res.ok) {
      throw new Error("Ошибка запроса " + path);
    }
    return res.json();
  }

  /**
   * Show one of login | home | room.
   *
   * @param {"login"|"home"|"room"} name
   */
  function showView(name) {
    Object.keys(views).forEach(function (key) {
      views[key].hidden = key !== name;
    });
  }

  function displayName(userId) {
    if (state.me && userId === state.me.user_id) {
      return state.me.display_name;
    }
    const hit = state.contacts.find(function (c) {
      return c.user_id === userId;
    });
    return (hit && hit.display_name) || userId;
  }

  function setHint(text) {
    const hint = document.getElementById("media-hint");
    if (!text) {
      hint.hidden = true;
      hint.textContent = "";
      return;
    }
    hint.textContent = text;
    hint.hidden = false;
  }

  function hideIncoming() {
    document.getElementById("incoming-call").hidden = true;
    state.pendingInvite = null;
  }

  function showIncoming(payload) {
    state.pendingInvite = payload;
    document.getElementById("incoming-text").textContent = "Входящий звонок";
    document.getElementById("incoming-call").hidden = false;
  }

  /**
   * Create MeshClient bound to current token/me/localStream.
   *
   * @returns {object}
   */
  function createMesh() {
    return new window.RuTatMesh.MeshClient({
      token: function () {
        return state.token;
      },
      me: function () {
        return state.me;
      },
      localStream: function () {
        return state.localStream;
      },
      onInvite: function (payload) {
        if (views.room.hidden === false) {
          state.mesh.reject(payload.room_id, "busy");
          return;
        }
        showIncoming(payload);
      },
      onPeerJoined: function (userId) {
        if (state.remoteIds.indexOf(userId) === -1) {
          state.remoteIds.push(userId);
        }
        renderGrid();
      },
      onPeerLeft: function (userId) {
        state.remoteIds = state.remoteIds.filter(function (id) {
          return id !== userId;
        });
        delete state.remoteStreams[userId];
        renderGrid();
      },
      onRemoteStream: function (userId, stream) {
        state.remoteStreams[userId] = stream;
        if (state.remoteIds.indexOf(userId) === -1) {
          state.remoteIds.push(userId);
        }
        renderGrid();
      },
      onError: function (message) {
        setHint(message);
      },
      onRoomReady: function (roomId) {
        startAsrPipeline(roomId).catch(function () {
          setHint("Субтитры недоступны");
        });
      },
      onSubtitle: function (payload) {
        if (state.subtitles) {
          state.subtitles.apply(payload);
        }
      },
    });
  }

  /**
   * GET /v1/client-config (public). Caches asr_ws_url.
   *
   * @returns {Promise<string>}
   */
  async function loadAsrWsUrl() {
    if (state.asrWsUrl) {
      return state.asrWsUrl;
    }
    const res = await fetch("/v1/client-config");
    if (!res.ok) {
      throw new Error("no client-config");
    }
    const body = await res.json();
    state.asrWsUrl = body.asr_ws_url || "";
    if (!state.asrWsUrl) {
      throw new Error("empty asr_ws_url");
    }
    return state.asrWsUrl;
  }

  /**
   * Stop ASR WS and AudioWorklet. Does not touch WebRTC.
   */
  function stopAsrPipeline() {
    if (state.pcmCapture) {
      try {
        state.pcmCapture.stop();
      } catch (e) {}
      state.pcmCapture = null;
    }
    if (state.asr) {
      try {
        state.asr.stop();
      } catch (e) {}
      state.asr = null;
    }
  }

  /**
   * Open ASR /v1/stream and pipe 16 kHz PCM. Failures only set a hint.
   *
   * @param {string} roomId
   * @returns {Promise<void>}
   */
  async function startAsrPipeline(roomId) {
    stopAsrPipeline();
    const stream = state.localStream;
    if (!stream || !stream.getAudioTracks().length) {
      return;
    }
    let baseUrl;
    try {
      baseUrl = await loadAsrWsUrl();
    } catch (e) {
      setHint("Субтитры недоступны");
      return;
    }
    const client = new window.RuTatAsr.AsrClient({
      baseUrl: baseUrl,
      token: function () {
        return state.token;
      },
      micOn: function () {
        return state.micOn;
      },
      onError: function (message) {
        setHint(message);
      },
      onTranscript: function (payload) {
        if (state.subtitles) {
          state.subtitles.apply(payload);
        }
      },
    });
    const ok = await client.start(roomId);
    if (!ok) {
      setHint("Субтитры недоступны");
      return;
    }
    state.asr = client;
    try {
      state.pcmCapture = await window.startPcmCapture(stream, function (samples) {
        if (state.asr) {
          state.asr.pushSamples(samples);
        }
      });
    } catch (e) {
      client.stop();
      state.asr = null;
      setHint("Субтитры недоступны");
    }
  }

  function logout() {
    hideIncoming();
    stopAsrPipeline();
    clearSubtitles();
    if (state.mesh) {
      state.mesh.disconnect();
      state.mesh = null;
    }
    stopLocalMedia();
    state.token = "";
    state.me = null;
    state.contacts = [];
    state.remoteIds = [];
    state.remoteStreams = {};
    sessionStorage.removeItem(TOKEN_KEY);
    document.getElementById("login-error").hidden = true;
    showView("login");
  }

  /**
   * Stop camera/mic tracks from the self tile.
   */
  function stopLocalMedia() {
    if (state.localStream) {
      state.localStream.getTracks().forEach(function (t) {
        t.stop();
      });
      state.localStream = null;
    }
    state.micOn = true;
    state.camOn = true;
  }

  /**
   * Apply mic/camera enabled flags to local tracks and button pressed state.
   */
  function syncMediaButtons() {
    const micBtn = document.getElementById("btn-mic");
    const camBtn = document.getElementById("btn-cam");
    micBtn.setAttribute("aria-pressed", state.micOn ? "true" : "false");
    camBtn.setAttribute("aria-pressed", state.camOn ? "true" : "false");
    micBtn.textContent = state.micOn ? "Мик" : "Мик выкл";
    camBtn.textContent = state.camOn ? "Кам" : "Кам выкл";
    if (!state.localStream) {
      return;
    }
    state.localStream.getAudioTracks().forEach(function (t) {
      t.enabled = state.micOn;
    });
    state.localStream.getVideoTracks().forEach(function (t) {
      t.enabled = state.camOn;
    });
  }

  /**
   * Request camera+mic for the self tile.
   *
   * @returns {Promise<void>}
   */
  async function startLocalPreview() {
    setHint("");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setHint("Камера недоступна в этом браузере. Звонок всё равно можно начать.");
      return;
    }
    try {
      state.localStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: { facingMode: "user" },
      });
    } catch (err) {
      setHint("Нет доступа к камере/микрофону — P2P без своего видео.");
      return;
    }
    attachLocalVideo();
    syncMediaButtons();
  }

  function attachLocalVideo() {
    const video = document.getElementById("local-video");
    if (video && state.localStream) {
      video.srcObject = state.localStream;
      video.muted = true;
      video.playsInline = true;
      video.play().catch(function () {});
    }
  }

  /**
   * Render 2x2 tiles: self + remotes with live streams + empty slots.
   */
  function renderGrid() {
    const grid = document.getElementById("video-grid");
    grid.innerHTML = "";
    const slots = [{ kind: "self", name: (state.me && state.me.display_name) || "Вы" }];
    state.remoteIds.slice(0, MAX_TILES - 1).forEach(function (id) {
      slots.push({ kind: "remote", userId: id, name: displayName(id) });
    });
    while (slots.length < MAX_TILES) {
      slots.push({ kind: "empty", name: "Свободно" });
    }
    slots.forEach(function (slot, index) {
      const tile = document.createElement("article");
      tile.className = "tile";
      if (slot.kind === "self") {
        const video = document.createElement("video");
        video.id = "local-video";
        video.autoplay = true;
        video.muted = true;
        video.setAttribute("playsinline", "");
        tile.appendChild(video);
      } else if (slot.kind === "remote") {
        const video = document.createElement("video");
        video.id = "remote-" + slot.userId;
        video.autoplay = true;
        video.setAttribute("playsinline", "");
        if (state.remoteStreams[slot.userId]) {
          video.srcObject = state.remoteStreams[slot.userId];
        }
        tile.appendChild(video);
      } else {
        const ph = document.createElement("div");
        ph.className = "placeholder";
        ph.textContent = "Ожидание участника";
        tile.appendChild(ph);
      }
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = slot.name;
      tile.appendChild(badge);
      tile.dataset.slot = String(index);
      grid.appendChild(tile);
    });
    attachLocalVideo();
    state.remoteIds.forEach(function (id) {
      const el = document.getElementById("remote-" + id);
      if (el && state.remoteStreams[id]) {
        el.srcObject = state.remoteStreams[id];
        el.play().catch(function () {});
      }
    });
  }

  function renderContacts() {
    const list = document.getElementById("contact-list");
    list.innerHTML = "";
    state.contacts.forEach(function (c) {
      const li = document.createElement("li");
      li.className = "contact";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.selectedIds.has(c.user_id);
      cb.addEventListener("change", function () {
        if (cb.checked) {
          if (state.selectedIds.size >= MAX_TILES - 1) {
            cb.checked = false;
            return;
          }
          state.selectedIds.add(c.user_id);
        } else {
          state.selectedIds.delete(c.user_id);
        }
      });
      const av = document.createElement("span");
      av.className = "avatar";
      av.textContent = (c.display_name || "?").slice(0, 1);
      const name = document.createElement("span");
      name.textContent = c.display_name;
      li.appendChild(cb);
      li.appendChild(av);
      li.appendChild(name);
      list.appendChild(li);
    });
  }

  async function ensureMesh() {
    if (!state.mesh) {
      state.mesh = createMesh();
    }
    await state.mesh.connect();
  }

  /**
   * Bind the overlay once; DOM nodes live in the room view.
   *
   * @returns {object}
   */
  function ensureSubtitleWidget() {
    if (!state.subtitles) {
      state.subtitles = new window.RuTatSubtitles.SubtitleWidget(
        document.getElementById("subtitle-list"),
        document.getElementById("subtitle-panel")
      );
    }
    return state.subtitles;
  }

  function clearSubtitles() {
    if (state.subtitles) {
      state.subtitles.clear();
    }
  }

  async function enterHome() {
    state.me = await apiGet("/v1/users/me");
    const contacts = await apiGet("/v1/contacts");
    state.contacts = contacts.items || [];
    document.getElementById("home-name").textContent = state.me.display_name;
    renderContacts();
    showView("home");
    await ensureMesh();
  }

  async function enterRoomAsCaller() {
    ensureSubtitleWidget().clear();
    state.remoteIds = [];
    state.remoteStreams = {};
    renderGrid();
    showView("room");
    await startLocalPreview();
    renderGrid();
    const ids = [state.me.user_id].concat(Array.from(state.selectedIds));
    const invites = Array.from(state.selectedIds);
    if (!state.mesh || !state.mesh.ws || state.mesh.ws.readyState !== WebSocket.OPEN) {
      throw new Error("Нет сигнализации — обновите страницу");
    }
    state.mesh.startCall(ids, invites);
  }

  async function enterRoomAsCallee(roomId) {
    ensureSubtitleWidget().clear();
    state.remoteIds = [];
    state.remoteStreams = {};
    renderGrid();
    showView("room");
    await startLocalPreview();
    renderGrid();
    state.mesh.accept(roomId);
  }

  async function hangup() {
    hideIncoming();
    stopAsrPipeline();
    clearSubtitles();
    if (state.mesh) {
      state.mesh.disconnect();
    }
    stopLocalMedia();
    state.remoteIds = [];
    state.remoteStreams = {};
    setHint("");
    showView("home");
    state.mesh = createMesh();
    try {
      await state.mesh.connect();
    } catch (e) {
      setHint("Не удалось заново открыть сигнализацию");
    }
  }

  function bindLoginChips() {
    const wrap = document.getElementById("login-chips");
    wrap.innerHTML = "";
    DEMO_USERS.forEach(function (u) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip";
      btn.textContent = u.label;
      btn.addEventListener("click", function () {
        document.getElementById("login-id").value = u.id;
        document.getElementById("login-password").value = "family";
      });
      wrap.appendChild(btn);
    });
  }

  document.getElementById("login-form").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const err = document.getElementById("login-error");
    err.hidden = true;
    try {
      const session = await apiLogin(
        document.getElementById("login-id").value.trim(),
        document.getElementById("login-password").value
      );
      state.token = session.access_token;
      sessionStorage.setItem(TOKEN_KEY, state.token);
      await enterHome();
    } catch (ex) {
      err.textContent = ex.message || "Ошибка входа";
      err.hidden = false;
    }
  });

  document.getElementById("btn-logout").addEventListener("click", logout);
  document.getElementById("btn-start-call").addEventListener("click", function () {
    enterRoomAsCaller().catch(function (e) {
      setHint(e.message || "Не удалось начать звонок");
    });
  });
  document.getElementById("btn-hangup").addEventListener("click", function () {
    hangup().catch(function () {});
  });
  document.getElementById("btn-mic").addEventListener("click", function () {
    state.micOn = !state.micOn;
    syncMediaButtons();
  });
  document.getElementById("btn-cam").addEventListener("click", function () {
    state.camOn = !state.camOn;
    syncMediaButtons();
  });
  document.getElementById("btn-accept").addEventListener("click", function () {
    const payload = state.pendingInvite;
    hideIncoming();
    if (!payload) {
      return;
    }
    enterRoomAsCallee(payload.room_id).catch(function (e) {
      setHint(e.message || "Не удалось принять звонок");
    });
  });
  document.getElementById("btn-reject").addEventListener("click", function () {
    const payload = state.pendingInvite;
    hideIncoming();
    if (payload && state.mesh) {
      state.mesh.reject(payload.room_id, "declined");
    }
  });

  bindLoginChips();
  ensureSubtitleWidget();
  if (state.token) {
    enterHome().catch(function () {
      logout();
    });
  } else {
    showView("login");
  }
})();
