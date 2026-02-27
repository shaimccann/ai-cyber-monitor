/**
 * AI & Cyber Daily Monitor - Dashboard Application
 */

(function () {
  "use strict";

  // State
  let allArticles = [];
  let filteredArticles = [];
  let currentCategory = "all";
  let currentPeriod = "today";
  let currentSearch = "";
  let availableDates = [];

  // DOM elements
  const articlesGrid = document.getElementById("articlesGrid");
  const loading = document.getElementById("loading");
  const noResults = document.getElementById("noResults");
  const searchInput = document.getElementById("searchInput");
  const dateSelect = document.getElementById("dateSelect");
  const statsTotal = document.getElementById("statsTotal");
  const statsAI = document.getElementById("statsAI");
  const statsCyber = document.getElementById("statsCyber");

  // Base path - detect if running locally or on GitHub Pages
  const BASE_PATH = (() => {
    const loc = window.location;
    // GitHub Pages: /repo-name/docs/ or custom domain
    // Local server: root serves project dir
    if (loc.protocol === "file:") {
      // Direct file open - try relative path
      return "..";
    }
    // HTTP server - use relative path from docs/
    return "..";
  })();

  // === Data Loading ===

  function getToday() {
    const now = new Date();
    return now.toISOString().split("T")[0];
  }

  function getDateRange(period) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    switch (period) {
      case "week": {
        const weekAgo = new Date(today);
        weekAgo.setDate(weekAgo.getDate() - 7);
        return weekAgo;
      }
      case "month": {
        const monthAgo = new Date(today);
        monthAgo.setMonth(monthAgo.getMonth() - 1);
        return monthAgo;
      }
      default:
        return today;
    }
  }

  function generateDateList(startDate, endDate) {
    const dates = [];
    const current = new Date(startDate);
    while (current <= endDate) {
      dates.push(current.toISOString().split("T")[0]);
      current.setDate(current.getDate() + 1);
    }
    return dates.reverse();
  }

  async function fetchArticles(date) {
    try {
      const resp = await fetch(`${BASE_PATH}/data/articles/${date}.json`);
      if (!resp.ok) return [];
      return await resp.json();
    } catch {
      return [];
    }
  }

  async function loadArticles() {
    const today = getToday();
    const monthAgo = new Date();
    monthAgo.setDate(monthAgo.getDate() - 30);
    availableDates = generateDateList(monthAgo, new Date());

    // Populate date selector
    dateSelect.innerHTML = "";
    for (const date of availableDates) {
      const opt = document.createElement("option");
      opt.value = date;
      opt.textContent = formatDateHe(date);
      if (date === today) opt.selected = true;
      dateSelect.appendChild(opt);
    }

    // Load articles based on period
    await loadArticlesForPeriod();
  }

  async function loadArticlesForPeriod() {
    loading.style.display = "block";
    noResults.style.display = "none";
    articlesGrid.innerHTML = "";
    articlesGrid.appendChild(loading);

    const selectedDate = dateSelect.value;
    let datesToLoad = [];

    if (selectedDate) {
      datesToLoad = [selectedDate];
    } else {
      const rangeStart = getDateRange(currentPeriod);
      datesToLoad = availableDates.filter(
        (d) => new Date(d) >= rangeStart
      );
    }

    const promises = datesToLoad.map((d) => fetchArticles(d));
    const results = await Promise.all(promises);
    allArticles = results.flat();

    applyFilters();
  }

  // Max articles to display
  const MAX_DISPLAY = 10;

  // === Filtering ===

  function scoreArticle(article) {
    // Rank by importance: more sources = more important, cyber threats ranked higher
    let score = 0;
    score += (article.duplicate_count || 1) * 10;
    score += (article.sources || []).length * 5;
    // Boost cyber articles with threat-related keywords
    const title = (article.title_original || "").toLowerCase();
    const threatWords = ["breach", "attack", "vulnerability", "exploit", "ransomware", "malware", "hack", "zero-day", "critical", "cve"];
    for (const word of threatWords) {
      if (title.includes(word)) score += 8;
    }
    return score;
  }

  function applyFilters() {
    let matched = allArticles.filter((article) => {
      // Category filter
      if (currentCategory !== "all" && article.category !== currentCategory) {
        return false;
      }

      // Search filter
      if (currentSearch) {
        const search = currentSearch.toLowerCase();
        const title = (article.title_he || article.title_original || "").toLowerCase();
        const summary = (article.summary_he || article.description || "").toLowerCase();
        const details = (article.details_he || "").toLowerCase();
        if (!title.includes(search) && !summary.includes(search) && !details.includes(search)) {
          return false;
        }
      }

      return true;
    });

    // Sort by importance score, then take top 10
    matched.sort((a, b) => scoreArticle(b) - scoreArticle(a));
    filteredArticles = matched.slice(0, MAX_DISPLAY);

    updateStats(matched.length);
    renderArticles();
  }

  function updateStats(totalMatched) {
    const ai = filteredArticles.filter((a) => a.category === "ai").length;
    const cyber = filteredArticles.filter((a) => a.category === "cyber").length;

    statsTotal.textContent = `מציג ${filteredArticles.length} מתוך ${totalMatched} עדכונים`;
    statsAI.textContent = `${ai} AI`;
    statsCyber.textContent = `${cyber} סייבר`;
  }

  // === Rendering ===

  function formatDateHe(dateStr) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString("he-IL", {
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  }

  function formatTime(isoStr) {
    try {
      const date = new Date(isoStr);
      return date.toLocaleTimeString("he-IL", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  function createCard(article) {
    const card = document.createElement("div");
    card.className = "card";

    const isAI = article.category === "ai";
    const badgeClass = isAI ? "card__badge--ai" : "card__badge--cyber";
    const badgeText = isAI ? "🤖 AI" : "🔒 סייבר";

    const title = article.title_he || article.title_original || "ללא כותרת";
    const fullDesc = article.description || "";
    // Short summary: first ~80 chars for collapsed view
    const summary = article.summary_he || truncateText(fullDesc, 120);
    // Details: prefer details_he, fallback to full description
    const details = article.details_he || fullDesc;
    const dateStr = formatDateHe(article.published || article.date || "");

    // Primary article link
    const articleUrl = article.url || (article.sources && article.sources[0] && article.sources[0].url) || "";

    // Sources list for expanded view
    const sources = article.sources || [
      { name: article.source_name, url: article.url },
    ];
    const sourcesHtml = sources
      .map((s) => `<li><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.name)} ↗</a></li>`)
      .join("");

    // Article link button
    const articleLinkHtml = articleUrl
      ? `<a href="${escapeHtml(articleUrl)}" target="_blank" rel="noopener" class="card__read-more">קרא את המאמר המלא ↗</a>`
      : "";

    card.innerHTML = `
      <div class="card__header">
        <span class="card__badge ${badgeClass}">${badgeText}</span>
        <span class="card__date">${dateStr}</span>
      </div>
      <h3 class="card__title">${escapeHtml(title)}</h3>
      <p class="card__summary">${escapeHtml(summary)}</p>
      <span class="card__expand-hint">לחץ להרחבה</span>
      <div class="card__details">
        <p class="card__details-text">${escapeHtml(details)}</p>
        ${articleLinkHtml}
        <div class="card__sources-section">
          <strong>מקורות:</strong>
          <ul class="card__sources-list">${sourcesHtml}</ul>
        </div>
      </div>
    `;

    // Toggle expand on click
    card.addEventListener("click", (e) => {
      if (e.target.tagName === "A") return;
      // Close other expanded cards
      document.querySelectorAll(".card--expanded").forEach((c) => {
        if (c !== card) c.classList.remove("card--expanded");
      });
      card.classList.toggle("card--expanded");
    });

    return card;
  }

  function truncateText(text, maxLen) {
    if (!text || text.length <= maxLen) return text || "";
    return text.substring(0, maxLen).replace(/\s+\S*$/, "") + "...";
  }

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function renderArticles() {
    loading.style.display = "none";
    articlesGrid.innerHTML = "";

    if (filteredArticles.length === 0) {
      noResults.style.display = "block";
      return;
    }

    noResults.style.display = "none";

    // Already sorted by importance in applyFilters
    for (const article of filteredArticles) {
      articlesGrid.appendChild(createCard(article));
    }
  }

  // === Event Listeners ===

  // Category filter buttons
  document.querySelectorAll("[data-category]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-category]").forEach((b) => b.classList.remove("filter-btn--active"));
      btn.classList.add("filter-btn--active");
      currentCategory = btn.dataset.category;
      applyFilters();
    });
  });

  // Period filter buttons
  document.querySelectorAll("[data-period]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-period]").forEach((b) => b.classList.remove("filter-btn--active"));
      btn.classList.add("filter-btn--active");
      currentPeriod = btn.dataset.period;
      dateSelect.value = "";
      loadArticlesForPeriod();
    });
  });

  // Search
  let searchTimeout;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      currentSearch = searchInput.value.trim();
      applyFilters();
    }, 300);
  });

  // Date selector
  dateSelect.addEventListener("change", () => {
    loadArticlesForPeriod();
  });

  // Initialize
  loadArticles();
})();
