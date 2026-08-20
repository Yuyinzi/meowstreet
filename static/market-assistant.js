(function () {
  const API_URL = "/api/market-assistant/questions/stream";
  const STORAGE_KEY = "meowstreet_market_assistant_v1";

  const state = {
    lastContextId: null,
    conversationId: null,
    serverHistoryReady: false,
    messages: [],
    busy: false,
    error: null,
    externalSearchRequested: false,
    deepResearchRequested: false,
    deepAnalysisRequested: false,
    isOpen: false,
    windowRect: { width: 360, height: 520, right: 24, bottom: 92 },
  };

  const CITATION_TARGET_ATTR = 'target="_blank"';
  const CITATION_REL_ATTR = 'rel="noopener noreferrer"';
  const CITATION_SECURITY_ATTRS = [CITATION_TARGET_ATTR, CITATION_REL_ATTR];

  const ALLOWED_ASSISTANT_TAGS = new Set([
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "P",
    "UL",
    "OL",
    "LI",
    "STRONG",
    "EM",
    "CODE",
    "PRE",
    "BLOCKQUOTE",
    "A",
    "TABLE",
    "THEAD",
    "TBODY",
    "TR",
    "TH",
    "TD",
    "BR",
    "HR",
  ]);

  const ALLOWED_ASSISTANT_ATTRIBUTES = new Set([
    "href",
    "title",
    "align",
    "colspan",
    "rowspan",
  ]);

  const THINKING_TEXT = "Thinking…";
  const COMPLETION_NOTICE = "已生成回答";
  const FAILED_NOTICE = "当前出现错误，请重试";
  const RETRY_LABEL = "重试";

  const PROGRESS_STAGES = [
    "reading_setup",
    "checking_confirmation",
    "querying_history",
    "comparing_evidence",
    "writing_answer",
  ];

  const VALIDATION_BADGE_TEXT = {
    passed: "已通过 Market Setup 证据验证",
    repaired_and_passed: "修复后已通过验证",
    failed: "未通过完整证据验证",
    disabled: "Claim validation 当前已关闭",
    unavailable: "验证不可用，回答未验证",
  };

  const VALIDATION_BADGE_CLASS = {
    passed: "market-assistant-validation-passed",
    repaired_and_passed: "market-assistant-validation-passed",
    failed: "market-assistant-validation-failed",
    disabled: "market-assistant-validation-disabled",
    unavailable: "market-assistant-validation-unavailable",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function elements() {
    return {
      fab: $("marketAssistantFab"),
      window: $("marketAssistantWindow"),
      head: $("marketAssistantWindowHead"),
      close: $("marketAssistantWindowClose"),
      newConversation: $("marketAssistantNewConversation"),
      log: $("marketAssistantLog"),
      form: $("marketAssistantForm"),
      question: $("marketAssistantQuestion"),
      submit: $("marketAssistantSubmit"),
      externalSearch: $("marketAssistantExternalSearch"),
      deepResearch: $("marketAssistantDeepResearch"),
      deepAnalysis: $("marketAssistantDeepAnalysis"),
      status: $("marketAssistantStatus"),
      validationDisabledNotice: $("marketAssistantValidationDisabledNotice"),
    };
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function saveState() {
    try {
      const payload = {
        conversationId: state.conversationId,
        serverHistoryReady: state.serverHistoryReady,
        messages: state.messages,
        lastContextId: state.lastContextId,
        isOpen: state.isOpen,
        windowRect: state.windowRect,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
      console.warn("market assistant state save failed", error);
    }
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const payload = JSON.parse(raw);
      if (payload.conversationId) state.conversationId = payload.conversationId;
      if (typeof payload.serverHistoryReady === "boolean") {
        state.serverHistoryReady = payload.serverHistoryReady;
      }
      if (Array.isArray(payload.messages)) state.messages = payload.messages;
      if (payload.lastContextId) state.lastContextId = payload.lastContextId;
      if (typeof payload.isOpen === "boolean") state.isOpen = payload.isOpen;
      if (payload.windowRect) state.windowRect = payload.windowRect;
      return true;
    } catch (error) {
      console.warn("market assistant state load failed", error);
      return false;
    }
  }

  function isMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 820px)").matches;
  }

  function applyWindowRect() {
    const el = elements();
    if (!el.window || !el.window.style) return;
    if (isMobileViewport()) {
      el.window.style.width = "";
      el.window.style.height = "";
      el.window.style.right = "";
      el.window.style.bottom = "";
      el.window.style.left = "";
      return;
    }
    const rect = state.windowRect;
    el.window.style.width = rect.width + "px";
    el.window.style.height = rect.height + "px";
    el.window.style.right = rect.right + "px";
    el.window.style.bottom = rect.bottom + "px";
  }

  function renderMarkdown(text) {
    if (typeof window !== "undefined" && window.marked && window.marked.parse) {
      return window.marked.parse(text || "");
    }
    return escapeHtml(text || "").replace(/\n/g, "<br>");
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function sanitizeAssistantHtml(html) {
    if (typeof DOMParser === "undefined") return html;
    const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
    const walk = (parent) => {
      Array.from(parent.children).forEach((child) => {
        if (!ALLOWED_ASSISTANT_TAGS.has(child.tagName)) {
          const text = document.createTextNode(child.textContent);
          parent.replaceChild(text, child);
          return;
        }
        if (child.tagName === "A") {
          const href = child.getAttribute("href") || "";
          if (!/^https?:\/\/\S+$/.test(href)) {
            child.removeAttribute("href");
          }
        }
        Array.from(child.attributes).forEach((attribute) => {
          if (!ALLOWED_ASSISTANT_ATTRIBUTES.has(attribute.name)) {
            child.removeAttribute(attribute.name);
          }
        });
        walk(child);
      });
    };
    walk(doc.body);
    return doc.body.innerHTML;
  }

  function setAssistantMessageHtml(textEl, text) {
    if (!textEl) return;
    textEl.innerHTML = sanitizeAssistantHtml(renderMarkdown(text));
    if (typeof textEl.querySelectorAll === "function") {
      textEl.querySelectorAll("a").forEach((link) => {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      });
    }
  }

  function pushAssistantMessage(message) {
    state.messages.push({
      role: "assistant",
      text: message.text,
      citations: message.citations || [],
      validation: message.validation || null,
      errorCodes: message.errorCodes || [],
      context: Boolean(message.context),
    });
    saveState();
  }

  function renderStoredAssistantMessage(message) {
    const article = document.createElement("div");
    article.className = "market-assistant-message market-assistant-message-assistant";
    if (message.context) {
      const details = document.createElement("details");
      details.className = "market-assistant-context-note";
      const summary = document.createElement("summary");
      summary.textContent = "Page results attached as context";
      const textEl = document.createElement("p");
      textEl.className = "market-assistant-message-text";
      setAssistantMessageHtml(textEl, message.text || "");
      details.appendChild(summary);
      details.appendChild(textEl);
      article.appendChild(details);
      return article;
    }
    const textEl = document.createElement("p");
    textEl.className = "market-assistant-message-text";
    setAssistantMessageHtml(textEl, message.text || "");
    article.appendChild(textEl);
    if (message.citations && message.citations.length) {
      const heading = document.createElement("p");
      heading.className = "market-assistant-citations-heading";
      heading.textContent = "External research";
      article.appendChild(heading);
      article.appendChild(renderCitations(message.citations));
    }
    if (
      message.validation &&
      message.validation !== "disabled" &&
      VALIDATION_BADGE_TEXT[message.validation]
    ) {
      article.appendChild(
        renderValidationBadge(message.validation, message.errorCodes || [])
      );
    }
    return article;
  }

  function renderValidationDisabledNotice() {
    const el = elements();
    if (!el.validationDisabledNotice) return;
    el.validationDisabledNotice.textContent = VALIDATION_BADGE_TEXT.disabled;
    el.validationDisabledNotice.className =
      "market-assistant-validation-disabled-notice market-assistant-validation-disabled-shown";
  }

  function hideValidationDisabledNotice() {
    const el = elements();
    if (!el.validationDisabledNotice) return;
    el.validationDisabledNotice.textContent = "";
    el.validationDisabledNotice.className = "market-assistant-validation-disabled-notice";
  }

  function syncValidationDisabledNotice() {
    const hasDisabled = state.messages.some(
      (message) => message.role === "assistant" && message.validation === "disabled"
    );
    if (hasDisabled) {
      renderValidationDisabledNotice();
    } else {
      hideValidationDisabledNotice();
    }
  }

  function renderMessages() {
    const el = elements();
    if (!el.log) return;
    el.log.textContent = "";
    state.messages.forEach((message) => {
      if (message.role === "user") {
        el.log.appendChild(renderUserMessage(message.text));
      } else {
        el.log.appendChild(renderStoredAssistantMessage(message));
      }
    });
    syncValidationDisabledNotice();
  }

  function openWindow() {
    const el = elements();
    if (!el.window) return;
    state.isOpen = true;
    el.window.classList.add("open");
    el.window.setAttribute("aria-hidden", "false");
    applyWindowRect();
    if (state.messages.length === 0) {
      loadState();
    }
    if (el.log && el.log.children.length === 0) {
      renderMessages();
    }
    if (el.question) el.question.focus();
  }

  function closeWindow() {
    const el = elements();
    state.isOpen = false;
    if (el.window) {
      el.window.classList.remove("open");
      el.window.setAttribute("aria-hidden", "true");
    }
    saveState();
    if (el.fab) el.fab.focus();
  }

  function toggleWindow() {
    if (state.isOpen) closeWindow();
    else openWindow();
  }

  function conversationId() {
    if (!state.conversationId) {
      state.conversationId =
        "conv_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    }
    return state.conversationId;
  }

  function startNewConversation() {
    if (state.busy) return false;
    const el = elements();
    state.conversationId = null;
    state.serverHistoryReady = false;
    state.lastContextId = null;
    state.messages = [];
    state.error = null;
    if (el.question) el.question.value = "";
    renderStatus("", false);
    renderMessages();
    saveState();
    if (el.question) el.question.focus();
    return true;
  }

  function messageId() {
    return "msg_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  function buildPayload(question, options = {}) {
    const payload = {
      question: String(question || "").trim(),
      mode: "current",
      conversation_id: conversationId(),
      message_id: messageId(),
      deep_research_requested: Boolean(
        options.deepResearchRequested !== undefined
          ? options.deepResearchRequested
          : state.deepResearchRequested
      ),
      external_search_requested: Boolean(
        options.externalSearchRequested !== undefined
          ? options.externalSearchRequested
          : state.externalSearchRequested
      ),
      deep_analysis_requested: Boolean(
        options.deepAnalysisRequested !== undefined
          ? options.deepAnalysisRequested
          : state.deepAnalysisRequested
      ),
    };
    if (state.lastContextId) {
      payload.previous_context_id = state.lastContextId;
    }
    if (!state.serverHistoryReady) {
      const priorMessages = state.messages.slice();
      const lastMessage = priorMessages[priorMessages.length - 1];
      if (
        lastMessage &&
        lastMessage.role === "user" &&
        String(lastMessage.text || "").trim() === payload.question
      ) {
        priorMessages.pop();
      }
      const bootstrap = priorMessages
        .filter(
          (message) =>
            (message.role === "user" || message.role === "assistant") &&
            String(message.text || "").trim()
        )
        .map((message) => ({
          role: message.role,
          text: String(message.text).trim(),
        }));
      if (bootstrap.length) {
        payload.conversation_bootstrap = bootstrap;
      }
    }
    return payload;
  }

  function acceptedEvidenceDate(resolution) {
    if (!resolution) return null;
    const evidenceThrough =
      resolution.evidence_through ||
      (resolution.snapshot || {}).evidence_through;
    if (evidenceThrough) return String(evidenceThrough).slice(0, 10);
    return null;
  }

  function renderContextChangeNotice() {
    const notice = document.createElement("p");
    notice.className = "market-assistant-notice market-assistant-notice-context";
    notice.textContent = "Market Setup context changed since the previous message.";
    return notice;
  }

  function renderEvidenceDate(date) {
    const line = document.createElement("p");
    line.className = "market-assistant-evidence-date";
    line.textContent = "Market Setup evidence through " + date;
    return line;
  }

  function renderUserMessage(text) {
    const article = document.createElement("div");
    article.className = "market-assistant-message market-assistant-message-user";
    const textEl = document.createElement("p");
    textEl.className = "market-assistant-message-text";
    textEl.textContent = text;
    article.appendChild(textEl);
    return article;
  }

  function citationDate(citation) {
    return citation.event_date || citation.publication_date || "";
  }

  function applyCitationSecurityAttributes(link) {
    CITATION_SECURITY_ATTRS.forEach((attribute) => {
      const separator = attribute.indexOf("=");
      const name = attribute.slice(0, separator);
      const value = attribute.slice(separator + 2, -1);
      link.setAttribute(name, value);
    });
  }

  function renderCitation(citation) {
    const item = document.createElement("li");
    item.className = "market-assistant-citation";
    const link = document.createElement("a");
    link.className = "market-assistant-citation-link";
    link.setAttribute("href", citation.url || "#");
    link.textContent = citation.title || citation.source_id || "Source";
    applyCitationSecurityAttributes(link);
    item.appendChild(link);
    const date = citationDate(citation);
    if (date) {
      const meta = document.createElement("span");
      meta.className = "market-assistant-citation-date";
      meta.textContent = date;
      item.appendChild(meta);
    }
    return item;
  }

  function renderCitations(citations) {
    const list = document.createElement("ul");
    list.className = "market-assistant-citations";
    (citations || []).forEach((citation) => {
      list.appendChild(renderCitation(citation));
    });
    return list;
  }

  function getActiveMessageStatus() {
    const el = elements();
    const active = el.log
      ? el.log.querySelector('.market-assistant-message[aria-busy="true"] .market-assistant-message-status')
      : null;
    if (active) return active;
    return el.status || null;
  }

  function renderStatus(text, isError) {
    const target = getActiveMessageStatus();
    if (!target) return;
    target.textContent = text;
    target.className = text && isError
      ? "market-assistant-message-status market-assistant-status-error"
      : "market-assistant-message-status";
  }

  function clearStreamStatus(stream) {
    stream.statusEl.textContent = "";
    stream.statusEl.className = "market-assistant-message-status";
  }

  function completeStreamStatus(stream) {
    stream.statusEl.textContent = COMPLETION_NOTICE;
    stream.statusEl.className = "market-assistant-message-status";
    stream.element.appendChild(stream.statusEl);
  }

  function renderThinking() {
    const target = getActiveMessageStatus();
    if (!target) return;
    target.textContent = THINKING_TEXT;
    target.className = "market-assistant-message-status market-assistant-thinking";
  }

  function clearThinking() {
    const target = getActiveMessageStatus();
    if (!target || target.textContent !== THINKING_TEXT) return;
    target.textContent = "";
    target.className = "market-assistant-message-status";
  }

  function renderProgress(message) {
    const target = getActiveMessageStatus();
    if (!target) return;
    target.textContent = message;
    target.className = "market-assistant-message-status market-assistant-progress";
  }

  function clearProgress() {
    const target = getActiveMessageStatus();
    if (!target || target.className.indexOf("market-assistant-progress") === -1) return;
    target.textContent = "";
    target.className = "market-assistant-message-status";
  }

  function renderValidationBadge(status, errorCodes) {
    const badge = document.createElement("div");
    badge.className = "market-assistant-validation " + VALIDATION_BADGE_CLASS[status];
    const label = document.createElement("span");
    label.className = "market-assistant-validation-label";
    label.textContent = VALIDATION_BADGE_TEXT[status];
    badge.appendChild(label);
    if (status === "failed" && errorCodes && errorCodes.length) {
      const codes = document.createElement("span");
      codes.className = "market-assistant-validation-codes";
      codes.textContent = errorCodes.join(", ");
      badge.appendChild(codes);
    }
    return badge;
  }

  function renderFailure(stream, question) {
    stream.message.failed = true;
    stream.element.setAttribute("aria-busy", "false");
    stream.element.textContent = "";
    const notice = document.createElement("div");
    notice.className = "market-assistant-notice market-assistant-notice-failed";
    const text = document.createElement("span");
    text.className = "market-assistant-notice-failed-text";
    text.textContent = FAILED_NOTICE;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "market-assistant-retry-button";
    retry.textContent = RETRY_LABEL;
    retry.addEventListener("click", () => {
      if (state.busy) return;
      stream.element.remove();
      sendQuestion(question, { recordUser: false });
    });
    notice.appendChild(text);
    notice.appendChild(retry);
    stream.element.appendChild(notice);
  }

  function appendUserMessage(text) {
    const el = elements();
    if (el.log) {
      el.log.appendChild(renderUserMessage(text));
    }
    state.messages.push({ role: "user", text: text });
    saveState();
  }

  function createStreamingAssistantMessage() {
    const el = elements();
    const message = {
      text: "",
      resolution: null,
      citations: [],
      validation: null,
      complete: false,
    };
    const textEl = document.createElement("p");
    textEl.className = "market-assistant-message-text";
    const statusEl = document.createElement("div");
    statusEl.className = "market-assistant-message-status";
    statusEl.setAttribute("role", "status");
    statusEl.setAttribute("aria-live", "polite");
    statusEl.setAttribute("aria-atomic", "true");
    const article = document.createElement("div");
    article.className = "market-assistant-message market-assistant-message-assistant";
    article.setAttribute("aria-busy", "true");
    article.appendChild(textEl);
    article.appendChild(statusEl);
    if (el.log) {
      el.log.appendChild(article);
    }
    return { element: article, message, textEl, statusEl };
  }

  function applyStreamEvent(stream, event) {
    switch (event.type) {
      case "resolution":
        stream.message.resolution = event.resolution;
        if (event.resolution && event.resolution.current_context_id) {
          state.lastContextId = event.resolution.current_context_id;
        }
        if (
          event.resolution &&
          event.resolution.context_changed &&
          event.resolution.previous_context_id != null
        ) {
          stream.element.insertBefore(renderContextChangeNotice(), stream.textEl);
        }
        const evidenceDate = acceptedEvidenceDate(event.resolution);
        if (evidenceDate) {
          stream.element.appendChild(renderEvidenceDate(evidenceDate));
        }
        break;
      case "answer_delta":
        stream.message.text += event.delta || "";
        stream.textEl.textContent = stream.message.text;
        clearThinking();
        clearProgress();
        break;
      case "answer_replace":
        stream.message.text = event.text || "";
        setAssistantMessageHtml(stream.textEl, stream.message.text);
        clearThinking();
        clearProgress();
        break;
      case "validation":
        clearStreamStatus(stream);
        if (event.status === "disabled") {
          stream.message.validation = event.status;
          renderValidationDisabledNotice();
        } else if (
          event.status !== "failed_initial" &&
          VALIDATION_BADGE_TEXT[event.status]
        ) {
          stream.message.validation = event.status;
          stream.message.errorCodes = event.error_codes || [];
          stream.element.appendChild(
            renderValidationBadge(event.status, event.error_codes || [])
          );
        }
        break;
      case "status":
        if (event.status === "thinking") {
          renderThinking();
        } else if (event.status === "validating") {
          renderStatus("Validating…", false);
        } else if (event.status === "repairing") {
          renderStatus("Repairing…", false);
        }
        break;
      case "progress":
        if (PROGRESS_STAGES.indexOf(event.stage) !== -1 && event.message) {
          renderProgress(event.message);
        }
        break;
      case "answer_failed":
        stream.message.failed = true;
        clearThinking();
        clearProgress();
        break;
      case "complete":
        state.serverHistoryReady = true;
        stream.message.complete = true;
        if (stream.message.failed) {
          renderFailure(stream, stream.question || "");
          break;
        }
        stream.message.citations = event.citations || [];
        setAssistantMessageHtml(stream.textEl, stream.message.text);
        if (stream.message.citations.length) {
          const heading = document.createElement("p");
          heading.className = "market-assistant-citations-heading";
          heading.textContent = "External research";
          stream.element.appendChild(heading);
          stream.element.appendChild(renderCitations(stream.message.citations));
        }
        if (stream.message.validation === "disabled") {
          renderValidationDisabledNotice();
        }
        completeStreamStatus(stream);
        stream.element.setAttribute("aria-busy", "false");
        pushAssistantMessage(stream.message);
        break;
    }
  }

  function parseNdjsonLine(line) {
    return JSON.parse(line);
  }

  function parseNdjsonLines(buffer, onEvent) {
    let newlineIndex = buffer.indexOf("\n");
    let residual = buffer;
    while (newlineIndex !== -1) {
      const line = residual.slice(0, newlineIndex);
      residual = residual.slice(newlineIndex + 1);
      if (line.trim()) {
        onEvent(parseNdjsonLine(line));
      }
      newlineIndex = residual.indexOf("\n");
    }
    return residual;
  }

  async function consumeNdjsonStream(response, onEvent) {
    if (!response.body) {
      throw new Error("response body is missing");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let terminalEvent = false;
    const wrapped = (event) => {
      if (event.type === "complete" || event.type === "error") {
        terminalEvent = true;
      }
      onEvent(event);
    };
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = parseNdjsonLines(buffer, wrapped);
      }
      buffer += decoder.decode();
      if (buffer.trim()) {
        wrapped(parseNdjsonLine(buffer));
      }
      if (!terminalEvent) {
        throw new Error("stream ended without a terminal event");
      }
    } catch (error) {
      await reader.cancel();
      throw error;
    } finally {
      reader.releaseLock();
    }
  }

  async function submitQuestionStream(question, handlers) {
    const payload = buildPayload(question);
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error("request failed with status " + response.status);
    }
    await consumeNdjsonStream(response, (event) => {
      if (event.type === "error") {
        throw new Error(event.message || "stream failed");
      }
      handlers.onEvent(event);
    });
  }

  function createClientTiming() {
    const startedAt = performance.now();
    const marks = {};
    function mark(name) {
      if (marks[name] === undefined) {
        marks[name] = performance.now() - startedAt;
      }
    }
    return {
      markFirstEvent() {
        mark("first_event");
      },
      markFirstDelta() {
        mark("first_delta");
      },
      markValidation() {
        mark("validation");
      },
      markComplete() {
        mark("complete");
      },
      durations() {
        return {
          first_event_ms: marks.first_event,
          first_delta_ms: marks.first_delta,
          complete_ms: marks.complete,
          validation_ms: marks.validation,
        };
      },
    };
  }

  function emitClientTiming(requestId, durations) {
    if (!requestId) return;
    console.info("market assistant client timing", {
      request_id: requestId,
      durations_ms: durations,
    });
  }

  async function sendQuestion(question, options) {
    const el = elements();
    const recordUser = !options || options.recordUser !== false;
    if (!question || state.busy) return;
    renderStatus("", false);
    state.busy = true;
    el.submit.disabled = true;
    if (el.newConversation) el.newConversation.disabled = true;
    if (recordUser) {
      appendUserMessage(question);
    }
    el.question.value = "";
    const stream = createStreamingAssistantMessage();
    stream.question = question;
    renderThinking();
    const timing = createClientTiming();
    let requestId = null;
    try {
      await submitQuestionStream(question, {
        onEvent: (event) => {
          timing.markFirstEvent();
          if (event.type === "resolution" || event.type === "complete") {
            requestId = event.request_id || requestId;
          }
          if (event.type === "answer_delta") {
            timing.markFirstDelta();
          }
          if (event.type === "validation") {
            timing.markValidation();
          }
          if (event.type === "complete") {
            timing.markComplete();
          }
          applyStreamEvent(stream, event);
        },
      });
      emitClientTiming(requestId, timing.durations());
    } catch (error) {
      state.error = String(error.message || "request failed");
      renderFailure(stream, question);
    } finally {
      state.busy = false;
      el.submit.disabled = false;
      if (el.newConversation) el.newConversation.disabled = false;
      el.question.focus();
    }
  }

  async function handleSubmit() {
    const el = elements();
    const question = String(el.question.value || "").trim();
    await sendQuestion(question);
  }

  function syncDeepResearchEnabled() {
    const el = elements();
    if (!el.deepResearch || !el.externalSearch) return;
    el.deepResearch.disabled = !state.externalSearchRequested;
    if (el.deepResearch.disabled) {
      el.deepResearch.checked = false;
      state.deepResearchRequested = false;
    }
  }

  function bindDrag() {
    const el = elements();
    if (!el.head) return;
    el.head.addEventListener("mousedown", (event) => {
      if (event.button !== 0 || isMobileViewport()) return;
      const rect = state.windowRect;
      const startX = event.clientX;
      const startY = event.clientY;
      const startRight = rect.right;
      const startBottom = rect.bottom;
      const onMove = (moveEvent) => {
        state.windowRect.right = Math.max(12, startRight - (moveEvent.clientX - startX));
        state.windowRect.bottom = Math.max(12, startBottom - (moveEvent.clientY - startY));
        applyWindowRect();
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        saveState();
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      event.preventDefault();
    });
  }

  function bindResize() {
    const el = elements();
    if (!el.window || typeof el.window.querySelectorAll !== "function") return;
    el.window.querySelectorAll(".market-assistant-resize").forEach((handle) => {
      handle.addEventListener("mousedown", (event) => {
        if (event.button !== 0 || isMobileViewport()) return;
        const edge = handle.getAttribute("data-edge") || "se";
        const rect = state.windowRect;
        const startX = event.clientX;
        const startY = event.clientY;
        const startWidth = rect.width;
        const startHeight = rect.height;
        const startRight = rect.right;
        const startBottom = rect.bottom;
        const maxHeight = Math.max(360, Math.floor((window.innerHeight || 640) * 0.9));
        const onMove = (moveEvent) => {
          const dx = moveEvent.clientX - startX;
          const dy = moveEvent.clientY - startY;
          let width = startWidth;
          let height = startHeight;
          let right = startRight;
          let bottom = startBottom;
          if (edge.includes("e")) {
            width = clamp(startWidth + dx, 280, 720);
          }
          if (edge.includes("w")) {
            const desired = clamp(startWidth - dx, 280, 720);
            const deltaWidth = desired - width;
            width = desired;
            right = Math.max(12, startRight - deltaWidth);
          }
          if (edge.includes("s")) {
            height = clamp(startHeight + dy, 360, maxHeight);
          }
          if (edge.includes("n")) {
            const desired = clamp(startHeight - dy, 360, maxHeight);
            const deltaHeight = desired - height;
            height = desired;
            bottom = Math.max(12, startBottom - deltaHeight);
          }
          state.windowRect.width = width;
          state.windowRect.height = height;
          state.windowRect.right = right;
          state.windowRect.bottom = bottom;
          applyWindowRect();
        };
        const onUp = () => {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          saveState();
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
        event.preventDefault();
      });
    });
  }

  function bindEvents() {
    const el = elements();
    if (!el.form || !el.question || !el.submit) return;
    el.form.addEventListener("submit", (event) => {
      event.preventDefault();
      handleSubmit();
    });
    el.question.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        handleSubmit();
      }
    });
    if (el.fab) {
      el.fab.addEventListener("click", (event) => {
        event.preventDefault();
        toggleWindow();
      });
    }
    if (el.close) {
      el.close.addEventListener("click", () => {
        closeWindow();
      });
    }
    if (el.newConversation) {
      el.newConversation.addEventListener("click", () => {
        startNewConversation();
      });
    }
    bindDrag();
    bindResize();
    if (el.externalSearch) {
      el.externalSearch.addEventListener("change", (event) => {
        state.externalSearchRequested = Boolean(event.target.checked);
        syncDeepResearchEnabled();
      });
    }
    if (el.deepResearch) {
      el.deepResearch.addEventListener("change", (event) => {
        state.deepResearchRequested = Boolean(event.target.checked);
      });
    }
    if (el.deepAnalysis) {
      el.deepAnalysis.addEventListener("change", (event) => {
        state.deepAnalysisRequested = Boolean(event.target.checked);
      });
    }
    syncDeepResearchEnabled();
  }

  bindEvents();
  loadState();
  if (state.isOpen) {
    openWindow();
  } else {
    renderMessages();
  }

  function openWithContext(options) {
    const seedText = options && options.seedText ? String(options.seedText).trim() : "";
    const question = options && options.question ? String(options.question).trim() : "";
    if (!seedText && !question) return;
    if (!startNewConversation()) return;
    if (seedText) {
      pushAssistantMessage({ text: seedText, context: true });
    }
    openWindow();
    if (question) {
      const el = elements();
      if (el.question) {
        el.question.value = question;
        handleSubmit();
      }
    }
  }

  window.marketAssistant = {
    openWithContext: openWithContext,
  };

  if (typeof window !== "undefined" && window.__MEOWSTREET_TEST__) {
    window.__MEOWSTREET_TEST__ = {
      buildPayload,
      submitQuestionStream,
      consumeNdjsonStream,
      createStreamingAssistantMessage,
      applyStreamEvent,
      renderContextChangeNotice,
      renderEvidenceDate,
      acceptedEvidenceDate,
      renderCitations,
      renderMarkdown,
      setAssistantMessageHtml,
      sanitizeAssistantHtml,
      isMobileViewport,
      saveState,
      loadState,
      applyWindowRect,
      renderMessages,
      openWindow,
      closeWindow,
      toggleWindow,
      startNewConversation,
      handleSubmit,
      sendQuestion,
      state,
    };
  }
})();
