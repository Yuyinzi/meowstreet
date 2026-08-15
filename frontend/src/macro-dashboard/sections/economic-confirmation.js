import { state } from "../state.js";
import { $, escapeHtml, fmtDateOnly, fmtNumber, fmtInteger, bilingualLabel, bilingualTitle, titleCaseToken } from "../utils.js";
import { loadEconomicConfirmationDetail, fetchEconomicConfirmation } from "../api.js";
import { renderOverview } from "./benchmark-grid.js";
import { renderUsRatesLiquidity } from "./us-rates-liquidity.js";
import { renderDetailPanel } from "../detail-panel.js";
import { bindConsumerSentimentDetailTrigger } from "./consumer-sentiment.js";

export async function loadEconomicConfirmation() {
    await fetchEconomicConfirmation();
    renderEconomicConfirmation();
  }


export function renderEconomicConfirmation() {
    const section = $("economicConfirmation");
    if (!section || typeof section.querySelector !== "function") return;
    const head = section.querySelector(".relationship-head");
    if (!head) return;
    head.querySelectorAll(".mock-pill").forEach((el) => el.remove());
    if (state.economicConfirmationError) {
      section.innerHTML = `${head.outerHTML}<div class="growth-empty" role="status">Failed to load economic confirmation data. <button type="button" class="ms-retry-btn" data-economic-confirmation-retry>Retry</button></div>`;
      const retryBtn = section.querySelector("[data-economic-confirmation-retry]");
      if (retryBtn) {
        retryBtn.addEventListener("click", () => {
          state.economicConfirmation = null;
          state.economicConfirmationError = null;
          loadEconomicConfirmation();
        });
      }
      return;
    }
    if (!state.economicConfirmation) {
      section.innerHTML = `${head.outerHTML}<div class="economic-confirmation-loading" aria-busy="true">Loading economic confirmation…</div>`;
      return;
    }
    if (!window.claimsConfirmationUi || !window.claimsConfirmationUi.renderCard) {
      section.innerHTML = `${head.outerHTML}<p class="growth-empty">Economic confirmation data is not available.</p>`;
      return;
    }
    const cardHtml = window.claimsConfirmationUi.renderCard(state.economicConfirmation, {
      escapeHtml,
      bilingualLabel,
      bilingualTitle,
      titleCaseToken,
      fmtNumber,
      isSelectedEconomicConfirmationDetailId: (id) => state.selectedEconomicConfirmationDetailId === id,
    });
    const asOf = state.economicConfirmation.as_of;
    section.innerHTML = `
      <div class="relationship-head">
        ${head.innerHTML}
        ${asOf ? `<span class="mock-pill">Data as of ${escapeHtml(fmtDateOnly(asOf))}</span>` : ""}
      </div>
      <div class="economic-confirmation-layer-body">${cardHtml}</div>
    `;
    section.querySelectorAll("[data-economic-confirmation-detail-id]").forEach((button) => {
      bindConsumerSentimentDetailTrigger(button, () => {
        state.selectedEconomicConfirmationDetailId = state.selectedEconomicConfirmationDetailId === button.dataset.economicConfirmationDetailId
          ? null
          : button.dataset.economicConfirmationDetailId;
        state.selectedBenchmarkId = null;
        state.selectedRatesDetailId = null;
        state.selectedGrowthCycleDetailId = null;
        state.selectedConsumerDetailId = null;
        renderOverview();
        renderUsRatesLiquidity();
        renderEconomicConfirmation();
        renderDetailPanel();
      });
    });
  }


export function renderEconomicConfirmationDetailInPanel(body) {
    const detailId = state.selectedEconomicConfirmationDetailId;
    if (!detailId) return;
    body.innerHTML = `<p class="status">Loading economic confirmation detail…</p>`;
    loadEconomicConfirmationDetail()
      .then((payload) => {
        if (!window.claimsConfirmationUi || !window.claimsConfirmationUi.renderDetail) return;
        window.claimsConfirmationUi.renderDetail(body, payload, {
          escapeHtml,
          bilingualLabel,
          bilingualTitle,
          titleCaseToken,
          fmtNumber,
          fmtInteger,
        });
      })
      .catch((error) => {
        body.innerHTML = `<p class="status" role="status">Failed to load economic confirmation detail. <button type="button" class="ms-retry-btn" data-economic-confirmation-detail-retry>Retry</button></p>`;
        const retryBtn = body.querySelector("[data-economic-confirmation-detail-retry]");
        if (retryBtn) {
          retryBtn.addEventListener("click", () => {
            renderDetailPanel();
          });
        }
        console.error(error);
      });
  }

