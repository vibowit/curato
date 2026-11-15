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
  };

  // DOM Elements
  const profilePill = document.getElementById("profile-pill");
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
        const msg = errData.message || `Błąd serwera (HTTP ${resp.status})`;
        throw new Error(msg);
      }
      if (resp.status === 204) return null;
      return await resp.json();
    } catch (err) {
      console.error(`API Error on ${path}:`, err);
      throw err;
    }
  }

  // Initial Load
  async function init() {
    await Promise.all([loadProfile(), loadRuns()]);
  }

  // Load Active Taste Profile
  async function loadProfile() {
    try {
      const data = await api("/api/profile");
      state.activeProfile = data;
      profilePill.textContent = `Profil: ${data.version}`;
      profilePill.title = `Profil aktywny: ${data.version}`;
    } catch (err) {
      profilePill.textContent = "Profil: brak";
    }
  }

  // Load All Recommendation Runs
  async function loadRuns() {
    try {
      const runs = await api("/api/recommendation-runs?limit=30");
      state.runs = runs;
      runSelect.innerHTML = "";

      if (!runs || runs.length === 0) {
        runSelect.innerHTML = '<option value="">Brak wygenerowanych edycji</option>';
        recsContainer.innerHTML = `
          <div class="empty-state">
            <span style="font-size: 3rem;">🎬</span>
            <h3>Brak rekomendacji</h3>
            <p>Nie wygenerowano jeszcze żadnej edycji. Kliknij "Nowa Edycja", aby stworzyć pierwsze propozycje.</p>
          </div>
        `;
        return;
      }

      runs.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.id;
        const dateStr = new Date(r.created_at).toLocaleString("pl-PL", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
        opt.textContent = `Edycja #${r.id} (${dateStr}) - ${r.recommendations_count} pozycji`;
        runSelect.appendChild(opt);
      });

      // Load the latest run by default
      await loadRunDetails(runs[0].id);
    } catch (err) {
      showToast(`Błąd ładowania edycji: ${err.message}`, "error");
    }
  }

  // Load Details of a Single Run
  async function loadRunDetails(runId) {
    recsContainer.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>Ładowanie pozycji edycji #${runId}...</p>
      </div>
    `;

    try {
      const run = await api(`/api/recommendation-runs/${runId}`);
      state.currentRun = run;
      state.recommendations = run.recommendations || [];

      // Update Summary Header
      const dateStr = new Date(run.created_at).toLocaleString("pl-PL");
      summaryMeta.textContent = `Edycja #${run.id} | Profil: ${run.profile_version || "n/a"} | Model: ${run.model_name || run.model_provider || "LLM"} | Utworzono: ${dateStr}`;
      summaryText.textContent = run.summary || "Brak podsumowania dla tej edycji.";

      runMetaStatus.textContent = run.status.toUpperCase();
      runMetaStatus.className = `badge ${run.status === "completed" ? "badge-status-accepted" : "badge-status-pending"}`;

      renderRecommendations();
      updateApprovalBar();
    } catch (err) {
      showToast(`Nie udało się załadować edycji: ${err.message}`, "error");
    }
  }

  // Render Filtered Recommendations Grid
  function renderRecommendations() {
    const { type, status } = state.filters;
    const filtered = state.recommendations.filter((rec) => {
      const mType = rec.media_item ? rec.media_item.media_type : "movie";
      if (type !== "all" && mType !== type) return false;
      if (status !== "all" && rec.status !== status) return false;
      return true;
    });

    if (filtered.length === 0) {
      recsContainer.innerHTML = `
        <div class="empty-state">
          <span style="font-size: 2.5rem;">🔍</span>
          <h3>Brak pozycji dla wybranych filtrów</h3>
          <p>Zmień kryteria filtrowania, aby zobaczyć inne rekomendacje.</p>
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
    const typeLabel = isMovie ? "FILM" : "SERIAL";
    const typeBadgeClass = isMovie ? "badge-movie" : "badge-show";
    const title = media.title || "Nieznany tytuł";
    const year = media.year ? `(${media.year})` : "";
    const posterUrl = media.poster_path
      ? (media.poster_path.startsWith("http") ? media.poster_path : `https://image.tmdb.org/t/p/w500${media.poster_path}`)
      : null;

    const matchPercent = Math.round(rec.match_score);
    const tmdbRating = media.vote_average ? Number(media.vote_average).toFixed(1) : null;
    const isLowConfidence = rec.confidence < 0.75;

    // Status mapping
    const statusMap = {
      pending: { label: "Do decyzji", class: "badge-status-pending" },
      accepted: { label: "Zaakceptowano", class: "badge-status-accepted" },
      added: { label: "W Simkl (Plan to Watch)", class: "badge-status-added" },
      rejected: { label: "Odrzucono", class: "badge-status-rejected" },
      seen: { label: "Obejrzane", class: "badge-status-seen" },
    };
    const currentStatus = statusMap[rec.status] || { label: rec.status, class: "badge-status-pending" };

    const posFactorsHtml = (rec.positive_factors || [])
      .map((f) => `<span class="factor-tag factor-positive">✓ ${f}</span>`)
      .join("");

    const risksHtml = (rec.risks || [])
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
          <span class="match-score-badge" title="Dopasowanie do profilu gustu">${matchPercent}% dopasowania</span>
          ${tmdbRating ? `<span class="rating-badge" title="Ocena społeczności TMDB">★ ${tmdbRating}</span>` : ""}
          ${isLowConfidence ? `<span class="warning-badge" title="Ograniczone metadane w bazie dla tego tytułu">⚠️ Mało danych</span>` : ""}
          <button class="btn-card-trailer" data-action="trailer" data-id="${rec.id}" title="Obejrzyj oficjalny zwiastun">
            🎬 Zwiastun
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
            ✓ Zaakceptuj
          </button>
          <button class="action-btn btn-reject ${rec.status === "rejected" ? "active" : ""}" data-action="reject" data-id="${rec.id}">
            ✗ Odrzuć
          </button>
          <button class="action-btn btn-seen ${rec.status === "seen" ? "active" : ""}" data-action="seen" data-id="${rec.id}">
            👁 Widziałem
          </button>
          <button class="action-btn btn-later ${rec.status === "pending" ? "active" : ""}" data-action="later" data-id="${rec.id}">
            ⏱ Później
          </button>
        </div>
      </div>
    `;

    return card;
  }

  // Handle User Decision (Accept, Reject, Seen, Later)
  async function handleDecision(recId, decision) {
    const card = document.getElementById(`rec-card-${recId}`);
    const originalStatus = state.recommendations.find((r) => r.id === recId)?.status;

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

      // Re-render card or update elements
      renderRecommendations();
      updateApprovalBar();

      const labels = {
        accept: "zaakceptowana",
        reject: "odrzucona",
        seen: "oznaczona jako obejrzana",
        later: "odłożona na później",
      };
      showToast(`Pozycja została ${labels[decision] || decision}.`, "success");
    } catch (err) {
      showToast(`Błąd zapisu decyzji: ${err.message}`, "error");
    }
  }

  // Update Sticky Bottom Approval Bar
  function updateApprovalBar() {
    const acceptedCount = state.recommendations.filter(
      (r) => r.status === "accepted"
    ).length;

    if (acceptedCount > 0) {
      approvedCountText.textContent = `${acceptedCount} pozycji zaakceptowanych`;
      approvalBar.classList.remove("hidden");
    } else {
      approvalBar.classList.add("hidden");
    }
  }

  // Bulk Approve Accepted Items to Simkl
  async function submitBulkApprove() {
    const acceptedItems = state.recommendations.filter((r) => r.status === "accepted");
    if (acceptedItems.length === 0) {
      showToast("Brak zaakceptowanych pozycji do wysłania.", "info");
      return;
    }

    btnSubmitApprove.disabled = true;
    btnSubmitApprove.textContent = "⏳ Wysyłanie do Simkl...";

    try {
      const payload = {
        recommendation_ids: acceptedItems.map((r) => r.id),
      };
      const res = await api("/api/recommendations/approve", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      // Update local statuses
      res.items.forEach((item) => {
        const found = state.recommendations.find((r) => r.media_item && r.media_item.title === item.title);
        if (found && item.success) {
          found.status = "added";
        }
      });

      renderRecommendations();
      updateApprovalBar();

      showToast(
        `Sukces! Dodano ${res.added_count} pozycji do Simkl Plan to Watch (już obecne: ${res.already_added_count}).`,
        "success"
      );
    } catch (err) {
      showToast(`Błąd podczas zapisu do Simkl: ${err.message}`, "error");
    } finally {
      btnSubmitApprove.disabled = false;
      btnSubmitApprove.textContent = "🚀 Wyślij zaakceptowane do Simkl";
    }
  }

  // Open Decision History Modal
  async function openHistoryModal() {
    modalHistory.classList.remove("hidden");
    historyTableContainer.innerHTML = '<p class="loading-text">Ładowanie historii decyzji...</p>';

    try {
      const decisions = await api("/api/recommendations/decisions?limit=50");
      if (!decisions || decisions.length === 0) {
        historyTableContainer.innerHTML = "<p>Brak zapisanych decyzji.</p>";
        return;
      }

      let rowsHtml = decisions
        .map((d) => {
          const dateStr = new Date(d.created_at).toLocaleString("pl-PL");
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
              <td><strong>${d.media_title || "Nieznany"}</strong> (${d.media_year || "-"})</td>
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
              <th>Data</th>
              <th>Tytuł</th>
              <th>Typ</th>
              <th>Decyzja</th>
              <th>Notatka</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      `;
    } catch (err) {
      historyTableContainer.innerHTML = `<p style="color: var(--color-danger)">Błąd: ${err.message}</p>`;
    }
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
    // Clear iframe to immediately stop playback and audio
    trailerPlayerContainer.innerHTML = "";
    trailerFallbackContainer.classList.add("hidden");
    trailerPlayerContainer.classList.remove("hidden");
  }

  async function openTrailerModal(recId) {
    const rec = state.recommendations.find((r) => r.id === recId);
    const title = rec?.media_item?.title || "Zwiastun";
    const year = rec?.media_item?.year ? `(${rec.media_item.year})` : "";
    modalTrailerTitle.textContent = `${title} ${year} — Zwiastun`;

    // Clear previous state and show modal with loading spinner
    trailerPlayerContainer.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Ładowanie zwiastuna...</p></div>`;
    trailerFallbackContainer.classList.add("hidden");
    trailerPlayerContainer.classList.remove("hidden");
    modalTrailer.classList.remove("hidden");

    try {
      let trailerKey = rec?.trailer_key || rec?.media_item?.trailer_key;
      let trailerUrl = rec?.trailer_url || rec?.media_item?.trailer_url;
      let fallbackUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${title} ${year} official trailer`)}`;

      if (!trailerKey) {
        // Fetch on-demand from API
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
        // Show fallback search link
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
      showToast(`Nie udało się załadować zwiastuna: ${err.message}`, "error");
    }
  }

  // Submit Approval
  btnSubmitApprove.addEventListener("click", submitBulkApprove);

  // Sync Simkl
  btnSync.addEventListener("click", async () => {
    btnSync.disabled = true;
    btnSync.innerHTML = '<span class="icon">⏳</span> Synchronizacja...';
    try {
      const res = await api("/api/sync/simkl", { method: "POST" });
      showToast(
        `Synchronizacja zakończona pomyślnie. Dodano: ${res.items_added}, zaktualizowano: ${res.items_updated}.`,
        "success"
      );
    } catch (err) {
      showToast(`Błąd synchronizacji: ${err.message}`, "error");
    } finally {
      btnSync.disabled = false;
      btnSync.innerHTML = '<span class="icon">🔄</span> Sync Simkl';
    }
  });

  // New Run Modal & Submission
  btnNewRun.addEventListener("click", () => {
    modalNewRun.classList.remove("hidden");
  });

  formNewRun.addEventListener("submit", async (e) => {
    e.preventDefault();
    const movieLimit = Number(document.getElementById("input-movie-limit").value) || 10;
    const showLimit = Number(document.getElementById("input-show-limit").value) || 5;
    const excludeAnim = document.getElementById("input-exclude-animation").checked;

    const btnSubmit = document.getElementById("btn-submit-run");
    btnSubmit.disabled = true;
    btnSubmit.textContent = "⏳ Generowanie (może potrwać ok. 30s)...";

    try {
      const payload = {
        movie_limit: movieLimit,
        show_limit: showLimit,
        mode: "ondemand",
        exclude_genres: excludeAnim ? ["Animation"] : [],
      };
      const newRun = await api("/api/recommendation-runs", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      modalNewRun.classList.add("hidden");
      showToast(`Pomyślnie wygenerowano nową edycję #${newRun.id}!`, "success");
      await loadRuns();
    } catch (err) {
      showToast(`Błąd generowania rekomendacji: ${err.message}`, "error");
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Uruchom generowanie";
    }
  });

  // History Modal
  btnHistory.addEventListener("click", openHistoryModal);

  // Modal Closers
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      modalNewRun.classList.add("hidden");
      modalHistory.classList.add("hidden");
    });
  });

  document.querySelectorAll("[data-close-trailer]").forEach((btn) => {
    btn.addEventListener("click", closeTrailerModal);
  });

  // Close modal on click outside dialog
  window.addEventListener("click", (e) => {
    if (e.target === modalNewRun) modalNewRun.classList.add("hidden");
    if (e.target === modalHistory) modalHistory.classList.add("hidden");
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
