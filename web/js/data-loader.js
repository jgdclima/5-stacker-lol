/**
 * Async JSON payload loader with zero-CORS `file://` fallback.
 *
 * Priority:
 * 1. Inline `<script id="dashboard-data">` (if present in standalone exported builds).
 * 2. Live HTTP fetch of `./data/demo_payload.json` + `./data/live_payload.json` (cache-busted).
 * 3. `window.__DASHBOARD_BUNDLE__` from `./data/dashboard_bundle.js` (for `file://` browsing).
 */

function emptyLiveDataset() {
  return {
    is_demo: false,
    group_name: '5 Stackers',
    kpis: {
      total_matches: 0,
      wins: 0,
      losses: 0,
      win_rate: 0.0,
      streak_type: 'NONE',
      streak_count: 0,
      active_sessions_count: 0,
      total_sessions_count: 0
    },
    sessions: [],
    matches: [],
    players: [],
    synergies: {
      botlane: [],
      mid_jungle: [],
      top_jungle: [],
      support_jungle: []
    },
    champions: [],
    archetypes: [],
    role_distribution: {
      Top: { games: 0, wins: 0 },
      Jungle: { games: 0, wins: 0 },
      Mid: { games: 0, wins: 0 },
      Bot: { games: 0, wins: 0 },
      Support: { games: 0, wins: 0 }
    }
  };
}

async function fetchJsonSafe(url) {
  const resp = await fetch(url, { cache: 'no-store' });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} fetching ${url}`);
  }
  return resp.json();
}

export async function loadDashboardData() {
  // 1. Standalone single-file payload (when exported via custom --output path)
  const inlineEl = document.getElementById('dashboard-data');
  if (inlineEl && inlineEl.textContent.trim() && !inlineEl.textContent.includes('__DASHBOARD_JSON_PAYLOAD__')) {
    try {
      return JSON.parse(inlineEl.textContent);
    } catch (err) {
      console.warn('[DataLoader] Failed to parse inline dashboard-data JSON:', err);
    }
  }

  // 2. HTTP / GitHub Pages / NAS server fetch
  if (window.location.protocol !== 'file:') {
    const cacheBust = `ts=${Date.now()}`;
    const [demoRes, liveRes] = await Promise.allSettled([
      fetchJsonSafe(`./data/demo_payload.json?${cacheBust}`),
      fetchJsonSafe(`./data/live_payload.json?${cacheBust}`)
    ]);

    const demoPayload = demoRes.status === 'fulfilled' ? demoRes.value : null;
    const livePayload = liveRes.status === 'fulfilled' ? liveRes.value : null;

    if (demoPayload || livePayload) {
      const base = livePayload || demoPayload;
      const fallbackBundle = window.__DASHBOARD_BUNDLE__ || {};
      const liveDataset = livePayload?.dataset || fallbackBundle.live || emptyLiveDataset();
      const demoDataset = demoPayload?.dataset || fallbackBundle.demo || emptyLiveDataset();
      const hasLiveMatches = livePayload?.has_live_matches ??
        ((liveDataset.matches?.length || 0) > 0 || (liveDataset.sessions?.length || 0) > 0);

      return {
        generated_at: livePayload?.generated_at || demoPayload?.generated_at || fallbackBundle.generated_at || '',
        github_repo: base?.github_repo || fallbackBundle.github_repo || 'jgdclima/5-stacker-lol',
        has_live_matches: Boolean(hasLiveMatches),
        rating_formulas: demoPayload?.rating_formulas || livePayload?.rating_formulas || fallbackBundle.rating_formulas || {},
        live: liveDataset,
        demo: demoDataset
      };
    }
  }

  // 3. Fallback to synchronous JS bundle for local `file://` usage
  if (window.__DASHBOARD_BUNDLE__) {
    return window.__DASHBOARD_BUNDLE__;
  }

  throw new Error(
    'Unable to load dashboard payloads. Run `python export_dashboard.py` to generate web/data/ JSON and JS bundle files.'
  );
}
