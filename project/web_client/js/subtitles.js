/**
 * Live subtitle store: in-place partials, frozen finals, speaker colors.
 */
(function (root) {
  const PALETTE = ["#3d9cf0", "#3ecf8e", "#e8b84a", "#c084fc"];
  const MAX_ROWS = 40;

  /**
   * Stable color for a speaker id (up to four distinct hues).
   *
   * @param {string} speakerId
   * @returns {string} CSS hex color
   * @example
   * speakerColor("u_you") === speakerColor("u_you")
   */
  function speakerColor(speakerId) {
    const s = speakerId || "";
    let h = 0;
    for (let i = 0; i < s.length; i++) {
      h = (h * 31 + s.charCodeAt(i)) >>> 0;
    }
    return PALETTE[h % PALETTE.length];
  }

  /**
   * @param {number} [maxRows]
   */
  function SubtitleStore(maxRows) {
    this.maxRows = maxRows || MAX_ROWS;
    this.items = [];
  }

  /**
   * Insert or update a subtitle by subtitle_id. Final rows are immutable.
   *
   * @param {object} payload subtitle.update / asr transcript body + status
   * @returns {{row: object, isNew: boolean}|null}
   * @example
   * const s = new SubtitleStore();
   * s.apply({subtitle_id: "sub_1", speaker_id: "u_you", speaker_name: "Ты",
   *          text: "Привет", status: "partial"});
   * s.apply({subtitle_id: "sub_1", speaker_id: "u_you", speaker_name: "Ты",
   *          text: "Привет всем", status: "final"});
   */
  SubtitleStore.prototype.apply = function (payload) {
    if (!payload || !payload.subtitle_id) {
      return null;
    }
    const id = String(payload.subtitle_id);
    const status = payload.status === "final" ? "final" : "partial";
    const text = payload.text == null ? "" : String(payload.text);
    if (!text) {
      return null;
    }
    let i;
    for (i = 0; i < this.items.length; i++) {
      if (this.items[i].id === id) {
        break;
      }
    }
    if (i < this.items.length) {
      const row = this.items[i];
      if (row.status === "final") {
        return { row: row, isNew: false, dropped: [] };
      }
      row.text = text;
      row.status = status;
      row.speakerId = payload.speaker_id || row.speakerId;
      row.speakerName = payload.speaker_name || row.speakerName;
      row.language = payload.language || row.language;
      return { row: row, isNew: false, dropped: [] };
    }
    const row = {
      id: id,
      speakerId: payload.speaker_id || "",
      speakerName: payload.speaker_name || payload.speaker_id || "?",
      text: text,
      status: status,
      language: payload.language || "unknown",
    };
    this.items.push(row);
    const dropped = [];
    while (this.items.length > this.maxRows) {
      dropped.push(this.items.shift().id);
    }
    return { row: row, isNew: true, dropped: dropped };
  };

  SubtitleStore.prototype.clear = function () {
    this.items = [];
  };

  /**
   * Overlay widget bound to a scrollable list element.
   *
   * @param {HTMLElement} listEl
   * @param {HTMLElement} [panelEl] Hidden until the first line.
   */
  function SubtitleWidget(listEl, panelEl) {
    this.list = listEl;
    this.panel = panelEl || null;
    this.store = new SubtitleStore(MAX_ROWS);
    this._stick = true;
    const self = this;
    if (this.list) {
      this.list.addEventListener("scroll", function () {
        const el = self.list;
        self._stick = el.scrollHeight - el.scrollTop - el.clientHeight < 56;
      });
    }
  }

  /**
   * Build or update one DOM row.
   *
   * @param {object} row
   * @param {boolean} isNew
   */
  SubtitleWidget.prototype._paint = function (row, isNew) {
    const id = row.id;
    let el = this.list.querySelector('[data-sub-id="' + id.replace(/"/g, "") + '"]');
    if (!el) {
      el = document.createElement("p");
      el.className = "subtitle-row";
      el.setAttribute("data-sub-id", id);
      const badge = document.createElement("span");
      badge.className = "subtitle-badge";
      const text = document.createElement("span");
      text.className = "subtitle-text";
      el.appendChild(badge);
      el.appendChild(text);
      this.list.appendChild(el);
    }
    el.classList.toggle("partial", row.status !== "final");
    el.classList.toggle("final", row.status === "final");
    el.style.setProperty("--speaker", speakerColor(row.speakerId));
    el.querySelector(".subtitle-badge").textContent = row.speakerName;
    el.querySelector(".subtitle-text").textContent = row.text;
    if (this.panel) {
      this.panel.hidden = false;
    }
    if (this._stick) {
      try {
        this.list.scrollTo({ top: this.list.scrollHeight, behavior: isNew ? "smooth" : "auto" });
      } catch (e) {
        this.list.scrollTop = this.list.scrollHeight;
      }
    }
  };

  /**
   * Apply a live event. No-ops on empty payload.
   *
   * @param {object} payload
   */
  SubtitleWidget.prototype.apply = function (payload) {
    if (!this.list) {
      return;
    }
    const result = this.store.apply(payload);
    if (!result) {
      return;
    }
    (result.dropped || []).forEach(function (dropId) {
      const old = this.list.querySelector('[data-sub-id="' + String(dropId).replace(/"/g, "") + '"]');
      if (old) {
        old.remove();
      }
    }, this);
    this._paint(result.row, result.isNew);
  };

  SubtitleWidget.prototype.clear = function () {
    this.store.clear();
    this._stick = true;
    if (this.list) {
      this.list.innerHTML = "";
    }
    if (this.panel) {
      this.panel.hidden = true;
    }
  };

  /**
   * Map asr.partial / asr.final into a subtitle payload.
   *
   * @param {string} type
   * @param {object} payload
   * @returns {object|null}
   */
  function fromAsrEvent(type, payload) {
    if (type !== "asr.partial" && type !== "asr.final") {
      return null;
    }
    return {
      subtitle_id: payload.subtitle_id,
      speaker_id: payload.speaker_id,
      speaker_name: payload.speaker_name,
      text: payload.text,
      status: type === "asr.final" ? "final" : "partial",
      language: payload.language,
    };
  }

  root.RuTatSubtitles = {
    PALETTE: PALETTE,
    speakerColor: speakerColor,
    SubtitleStore: SubtitleStore,
    SubtitleWidget: SubtitleWidget,
    fromAsrEvent: fromAsrEvent,
  };
})(typeof window !== "undefined" ? window : globalThis);
