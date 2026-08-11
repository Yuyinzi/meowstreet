(function () {
  const API_URL = "/api/market-assistant/questions";

  const state = {
    lastContextId: null,
    conversationId: null,
    messages: [],
    busy: false,
    error: null,
    fallback: false,
    externalSearchRequested: false,
    deepResearchRequested: false,
  };

  const CITATION_TARGET_ATTR = 'target="_blank"';
  const CITATION_REL_ATTR = 'rel="noopener noreferrer"';
  const CITATION_SECURITY_ATTRS = [CITATION_TARGET_ATTR, CITATION_REL_ATTR];

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

  function renderFallbackNotice() {
    const notice = document.createElement("p");
    notice.className = "market-assistant-notice market-assistant-notice-fallback";
    notice.textContent =
      "A deterministic fallback was used because a validated assistant response was unavailable.";
    return notice;
  }

  function renderUnvalidatedDebugNotice() {
    const notice = document.createElement("p");
    notice.className = "market-assistant-notice market-assistant-notice-debug";
    notice.textContent =
      "Claim validation is disabled. This is unvalidated DeepSeek debug output " +
      "and must not be treated as a Market Setup decision.";
    return notice;
  }

  function renderEvidenceDate(date) {
    const line = document.createElement("p");
    line.className = "market-assistant-evidence-date";
    line.textContent = "Market Setup evidence through " + date;
    return line;
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

  function renderMessage(message) {
    const article = document.createElement("div");
    article.className =
      "market-assistant-message market-assistant-message-" + message.role;
    if (message.contextChanged) {
      article.appendChild(renderContextChangeNotice());
    }
    if (message.unvalidatedDebug) {
      article.appendChild(renderUnvalidatedDebugNotice());
    }
    const text = document.createElement("p");
    text.className = "market-assistant-message-text";
    text.textContent = message.text;
    article.appendChild(text);
    if (message.evidenceDate) {
      article.appendChild(renderEvidenceDate(message.evidenceDate));
    }
    if (message.fallback) {
      article.appendChild(renderFallbackNotice());
    }
    if (message.citations && message.citations.length) {
      const heading = document.createElement("p");
      heading.className = "market-assistant-citations-heading";
      heading.textContent = "External research";
      article.appendChild(heading);
      article.appendChild(renderCitations(message.citations));
    }
    return article;
  }

  function assistantMessageFrom(data) {
    const resolution = data.resolution || {};
    return {
      role: "assistant",
      text: data.answer_text || "",
      citations: data.citations || [],
      fallback: data.generation_status === "fallback",
      unvalidatedDebug: data.generation_status === "unvalidated_debug",
      contextChanged:
        Boolean(resolution.context_changed) && resolution.previous_context_id != null,
      evidenceDate: acceptedEvidenceDate(resolution),
    };
  }

  function appendMessage(message) {
    const el = elements();
    if (el.log) {
      el.log.appendChild(renderMessage(message));
    }
  }

  function renderStatus(text, isError) {
    const el = elements();
    if (!el.status) return;
    el.status.textContent = text;
    el.status.className = text && isError
      ? "market-assistant-status market-assistant-status-error"
      : "market-assistant-status";
  }

  function applyResponse(data) {
    const resolution = data.resolution || {};
    if (resolution.current_context_id) {
      state.lastContextId = resolution.current_context_id;
    }
    state.fallback = data.generation_status === "fallback";
    state.error = null;
  }

  async function submitQuestion(question) {
    const payload = buildPayload(question);
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error("request failed with status " + response.status);
    }
    const data = await response.json();
    applyResponse(data);
    return data;
  }

  async function handleSubmit() {
    const el = elements();
    const question = String(el.question.value || "").trim();
    if (!question || state.busy) return;
    state.busy = true;
    el.submit.disabled = true;
    renderStatus("Generating a grounded answer...", false);
    appendMessage({ role: "user", text: question });
    el.question.value = "";
    try {
      const data = await submitQuestion(question);
      appendMessage(assistantMessageFrom(data));
      renderStatus("", false);
    } catch (error) {
      state.error = String(error.message || "request failed");
      renderStatus(
        "The assistant could not answer right now. Your question is preserved.",
        true
      );
      el.question.value = question;
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
      submitQuestion,
      handleSubmit,
      renderMessage,
      renderCitations,
      renderContextChangeNotice,
      renderFallbackNotice,
      renderEvidenceDate,
      acceptedEvidenceDate,
      assistantMessageFrom,
      state,
    };
  }
})();
