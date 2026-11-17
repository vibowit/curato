// Simkl Taste & Recommendation Engine - Frontend Application
document.addEventListener("DOMContentLoaded", () => {
  // App State
  const state = {
    runs: [],
    currentRun: null,
    recommendations: [],
    filters: {
      type: "all",
      status: "all",
    },
    activeProfile: null,
    languages: [],
    currentLang: localStorage.getItem("movie_recommend_lang") || "pl",
    translations: {},
  };

  // DOM Elements
  const langSelect = document.getElementById("lang-select");
  const inputRunLanguage = document.getElementById("input-run-language");
  const profilePillText = document.getElementById("profile-pill-text");
  const btnProfile = document.getElementById("btn-profile");
  const modalProfile = document.getElementById("modal-profile");
  const profileContentContainer = document.getElementById("profile-content-container");
  const btnGenerateProfile = document.getElementById("btn-generate-profile");
  const runSelect = document.getElementById("run-select");
  const runMetaStatus = document.getElementById("run-meta-status");
  const summaryMeta = document.getElementById("summary-meta");
  const summaryText = document.getElementById("summary-text");
  const recsContainer = document.getElementById("recommendations-container");
  const approvalBar = document.getElementById("approval-bar");
  const approvedCountText = document.getElementById("approved-count-text");
  const btnSubmitApprove = document.getElementById("btn-submit-approve");
  const btnSync = document.getElementById("btn-sync");
  const btnNewRun = document.getElementById("btn-new-run");
  const btnHistory = document.getElementById("btn-history");
  const modalNewRun = document.getElementById("modal-new-run");
  const modalHistory = document.getElementById("modal-history");
  const formNewRun = document.getElementById("form-new-run");
  const historyTableContainer = document.getElementById("history-table-container");
  const toastContainer = document.getElementById("toast-container");

  // Translation helper
  function t(key, fallback = "") {
    return state.translations?.ui?.[key] || fallback;
  }

  // Helper: Toast Notifications
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "success" ? "✅" : type === "error" ? "❌" : "ℹ️";
    toast.innerHTML = `<span>${icon}</span> <div>${message}</div>`;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-10px)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // API helper
  async function api(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    try {
      const resp = await fetch(path, { ...options, headers });
      if (!resp.ok) {
        let errData = {};
        try {
          errData = await resp.json();
        } catch (_) {}
        const msg = errData.message || `Server error (HTTP ${resp.status})`;
        throw new Error(msg);
      }
      if (resp.status === 204) return null;
      return await resp.json();
    } catch (err) {
      console.error(`API Error on ${path}:`, err);
      throw err;
    }
  }

  // i18n: Load available languages and initialize active language
  async function initLanguages() {
    try {
      const langs = await api("/api/v1/languages");
      state.languages = langs || [];

      // Check if stored language is supported, fallback to first available
      const langCodes = state.languages.map((l) => l.code);
      if (!langCodes.includes(state.currentLang)) {
        state.currentLang = langCodes.includes("pl") ? "pl" : langCodes[0] || "pl";
      }

      // Populate language selector in header
      if (langSelect) {
        langSelect.innerHTML = state.languages
          .map((l) => `<option value="${l.code}">${l.flag || "🌐"} ${l.name}</option>`)
          .join("");
        langSelect.value = state.currentLang;
      }

      // Populate language selector in "New Run" modal
      if (inputRunLanguage) {
        inputRunLanguage.innerHTML = state.languages
          .map((l) => `<option value="${l.code}">${l.flag || "🌐"} ${l.name}</option>`)
          .join("");
        inputRunLanguage.value = state.currentLang;
      }

      // Fetch dictionary for current language
      await applyLanguage(state.currentLang);
    } catch (err) {
      console.error("Failed to initialize languages:", err);
    }
  }

  // i18n: Fetch dictionary and update UI strings
  async function applyLanguage(code) {
    try {
      const data = await api(`/api/v1/languages/${code}`);
      state.translations = data;
      state.currentLang = code;
      localStorage.setItem("movie_recommend_lang", code);
      document.documentElement.lang = code;

      if (langSelect && langSelect.value !== code) {
        langSelect.value = code;
      }
      if (inputRunLanguage && inputRunLanguage.value !== code) {
        inputRunLanguage.value = code;
      }

      // Update static elements with data-i18n attribute
      document.querySelectorAll("[data-i18n]").forEach((el) => {
        const key = el.getAttribute("data-i18n");
        const val = t(key);
        if (val) {
          el.textContent = val;
        }
      });

      // Update dynamic UI parts
      if (state.activeProfile && profilePillText) {
        profilePillText.textContent = `${t("profile_active", "Profil: Aktywny")}: ${state.activeProfile.version}`;
      } else if (profilePillText) {
        profilePillText.textContent = t("profile_none", "Profil: Brak");
      }

      updateApprovalBar();
      if (state.recommendations && state.recommendations.length > 0) {
        renderRecommendations();
      }
    } catch (err) {
      console.error(`Failed to apply language ${code}:`, err);
    }
  }

  // Initial Load
  async function init() {
    await initLanguages();
    await Promise.all([loadProfile(), loadRuns()]);
  }

  // Load Active Taste Profile
  async function loadProfile() {
    try {
      const data = await api("/api/profile");
      state.activeProfile = data;
      if (profilePillText) {
        profilePillText.textContent = `${t("profile_active", "Profil: Aktywny")}: ${data.version}`;
      }
    } catch (err) {
      state.activeProfile = null;
      if (profilePillText) {
        profilePillText.textContent = t("profile_none", "Profil: Brak");
      }
    }
  }

  // Load All Recommendation Runs
  async function loadRuns() {
    try {
      const runs = await api("/api/recommendation-runs?limit=30");
      state.runs = runs;
      runSelect.innerHTML = "";

      if (!runs || runs.length === 0) {
        runSelect.innerHTML = `<option value="">${t("run_select_empty", "Brak wygenerowanych edycji")}</option>`;
        recsContainer.innerHTML = `
          <div class="empty-state">
            <span style="font-size: 3rem;">🎬</span>
            <h3>${t("no_recommendations", "Brak rekomendacji")}</h3>
            <p>${t("run_summary_empty", "Nie wygenerowano jeszcze żadnej edycji. Kliknij 'Nowa Edycja', aby stworzyć pierwsze propozycje.")}</p>
          </div>
        `;
        return;
      }

      runs.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.id;
        const localeCode = state.currentLang === "en" ? "en-US" : "pl-PL";
        const dateStr = new Date(r.created_at).toLocaleString(localeCode, {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
        opt.textContent = `Edycja #${r.id} (${dateStr}) - ${r.status.toUpperCase()}`;
        runSelect.appendChild(opt);
      });

      // Load latest run automatically
      const latestRunId = runs[0].id;
      runSelect.value = latestRunId;
      await loadRunDetails(latestRunId);
    } catch (err) {
      showToast(`Error loading runs: ${err.message}`, "error");
    }
  }

  // Load Single Run Details and Items
  async function loadRunDetails(runId) {
    try {
      recsContainer.innerHTML = `
        <div class="loading-state">
          <div class="spinner"></div>
          <p>${t("loading_recommendations", "Ładowanie rekomendacji...")}</p>
        </div>
      `;

      const run = await api(`/api/recommendation-runs/${runId}`);
      state.currentRun = run;
      state.recommendations = run.recommendations || [];

      // Update Run Info Toolbar
      runMetaStatus.textContent = run.status.toUpperCase();
      runMetaStatus.className = `badge ${run.status === "completed" ? "badge-success" : "badge-warning"}`;

      const localeCode = state.currentLang === "en" ? "en-US" : "pl-PL";
      const dateFormatted = new Date(run.created_at).toLocaleString(localeCode);
      summaryMeta.textContent = `Run #${run.id} | Model: ${run.model_provider || "N/A"} (${run.model_name || "N/A"}) | ${dateFormatted}`;
      summaryText.textContent = run.summary || t("run_summary_empty", "Brak podsumowania dla tej edycji.");

      renderRecommendations();
      updateApprovalBar();
    } catch (err) {
      showToast(`Error loading edition #${runId}: ${err.message}`, "error");
    }
  }

  // Render Filtered Cards
  function renderRecommendations() {
    const { type, status } = state.filters;
    let filtered = state.recommendations;

    if (type !== "all") {
      filtered = filtered.filter((r) => r.media_item && r.media_item.media_type === type);
    }
    if (status !== "all") {
      filtered = filtered.filter((r) => r.status === status);
    }

    if (filtered.length === 0) {
      recsContainer.innerHTML = `
        <div class="empty-state">
          <span style="font-size: 3rem;">🔍</span>
          <h3>${t("no_recommendations", "Brak pozycji dla wybranych filtrów")}</h3>
          <p>${t("filter_status_all", "Zmień kryteria filtrowania, aby zobaczyć inne rekomendacje.")}</p>
        </div>
      `;
      return;
    }

    recsContainer.innerHTML = "";
    filtered.forEach((rec) => {
      recsContainer.appendChild(createCardElement(rec));
    });
  }

  // Create Recommendation Card HTML Element
  function createCardElement(rec) {
    const card = document.createElement("div");
    card.className = "card";
    card.id = `rec-card-${rec.id}`;

    const media = rec.media_item || {};
    const isMovie = media.media_type === "movie";
    const typeLabel = isMovie ? t("filter_type_movie", "FILM").toUpperCase() : t("filter_type_show", "SERIAL").toUpperCase();
    const typeBadgeClass = isMovie ? "badge-movie" : "badge-show";
    const title = media.title || "Unknown title";
    const year = media.year ? `(${media.year})` : "";
    const posterUrl = media.poster_path
      ? (media.poster_path.startsWith("http") ? media.poster_path : `https://image.tmdb.org/t/p/w500${media.poster_path}`)
      : null;

    const matchPercent = Math.round(rec.match_score);
    const tmdbRating = media.vote_average ? Number(media.vote_average).toFixed(1) : null;
    const isLowConfidence = rec.confidence < 0.75;

    // Status mapping with localized labels
    const statusMap = {
      pending: { label: t("filter_status_pending", "Do decyzji"), class: "badge-status-pending" },
      accepted: { label: t("filter_status_accepted", "Zaakceptowano"), class: "badge-status-accepted" },
      added: { label: t("filter_status_added", "W Simkl"), class: "badge-status-added" },
      rejected: { label: t("filter_status_rejected", "Odrzucono"), class: "badge-status-rejected" },
      seen: { label: t("filter_status_seen", "Obejrzane"), class: "badge-status-seen" },
    };
    const currentStatus = statusMap[rec.status] || { label: rec.status, class: "badge-status-pending" };

    const posFactorsHtml = (rec.positive_factors || [])
      .map((f) => `<span class="factor-tag factor-positive">✓ ${f}</span>`)
      .join("");

    const allRisks = [...(rec.risks || [])];
    if (isLowConfidence) {
      allRisks.unshift(t("risks_label", "Ograniczone metadane w bazie dla tego tytułu"));
    }

    const risksHtml = allRisks
      .map((r) => `<span class="factor-tag factor-risk">⚠ ${r}</span>`)
      .join("");

    card.innerHTML = `
      <div class="card-poster-wrap">
        ${posterUrl
          ? `<img src="${posterUrl}" alt="${title}" class="card-poster" loading="lazy" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'card-poster-placeholder\\'>🎬</div>';">`
          : `<div class="card-poster-placeholder">${isMovie ? "🎬" : "📺"}</div>`
        }
        <div class="card-poster-overlay">
          <span class="badge ${typeBadgeClass}">${typeLabel}</span>
          <span class="badge ${currentStatus.class}" id="status-badge-${rec.id}">${currentStatus.label}</span>
        </div>
      </div>
      <div class="card-body">
        <div class="card-title-row">
          <h3 class="card-title">${title}</h3>
          <span class="card-year">${year}</span>
        </div>
        <div class="card-match-bar">
          <span class="match-score-badge" title="Score: ${matchPercent}%">${matchPercent}%</span>
          ${tmdbRating ? `<span class="rating-badge" title="TMDB Community Rating">★ ${tmdbRating}</span>` : ""}
          <button class="btn-card-trailer" data-action="trailer" data-id="${rec.id}" title="${t("btn_trailer", "Zwiastun")}">
            🎬 ${t("btn_trailer", "Zwiastun")}
          </button>
        </div>
        <div class="card-reason">
          ${rec.reason}
        </div>
        ${posFactorsHtml || risksHtml ? `
          <div class="factors-section">
            ${posFactorsHtml}
            ${risksHtml}
          </div>
        ` : ""}
        <div class="card-actions">
          <button class="action-btn btn-accept ${rec.status === "accepted" ? "active" : ""}" data-action="accept" data-id="${rec.id}">
            ✓ ${t("btn_accept", "Zaakceptuj")}
          </button>
          <button class="action-btn btn-reject ${rec.status === "rejected" ? "active" : ""}" data-action="reject" data-id="${rec.id}">
            ✗ ${t("btn_reject", "Odrzuć")}
          </button>
          <button class="action-btn btn-seen ${rec.status === "seen" ? "active" : ""}" data-action="seen" data-id="${rec.id}">
            👁 ${t("btn_seen", "Widziałem")}
          </button>
          <button class="action-btn btn-later ${rec.status === "pending" ? "active" : ""}" data-action="later" data-id="${rec.id}">
            ⏱ ${t("btn_later", "Później")}
          </button>
        </div>
      </div>
    `;

    return card;
  }

  // Handle User Decision (Accept, Reject, Seen, Later)
  async function handleDecision(recId, decision) {
    try {
      const payload = {
        decisions: [{ recommendation_id: recId, decision }],
      };
      await api("/api/recommendations/decisions", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      // Update local state
      const target = state.recommendations.find((r) => r.id === recId);
      if (target) {
        if (decision === "accept") target.status = "accepted";
        else if (decision === "reject") target.status = "rejected";
        else if (decision === "seen") target.status = "seen";
        else if (decision === "later") target.status = "pending";
      }

      renderRecommendations();
      updateApprovalBar();

      showToast(`${t("toast_decision_saved", "Zapisano decyzję")}: ${decision.toUpperCase()}`, "success");
    } catch (err) {
      showToast(`Error saving decision: ${err.message}`, "error");
    }
  }

  // Update Sticky Bottom Approval Bar
  function updateApprovalBar() {
    const acceptedCount = state.recommendations.filter(
      (r) => r.status === "accepted"
    ).length;

    if (acceptedCount > 0) {
      approvedCountText.innerHTML = `${acceptedCount} <span>${t("approved_items_count", "pozycji zaakceptowanych")}</span>`;
      approvalBar.classList.remove("hidden");
    } else {
      approvalBar.classList.add("hidden");
    }
  }

  // Bulk Approve Accepted Items to Simkl
  async function submitBulkApprove() {
    const acceptedItems = state.recommendations.filter((r) => r.status === "accepted");
    if (acceptedItems.length === 0) return;

    btnSubmitApprove.disabled = true;
    btnSubmitApprove.textContent = `⏳ ${t("toast_approve_submitting", "Wysyłanie do Simkl...")}`;

    try {
      const payload = {
        recommendation_ids: acceptedItems.map((r) => r.id),
      };
      const res = await api("/api/recommendations/approve", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      res.items.forEach((item) => {
        const found = state.recommendations.find((r) => r.media_item && r.media_item.title === item.title);
        if (found && item.success) {
          found.status = "added";
        }
      });

      renderRecommendations();
      updateApprovalBar();
      showToast(t("toast_approve_success", "Pomyślnie dodano do Simkl!"), "success");
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btnSubmitApprove.disabled = false;
      btnSubmitApprove.textContent = `🚀 ${t("btn_submit_approve", "Wyślij zaakceptowane do Simkl")}`;
    }
  }

  // Open Taste Profile Modal
  async function openProfileModal() {
    modalProfile.classList.remove("hidden");
    profileContentContainer.innerHTML = `<p class="loading-text">${t("profile_loading", "Ładowanie profilu gustu...")}</p>`;

    try {
      const profile = await api("/api/profile");
      state.activeProfile = profile;
      if (profilePillText) profilePillText.textContent = `${t("profile_active", "Profil: Aktywny")}: ${profile.version}`;

      const content = profile.content || {};
      const genres = content.genres || [];
      const themes = content.themes || [];
      const directors = content.directors_or_creators || [];
      const anti = content.anti_preferences || [];
      const temp = content.temporary_interests || [];
      const localeCode = state.currentLang === "en" ? "en-US" : "pl-PL";
      const createdDate = new Date(profile.created_at).toLocaleString(localeCode);

      profileContentContainer.innerHTML = `
        <div style="margin-bottom: 1rem; padding: 0.75rem 1rem; background: var(--bg-primary); border-radius: var(--radius-sm); border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <div>
            <strong>Version:</strong> <span class="badge badge-profile">${profile.version}</span>
            <span style="color: var(--text-muted); font-size: 0.85rem; margin-left: 0.5rem;">(${createdDate})</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--color-success);">● ${t("profile_active", "Aktywny")}</div>
        </div>

        <div class="profile-section-title">Summary</div>
        <p style="color: var(--text-main); font-size: 0.95rem; line-height: 1.6; background: var(--bg-primary); padding: 0.85rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
          ${content.summary || "No summary available."}
        </p>

        <div class="profile-section-title">Preferred Genres</div>
        <div class="profile-tags-grid">
          ${genres.map(g => `<span class="profile-tag"><strong>${g.name}</strong> <span class="profile-tag-weight">${Math.round(g.weight * 100)}%</span></span>`).join("")}
        </div>

        <div class="profile-section-title">Key Themes</div>
        <div class="profile-tags-grid">
          ${themes.map(t => `<span class="profile-tag">🎯 ${t.name} <span class="profile-tag-weight">${Math.round(t.weight * 100)}%</span></span>`).join("")}
        </div>

        <div class="profile-section-title">Favorite Directors & Creators</div>
        <div class="profile-tags-grid">
          ${directors.map(d => `<span class="profile-tag">🎬 ${d}</span>`).join("")}
        </div>

        ${anti.length > 0 ? `
          <div class="profile-section-title" style="color: var(--color-danger);">⛔ Anti-preferences (Exclusions)</div>
          <div class="profile-tags-grid">
            ${anti.map(a => `<span class="profile-tag" style="border-color: rgba(239, 68, 68, 0.4); color: #fca5a5;">✕ ${a}</span>`).join("")}
          </div>
        ` : ""}

        ${temp.length > 0 ? `
          <div class="profile-section-title" style="color: var(--color-warning);">⏳ Temporary Interests</div>
          <div class="profile-tags-grid">
            ${temp.map(ti => `<span class="profile-tag">✨ ${ti.name}</span>`).join("")}
          </div>
        ` : ""}
      `;

      btnGenerateProfile.textContent = t("btn_generate_profile", "⚡ Wygeneruj profil (Gemini)");
    } catch (err) {
      state.activeProfile = null;
      if (profilePillText) profilePillText.textContent = t("profile_none", "Profil: Brak");
      profileContentContainer.innerHTML = `
        <div class="empty-state" style="padding: 2rem 1rem;">
          <span style="font-size: 3rem;">🧠</span>
          <h3 style="margin: 0.75rem 0 0.5rem;">${t("profile_none", "Brak wygenerowanego profilu gustu")}</h3>
          <p style="color: var(--text-muted); max-width: 500px; margin: 0 auto 1.5rem;">
            Click below to generate a taste profile via Gemini based on your Simkl library.
          </p>
        </div>
      `;
      btnGenerateProfile.textContent = t("btn_generate_profile", "⚡ Wygeneruj profil (Gemini)");
    }
  }

  // Generate Profile Handler
  async function handleGenerateProfile() {
    btnGenerateProfile.disabled = true;
    const origText = btnGenerateProfile.textContent;
    btnGenerateProfile.textContent = `⏳ ${t("toast_profile_generating", "Generowanie profilu...")}`;

    try {
      const payload = { language: state.currentLang };
      const newProfile = await api("/api/profile/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.activeProfile = newProfile;
      if (profilePillText) profilePillText.textContent = `${t("profile_active", "Profil: Aktywny")}: ${newProfile.version}`;
      showToast(t("toast_profile_success", "Nowy profil gustu został pomyślnie wygenerowany!"), "success");
      await openProfileModal();
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btnGenerateProfile.disabled = false;
      btnGenerateProfile.textContent = origText;
    }
  }

  // Open Decision History Modal
  async function openHistoryModal() {
    modalHistory.classList.remove("hidden");
    historyTableContainer.innerHTML = `<p class="loading-text">${t("profile_loading", "Ładowanie...")}</p>`;

    try {
      const decisions = await api("/api/recommendations/decisions?limit=50");
      if (!decisions || decisions.length === 0) {
        historyTableContainer.innerHTML = `<p>${t("history_empty", "Brak zapisanych decyzji.")}</p>`;
        return;
      }

      const localeCode = state.currentLang === "en" ? "en-US" : "pl-PL";
      let rowsHtml = decisions
        .map((d) => {
          const dateStr = new Date(d.created_at).toLocaleString(localeCode);
          const decisionBadgeClass =
            d.decision === "accept"
              ? "badge-status-accepted"
              : d.decision === "reject"
              ? "badge-status-rejected"
              : d.decision === "seen"
              ? "badge-status-seen"
              : "badge-status-pending";

          return `
            <tr>
              <td>${dateStr}</td>
              <td><strong>${d.media_title || "Unknown"}</strong> (${d.media_year || "-"})</td>
              <td><span class="badge ${d.media_type === "movie" ? "badge-movie" : "badge-show"}">${(d.media_type || "").toUpperCase()}</span></td>
              <td><span class="badge ${decisionBadgeClass}">${d.decision.toUpperCase()}</span></td>
              <td>${d.note || "-"}</td>
            </tr>
          `;
        })
        .join("");

      historyTableContainer.innerHTML = `
        <table class="history-table">
          <thead>
            <tr>
              <th>${t("history_col_date", "Data")}</th>
              <th>${t("history_col_title", "Tytuł")}</th>
              <th>${t("history_col_type", "Typ")}</th>
              <th>${t("history_col_decision", "Decyzja")}</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      `;
    } catch (err) {
      historyTableContainer.innerHTML = `<p style="color: var(--color-danger)">Error: ${err.message}</p>`;
    }
  }

  // Language Selector Listener
  if (langSelect) {
    langSelect.addEventListener("change", async (e) => {
      await applyLanguage(e.target.value);
    });
  }

  // Event Listeners
  runSelect.addEventListener("change", (e) => {
    if (e.target.value) {
      loadRunDetails(Number(e.target.value));
    }
  });

  // Type Filters
  document.querySelectorAll("[data-type-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("[data-type-filter]").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.filters.type = chip.dataset.typeFilter;
      renderRecommendations();
    });
  });

  // Status Filters
  document.querySelectorAll("[data-status-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("[data-status-filter]").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.filters.status = chip.dataset.statusFilter;
      renderRecommendations();
    });
  });

  // Card Action Buttons (Event Delegation)
  recsContainer.addEventListener("click", (e) => {
    const trailerBtn = e.target.closest("[data-action='trailer']");
    if (trailerBtn) {
      const recId = Number(trailerBtn.dataset.id);
      if (recId) openTrailerModal(recId);
      return;
    }

    const btn = e.target.closest(".action-btn");
    if (!btn) return;
    const recId = Number(btn.dataset.id);
    const action = btn.dataset.action;
    if (recId && action) {
      handleDecision(recId, action);
    }
  });

  // Trailer Modal Handlers
  const modalTrailer = document.getElementById("modal-trailer");
  const modalTrailerTitle = document.getElementById("modal-trailer-title");
  const trailerPlayerContainer = document.getElementById("trailer-player-container");
  const trailerFallbackContainer = document.getElementById("trailer-fallback-container");
  const trailerFallbackLink = document.getElementById("trailer-fallback-link");
  const trailerDirectLink = document.getElementById("trailer-direct-link");

  function closeTrailerModal() {
    if (!modalTrailer) return;
    modalTrailer.classList.add("hidden");
    trailerPlayerContainer.innerHTML = "";
    trailerFallbackContainer.classList.add("hidden");
    trailerPlayerContainer.classList.remove("hidden");
  }

  async function openTrailerModal(recId) {
    const rec = state.recommendations.find((r) => r.id === recId);
    const title = rec?.media_item?.title || "Trailer";
    const year = rec?.media_item?.year ? `(${rec.media_item.year})` : "";
    modalTrailerTitle.textContent = `${title} ${year} — ${t("modal_trailer_title", "Zwiastun")}`;

    trailerPlayerContainer.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>${t("loading_recommendations", "Ładowanie...")}</p></div>`;
    trailerFallbackContainer.classList.add("hidden");
    trailerPlayerContainer.classList.remove("hidden");
    modalTrailer.classList.remove("hidden");

    try {
      let trailerKey = rec?.trailer_key || rec?.media_item?.trailer_key;
      let trailerUrl = rec?.trailer_url || rec?.media_item?.trailer_url;
      let fallbackUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${title} ${year} official trailer`)}`;

      if (!trailerKey) {
        const data = await api(`/api/recommendations/${recId}/trailer`);
        trailerKey = data.trailer_key;
        trailerUrl = data.trailer_url;
        fallbackUrl = data.fallback_search_url || fallbackUrl;
        if (rec && trailerKey) {
          rec.trailer_key = trailerKey;
          rec.trailer_url = trailerUrl;
          if (rec.media_item) {
            rec.media_item.trailer_key = trailerKey;
            rec.media_item.trailer_url = trailerUrl;
          }
        }
      }

      if (trailerKey) {
        trailerPlayerContainer.classList.remove("hidden");
        trailerFallbackContainer.classList.add("hidden");
        trailerPlayerContainer.innerHTML = `
          <iframe
            src="https://www.youtube-nocookie.com/embed/${trailerKey}?autoplay=1&rel=0"
            title="${title} Trailer"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen>
          </iframe>
        `;
        trailerDirectLink.href = trailerUrl || `https://www.youtube.com/watch?v=${trailerKey}`;
        trailerDirectLink.classList.remove("hidden");
      } else {
        trailerPlayerContainer.classList.add("hidden");
        trailerFallbackContainer.classList.remove("hidden");
        trailerFallbackLink.href = fallbackUrl;
        trailerDirectLink.classList.add("hidden");
      }
    } catch (err) {
      trailerPlayerContainer.classList.add("hidden");
      trailerFallbackContainer.classList.remove("hidden");
      trailerFallbackLink.href = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${title} ${year} official trailer`)}`;
      trailerDirectLink.classList.add("hidden");
      showToast(`Trailer error: ${err.message}`, "error");
    }
  }

  // Submit Approval
  btnSubmitApprove.addEventListener("click", submitBulkApprove);

  // Sync Simkl
  btnSync.addEventListener("click", async () => {
    btnSync.disabled = true;
    btnSync.innerHTML = `<span class="icon">⏳</span> ${t("toast_sync_started", "Synchronizacja...")}`;
    try {
      const res = await api("/api/sync/simkl", { method: "POST" });
      showToast(t("toast_sync_success", "Synchronizacja z Simkl zakończona pomyślnie!"), "success");
    } catch (err) {
      showToast(`Sync error: ${err.message}`, "error");
    } finally {
      btnSync.disabled = false;
      btnSync.innerHTML = `<span class="icon">🔄</span> ${t("btn_sync", "Sync Simkl")}`;
    }
  });

  // New Run Modal & Submission
  btnNewRun.addEventListener("click", () => {
    modalNewRun.classList.remove("hidden");
  });

  formNewRun.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!state.activeProfile) {
      modalNewRun.classList.add("hidden");
      showToast("Przed utworzeniem rekomendacji należy wygenerować profil gustu.", "warning");
      openProfileModal();
      return;
    }

    const movieLimit = Number(document.getElementById("input-movie-limit").value) || 10;
    const showLimit = Number(document.getElementById("input-show-limit").value) || 5;
    const excludeAnim = document.getElementById("input-exclude-animation").checked;
    const runLang = document.getElementById("input-run-language")?.value || state.currentLang;

    const btnSubmit = document.getElementById("btn-submit-run");
    btnSubmit.disabled = true;
    btnSubmit.textContent = `⏳ ${t("toast_run_generating", "Generowanie...")}`;

    try {
      const payload = {
        movie_limit: movieLimit,
        show_limit: showLimit,
        mode: "ondemand",
        exclude_genres: excludeAnim ? ["Animation"] : [],
        language: runLang,
      };
      const newRun = await api("/api/recommendation-runs", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      modalNewRun.classList.add("hidden");
      showToast(`${t("toast_run_success", "Nowa edycja rekomendacji została wygenerowana!")} #${newRun.id}`, "success");
      await loadRuns();
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = t("btn_start_generation", "Uruchom generowanie");
    }
  });

  // Profile Modal Listeners
  if (btnProfile) btnProfile.addEventListener("click", openProfileModal);
  if (btnGenerateProfile) btnGenerateProfile.addEventListener("click", handleGenerateProfile);

  // History Modal
  btnHistory.addEventListener("click", openHistoryModal);

  // Modal Closers
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      modalNewRun.classList.add("hidden");
      modalHistory.classList.add("hidden");
      if (modalProfile) modalProfile.classList.add("hidden");
    });
  });

  document.querySelectorAll("[data-close-trailer]").forEach((btn) => {
    btn.addEventListener("click", closeTrailerModal);
  });

  // Close modal on click outside dialog
  window.addEventListener("click", (e) => {
    if (e.target === modalNewRun) modalNewRun.classList.add("hidden");
    if (e.target === modalHistory) modalHistory.classList.add("hidden");
    if (e.target === modalProfile) modalProfile.classList.add("hidden");
    if (e.target === modalTrailer) closeTrailerModal();
  });

  // Close trailer modal on Escape key
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modalTrailer && !modalTrailer.classList.contains("hidden")) {
      closeTrailerModal();
    }
  });

  // Run app
  init();
});
