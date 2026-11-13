/**
 * Main Application Controller for the 5-Stack Coordinator Analytics Hub.
 */

import { loadDashboardData } from './data-loader.js';
import {
  renderOverviewTab,
  renderSessionsTab,
  renderPlayersTab,
  openPlayerModal,
  closePlayerModal,
  renderSynergiesTab,
  renderSquadBuilderTab,
  renderTrendsTab,
  updateWeightSimulator,
  updateFeedbackPreview
} from './views.js';
import {
  toggleBuilderPlayer,
  selectBuilderPreset
} from './squad-builder.js';

const VALID_TABS = new Set(['overview', 'sessions', 'players', 'synergies', 'builder', 'trends', 'faq']);

let RAW_BUNDLE = null;
let datasetMode = 'demo';
let currentTab = 'overview';
let filters = {
  role: 'ALL',
  player: 'ALL',
  mode: 'ALL',
  minGames: 1,
  search: ''
};
let playerSort = { key: 'avg_rating', asc: false };
let synergyCategory = 'ALL';
let synergySort = { key: 'synergy_score', asc: false };
let champSort = { key: 'picks', asc: false };

function getActiveData() {
  if (!RAW_BUNDLE) return {};
  return datasetMode === 'live' ? RAW_BUNDLE.live : RAW_BUNDLE.demo;
}

