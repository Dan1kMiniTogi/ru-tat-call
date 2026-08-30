/**
 * Mobile-first call UI (step 3.1): login, contacts, 2x2 room, mic/camera.
 * WebRTC mesh is step 3.2 — here only local getUserMedia preview.
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
    localStream: null,
    micOn: true,
    camOn: true,
  };

  /**
   * POST /v1/auth/login and return tokens.
   *
   * @param {string} identifier Login (`you`, `mama`, `sister`).
   * @param {string} password Demo password is `family`.
   * @returns {Promise<{access_token: string, user_id: string}>}
   * @example
   * const session = await apiLogin("you", "family");
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

  /**
   * Parse FastAPI error payload `{detail: {code, message}}`.
   *
   * @param {unknown} detail
   * @returns {string|undefined}
   */
  function errorMessage(detail) {
    if (detail && typeof detail === "object" && detail.message) {
      return detail.message;
    }
    return undefined;
  }

  function logout() {
    stopLocalMedia();
    state.token = "";
    state.me = null;
    state.contacts = [];
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
   * Request camera+mic for the self tile. Failures keep the call UI (ASR/call rule analog).
   *
   * @returns {Promise<void>}
   */
  async function startLocalPreview() {
    const hint = document.getElementById("media-hint");
    hint.hidden = true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      hint.textContent = "Камера недоступна в этом браузере. Сетка всё равно открыта.";
      hint.hidden = false;
      return;
    }
    try {
      state.localStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: { facingMode: "user" },
      });
    } catch (err) {
      hint.textContent = "Нет доступа к камере/микрофону — можно продолжить без превью.";
      hint.hidden = false;
      return;
    }
    const video = document.getElementById("local-video");
    if (video) {
      video.srcObject = state.localStream;
      video.muted = true;
      video.playsInline = true;
      video.play().catch(function () {});
    }
    syncMediaButtons();
  }

  /**
   * Render 2x2 tiles: self + selected contacts + empty slots (max 4).
   */
  function renderGrid() {
    const grid = document.getElementById("video-grid");
    grid.innerHTML = "";
    const others = state.contacts.filter(function (c) {
      return state.selectedIds.has(c.user_id);
    });
    const slots = [{ kind: "self", name: (state.me && state.me.display_name) || "Вы" }];
    others.slice(0, MAX_TILES - 1).forEach(function (c) {
      slots.push({ kind: "remote", name: c.display_name });
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
      } else {
        const ph = document.createElement("div");
        ph.className = "placeholder";
        ph.textContent = slot.kind === "empty" ? "Ожидание участника" : "Нет видео (шаг 3.2)";
        tile.appendChild(ph);
      }
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = slot.name;
      tile.appendChild(badge);
      tile.dataset.slot = String(index);
      grid.appendChild(tile);
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

  async function enterHome() {
    state.me = await apiGet("/v1/users/me");
    const contacts = await apiGet("/v1/contacts");
    state.contacts = contacts.items || [];
    document.getElementById("home-name").textContent = state.me.display_name;
    renderContacts();
    showView("home");
  }

  async function enterRoom() {
    renderGrid();
    showView("room");
    await startLocalPreview();
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
      err.textContent = errorMessage(ex.detail) || ex.message || "Ошибка входа";
      err.hidden = false;
    }
  });

  document.getElementById("btn-logout").addEventListener("click", logout);
  document.getElementById("btn-start-call").addEventListener("click", function () {
    enterRoom().catch(function () {});
  });
  document.getElementById("btn-hangup").addEventListener("click", function () {
    stopLocalMedia();
    showView("home");
  });
  document.getElementById("btn-mic").addEventListener("click", function () {
    state.micOn = !state.micOn;
    syncMediaButtons();
  });
  document.getElementById("btn-cam").addEventListener("click", function () {
    state.camOn = !state.camOn;
    syncMediaButtons();
  });

  bindLoginChips();
  if (state.token) {
    enterHome().catch(function () {
      logout();
    });
  } else {
    showView("login");
  }
})();
