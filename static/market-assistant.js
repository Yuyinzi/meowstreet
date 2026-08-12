(function () {
  const API_URL = "/api/market-assistant/questions/stream";

  const state = {
    lastContextId: null,
    conversationId: null,
    messages: [],
    busy: false,
    error: null,
    externalSearchRequested: false,
    deepResearchRequested: false,
  };

  const CITATION_TARGET_ATTR = 'target="_blank"';
  const CITATION_REL_ATTR = 'rel="noopener noreferrer"';
  const CITATION_SECURITY_ATTRS = [CITATION_TARGET_ATTR, CITATION_REL_ATTR];

  const THINKING_TEXT = "Thinking…";
  const UNAVAILABLE_NOTICE =
    "The assistant could not answer right now. Your question is preserved.";
  const INTERRUPTED_NOTICE = "连接中断，回答可能不完整";

  const VALIDATION_BADGE_TEXT = {
    passed: "已通过 Market Setup 证据验证",
    repaired_and_passed: "修复后已通过验证",
    failed: "未通过完整证据验证",
    disabled: "Claim validation 当前已关闭",
    fallback: "已使用确定性备用回答",
  };

  const VALIDATION_BADGE_CLASS = {
    passed: "market-assistant-validation-passed",
    repaired_and_passed: "market-assistant-validation-passed",
    failed: "market-assistant-validation-failed",
    disabled: "market-assistant-validation-disabled",
    fallback: "market-assistant-validation-passed",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function elements() {
    return {
      log: $("marketAssistantLog"),
      form: $("marketAssistantForm"),
      question: $("marketAssistantQuestion"),
      submit: $("marketAssistantSubmit"),
      externalSearch: $("marketAssistantExternalSearch"),
      deepResearch: $("marketAssistantDeepResearch"),
      status: $("marketAssistantStatus"),
    };
  }

  function conversationId() {
    if (!state.conversationId) {
      state.conversationId =
        "conv_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    }
    return state.conversationId;
  }

  function buildPayload(question, options = {}) {
    const payload = {
      question: String(question || "").trim(),
      mode: "current",
      conversation_id: conversationId(),
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
    };
    if (state.lastContextId) {
      payload.previous_context_id = state.lastContextId;
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

  function renderStatus(text, isError) {
    const el = elements();
    if (!el.status) return;
    el.status.textContent = text;
    el.status.className = text && isError
      ? "market-assistant-status market-assistant-status-error"
      : "market-assistant-status";
  }

  function renderThinking() {
    const el = elements();
    if (!el.status) return;
    el.status.textContent = THINKING_TEXT;
    el.status.className = "market-assistant-status market-assistant-thinking";
  }

  function clearThinking() {
    const el = elements();
    if (!el.status || el.status.textContent !== THINKING_TEXT) return;
    el.status.textContent = "";
    el.status.className = "market-assistant-status";
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

  function renderInterruptedNotice() {
    const notice = document.createElement("p");
    notice.className = "market-assistant-notice market-assistant-notice-fallback";
    notice.textContent = INTERRUPTED_NOTICE;
    return notice;
  }

  function appendUserMessage(text) {
    const el = elements();
    if (el.log) {
      el.log.appendChild(renderUserMessage(text));
    }
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
    const article = document.createElement("div");
    article.className = "market-assistant-message market-assistant-message-assistant";
    article.setAttribute("aria-busy", "true");
    article.appendChild(textEl);
    if (el.log) {
      el.log.appendChild(article);
    }
    return { element: article, message, textEl };
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
        break;
      case "answer_replace":
        stream.message.text = event.text || "";
        stream.textEl.textContent = stream.message.text;
        clearThinking();
        break;
      case "validation":
        if (
          event.status !== "failed_initial" &&
          VALIDATION_BADGE_TEXT[event.status]
        ) {
          stream.message.validation = event.status;
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
      case "complete":
        stream.message.complete = true;
        stream.message.citations = event.citations || [];
        if (stream.message.citations.length) {
          const heading = document.createElement("p");
          heading.className = "market-assistant-citations-heading";
          heading.textContent = "External research";
          stream.element.appendChild(heading);
          stream.element.appendChild(renderCitations(stream.message.citations));
        }
        stream.element.setAttribute("aria-busy", "false");
        break;
    }
  }

  function parseNdjsonLine(line) {
    try {
      return JSON.parse(line);
    } catch (error) {
      return null;
    }
  }

  function parseNdjsonLines(buffer, onEvent) {
    let newlineIndex = buffer.indexOf("\n");
    let residual = buffer;
    while (newlineIndex !== -1) {
      const line = residual.slice(0, newlineIndex);
      residual = residual.slice(newlineIndex + 1);
      if (line.trim()) {
        const event = parseNdjsonLine(line);
        if (event !== null) {
          onEvent(event);
        }
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
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = parseNdjsonLines(buffer, onEvent);
      }
      buffer += decoder.decode();
      if (buffer.trim()) {
        const event = parseNdjsonLine(buffer);
        if (event !== null) {
          onEvent(event);
        }
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

  async function handleSubmit() {
    const el = elements();
    const question = String(el.question.value || "").trim();
    if (!question || state.busy) return;
    state.busy = true;
    el.submit.disabled = true;
    renderThinking();
    appendUserMessage(question);
    el.question.value = "";
    const stream = createStreamingAssistantMessage();
    let bodyShown = false;
    try {
      await submitQuestionStream(question, {
        onEvent: (event) => {
          if (event.type === "answer_delta" || event.type === "answer_replace") {
            bodyShown = true;
          }
          applyStreamEvent(stream, event);
        },
      });
      renderStatus("", false);
    } catch (error) {
      state.error = String(error.message || "request failed");
      if (bodyShown || stream.message.text) {
        stream.element.setAttribute("aria-busy", "false");
        stream.element.appendChild(renderInterruptedNotice());
        renderStatus("", false);
      } else {
        stream.element.remove();
        renderStatus(UNAVAILABLE_NOTICE, true);
        el.question.value = question;
      }
    } finally {
      state.busy = false;
      el.submit.disabled = false;
      el.question.focus();
    }
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
    syncDeepResearchEnabled();
  }

  bindEvents();

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
      handleSubmit,
      state,
    };
  }
})();
