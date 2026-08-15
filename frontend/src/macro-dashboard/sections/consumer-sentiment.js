import { state } from "../state.js";
import { $, escapeHtml, fmtDate, fmtNumber } from "../utils.js";
import { loadConsumerSentimentDetail, fetchConsumerSentiment } from "../api.js";
import { renderOverview } from "./benchmark-grid.js";
import { renderUsRatesLiquidity } from "./us-rates-liquidity.js";
import { renderDetailPanel } from "../detail-panel.js";

export async function loadConsumerSentiment() {
    await fetchConsumerSentiment();
    renderConsumerSentiment();
  }


export function bindConsumerSentimentDetailTrigger(button, onActivate) {
    button.addEventListener("click", onActivate);
    button.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      button.click();
    });
  }


export function renderConsumerSentiment() {
    const section = $("consumerSentiment");
    if (!section) return;
    const head = section.querySelector(".relationship-head");
    if (state.consumerSentimentError) {
      section.innerHTML = `${head.outerHTML}<div class="growth-empty" role="status">Failed to load consumer sentiment data. <button type="button" class="ms-retry-btn" data-consumer-retry>Retry</button></div>`;
      const retryBtn = section.querySelector("[data-consumer-retry]");
      if (retryBtn) {
        retryBtn.addEventListener("click", () => {
          state.consumerSentiment = null;
          state.consumerSentimentError = null;
          loadConsumerSentiment();
        });
      }
      return;
    }
    if (!state.consumerSentiment) {
      section.innerHTML = `${head.outerHTML}<div class="consumer-loading" aria-busy="true">Loading consumer sentiment data\u2026</div>`;
      return;
    }
    const cardHtml = window.consumerSentimentUi.renderCard(state.consumerSentiment, {
      escapeHtml: escapeHtml,
      formatIndex: fmtNumber,
    });
    const asOf = state.consumerSentiment.as_of;
    section.innerHTML = `
      <div class="relationship-head">
        ${head.innerHTML}
        ${asOf ? `<span class="mock-pill">Data as of ${escapeHtml(fmtDate(asOf))}</span>` : ""}
      </div>
      <div class="growth-section-card-grid">
        ${cardHtml}
      </div>
    `;
    section.querySelectorAll("[data-consumer-detail-id]").forEach((button) => {
      bindConsumerSentimentDetailTrigger(button, () => {
        state.selectedConsumerDetailId = state.selectedConsumerDetailId === button.dataset.consumerDetailId
          ? null
          : button.dataset.consumerDetailId;
        state.selectedBenchmarkId = null;
        state.selectedRatesDetailId = null;
        state.selectedGrowthCycleDetailId = null;
        renderOverview();
        renderUsRatesLiquidity();
        renderConsumerSentiment();
        renderDetailPanel();
      });
    });
  }


export function renderConsumerDetailInPanel(body) {
    const detailId = state.selectedConsumerDetailId;
    if (!detailId) return;
    body.innerHTML = `<p class="status">Loading consumer detail\u2026</p>`;
    loadConsumerSentimentDetail()
      .then((payload) => {
        window.consumerSentimentUi.renderDetailInPanel(body, payload);
      })
      .catch((error) => {
        body.innerHTML = `<p class="status" role="status">Failed to load consumer detail. <button type="button" class="ms-retry-btn" data-consumer-detail-retry>Retry</button></p>`;
        const retryBtn = body.querySelector("[data-consumer-detail-retry]");
        if (retryBtn) {
          retryBtn.addEventListener("click", () => {
            renderDetailPanel();
          });
        }
      });
  }