function syncUrlState() {
  try {
    if (window.location.protocol === 'file:') return;
    const params = new URLSearchParams(window.location.search);
    params.set('mode', datasetMode);
    params.set('tab', currentTab);
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash || ''}`;
    window.history.replaceState(null, '', nextUrl);
  } catch (err) {
    // Ignore history restrictions in sandboxed environments
  }
}

function renderAll() {
  const data = getActiveData();
  renderOverviewTab(data, filters);
  renderSessionsTab(data, filters);
  renderPlayersTab(data, filters, playerSort);
  renderSynergiesTab(data, filters, synergyCategory, synergySort);
  renderSquadBuilderTab(data);
  renderTrendsTab(data, filters, champSort, currentTab);
}

function setDatasetMode(mode) {
  datasetMode = mode === 'live' ? 'live' : 'demo';
  closePlayerModal();
  document.getElementById('btn-mode-live')?.classList.toggle('active', datasetMode === 'live');
  document.getElementById('btn-mode-demo')?.classList.toggle('active', datasetMode === 'demo');

  const banner = document.getElementById('demo-notice-banner');
  const bannerBtn = document.getElementById('banner-switch-live-btn');
  const bannerText = document.getElementById('demo-banner-text');

  if (banner && bannerBtn && bannerText) {
    if (datasetMode === 'demo') {
      banner.style.display = 'flex';
      bannerText.textContent = RAW_BUNDLE.has_live_matches
        ? 'Viewing rich portfolio Demo Preview data. Click "View Live Server Data" to inspect actual synced squad records.'
        : 'Viewing portfolio Demo Preview data (live server currently has 0 synced matches). Explore all charts, Squad Builder, and leaderboards below.';
      bannerBtn.textContent = 'View Live Server Data';
      bannerBtn.onclick = () => setDatasetMode('live');
    } else if (!RAW_BUNDLE.has_live_matches) {
      banner.style.display = 'flex';
      bannerText.textContent = 'Live data currently has 0 logged matches. Log a match via /sync-matches or /log-match, or switch to Demo Preview.';
      bannerBtn.textContent = 'Enable Demo Preview';
      bannerBtn.onclick = () => setDatasetMode('demo');
    } else {
      banner.style.display = 'none';
    }
  }

  const data = getActiveData();
  const groupEl = document.getElementById('header-group-name');
  if (groupEl) {
    groupEl.textContent = data.group_name || '5 Stackers';
  }

  const playerSelect = document.getElementById('filter-player');
  if (playerSelect) {
    const prevVal = playerSelect.value;
    playerSelect.innerHTML = '<option value="ALL">All Squad Members</option>';
    (data.players || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = `${p.name} (${p.primary_role})`;
      playerSelect.appendChild(opt);
    });
    if ([...playerSelect.options].some(o => o.value === prevVal)) {
      playerSelect.value = prevVal;
    } else {
      playerSelect.value = 'ALL';
      filters.player = 'ALL';
    }
  }

  syncUrlState();
  renderAll();
}

function switchTab(tabId, scrollAnchor = null) {
  const targetTab = VALID_TABS.has(tabId) ? tabId : 'overview';
  currentTab = targetTab;

  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === targetTab);
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === 'tab-' + targetTab);
  });

  const filterBar = document.getElementById('global-filter-bar');
  if (filterBar) {
    filterBar.style.display = (targetTab === 'faq' || targetTab === 'builder') ? 'none' : 'flex';
  }

  syncUrlState();

  if (targetTab === 'trends') {
    setTimeout(() => renderTrendsTab(getActiveData(), filters, champSort, currentTab), 30);
  }
  if (scrollAnchor) {
    const el = document.getElementById(scrollAnchor);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }
}

function resetFilters() {
  filters = { role: 'ALL', player: 'ALL', mode: 'ALL', minGames: 1, search: '' };
  document.querySelectorAll('#role-filter-pills .role-pill').forEach(p => {
    p.classList.toggle('active', p.dataset.role === 'ALL');
  });
  const playerSel = document.getElementById('filter-player');
  const modeSel = document.getElementById('filter-mode');
  const minGamesEl = document.getElementById('filter-min-games');
  const minGamesVal = document.getElementById('min-games-val');
  const searchEl = document.getElementById('filter-search');

  if (playerSel) playerSel.value = 'ALL';
  if (modeSel) modeSel.value = 'ALL';
  if (minGamesEl) minGamesEl.value = '1';
  if (minGamesVal) minGamesVal.textContent = '1';
  if (searchEl) searchEl.value = '';
  renderAll();
}

function bindEvents() {
  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  document.querySelectorAll('#role-filter-pills .role-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('#role-filter-pills .role-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      filters.role = pill.dataset.role;
      renderAll();
    });
  });

  document.getElementById('filter-player')?.addEventListener('change', e => {
    filters.player = e.target.value;
    renderAll();
  });
  document.getElementById('filter-mode')?.addEventListener('change', e => {
    filters.mode = e.target.value;
    renderAll();
  });
  document.getElementById('filter-min-games')?.addEventListener('input', e => {
    filters.minGames = parseInt(e.target.value, 10) || 1;
    const valEl = document.getElementById('min-games-val');
    if (valEl) valEl.textContent = filters.minGames;
    renderAll();
  });
  document.getElementById('filter-search')?.addEventListener('input', e => {
    filters.search = e.target.value.trim().toLowerCase();
    renderAll();
  });
}

// Expose window bindings for inline handlers in HTML and dynamically rendered markup
window.setDatasetMode = setDatasetMode;
window.switchTab = switchTab;
window.resetFilters = resetFilters;
window.openPlayerModal = (playerName, compareName = '__SQUAD_AVG__') => openPlayerModal(getActiveData(), playerName, compareName);
window.closePlayerModal = closePlayerModal;
window.renderSessionsTab = () => renderSessionsTab(getActiveData(), filters);

window.sortPlayersBy = key => {
  if (playerSort.key === key) {
    playerSort.asc = !playerSort.asc;
  } else {
    playerSort.key = key;
    playerSort.asc = (key === 'name' || key === 'main_role');
  }
  renderPlayersTab(getActiveData(), filters, playerSort);
};

window.setSynergyCategory = cat => {
  synergyCategory = cat;
  document.querySelectorAll('#synergy-pair-pills .role-pill').forEach(p => {
    p.classList.toggle('active', p.dataset.pair === cat);
  });
  renderSynergiesTab(getActiveData(), filters, synergyCategory, synergySort);
};

window.sortSynergiesBy = key => {
  if (synergySort.key === key) {
    synergySort.asc = !synergySort.asc;
  } else {
    synergySort.key = key;
    synergySort.asc = false;
  }
  renderSynergiesTab(getActiveData(), filters, synergyCategory, synergySort);
};

window.sortChampsBy = key => {
  if (champSort.key === key) {
    champSort.asc = !champSort.asc;
  } else {
    champSort.key = key;
    champSort.asc = (key === 'champion' || key === 'archetype' || key === 'primary_role');
  }
  renderTrendsTab(getActiveData(), filters, champSort, currentTab);
};

window.updateWeightSimulator = () => updateWeightSimulator(RAW_BUNDLE);
window.updateFeedbackPreview = () => updateFeedbackPreview(RAW_BUNDLE);
window.toggleBuilderPlayer = playerName => {
  const data = getActiveData();
  toggleBuilderPlayer(playerName, data, () => renderSquadBuilderTab(data));
};
window.selectBuilderPreset = preset => {
  const data = getActiveData();
  selectBuilderPreset(preset, data, () => renderSquadBuilderTab(data));
};

async function initDashboard() {
  try {
    RAW_BUNDLE = await loadDashboardData();
  } catch (err) {
    console.error(err);
    const main = document.querySelector('main.main-container');
    if (main) {
      main.innerHTML = `<div class="hex-card empty-state">${err.message}</div>`;
    }
    return;
  }

  const updatedEl = document.getElementById('header-updated-at');
  if (updatedEl) {
    updatedEl.textContent = RAW_BUNDLE.generated_at ? `Synced ${RAW_BUNDLE.generated_at}` : 'Ready';
  }

  // Default to 'demo' unless '?mode=live' is explicitly passed
  const params = new URLSearchParams(window.location.search);
  const requestedMode = (params.get('mode') || '').toLowerCase();
  datasetMode = requestedMode === 'live' ? 'live' : 'demo';

  const requestedTab = (params.get('tab') || '').toLowerCase();
  if (VALID_TABS.has(requestedTab)) {
    currentTab = requestedTab;
  }

  bindEvents();
  setDatasetMode(datasetMode);
  switchTab(currentTab);
  updateWeightSimulator(RAW_BUNDLE);
  updateFeedbackPreview(RAW_BUNDLE);
}

window.addEventListener('DOMContentLoaded', initDashboard);
