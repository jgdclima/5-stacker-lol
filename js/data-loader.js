/**
 * Async JSON payload loader with zero-CORS `file://` fallback.
 *
 * Priority:
 * 1. Inline `<script id="dashboard-data">` (if present in standalone exported builds).
 * 2. Live HTTP fetch of `./data/demo_payload.json` + `./data/live_payload.json` (cache-busted).
 * 3. `window.__DASHBOARD_BUNDLE__` from `./data/dashboard_bundle.js` (for `file://` browsing).
 */

import {
  buildRoleMatchIndex,
  getSquadPlayerNameSet,
  isSquadLineupEntry,
  resolvePlayerRoles
} from './utils.js';

function splitLegacyChampionSummaries(dataset, squadNames = null) {
  const matches = dataset?.matches || [];
  if (matches.length === 0) return;

  const needsGlobalSplit = Array.isArray(dataset.champions) && dataset.champions.some(c => !c.role);
  const needsPlayerSplit = Array.isArray(dataset.players) && dataset.players.some(
    p => Array.isArray(p.champion_pool) && p.champion_pool.some(c => !c.role)
  );
  if (!needsGlobalSplit && !needsPlayerSplit) return;

  const globalMap = {};
  const playerMap = {};

  matches.forEach(m => {
    const isWin = m.result === 'WIN';
    const dur = parseFloat(m.duration_min || 30);
    Object.entries(m.lineup || {}).forEach(([role, p]) => {
      if (!isSquadLineupEntry(p, squadNames) || !p.champion) return;
      const champ = p.champion;
      const arch = p.archetype || 'bruiser';
      const kills = p.kills || 0;
      const deaths = p.deaths || 0;
      const assists = p.assists || 0;
      const damage = p.damage || 0;
      const cs = p.cs || 0;
      const vision = p.vision || 0;
      const rating = parseFloat(p.rating || 65);

      if (needsGlobalSplit) {
        const gKey = `${champ}||${role}`;
        if (!globalMap[gKey]) {
          globalMap[gKey] = {
            champion: champ, role, archetype: arch, picks: 0, wins: 0, losses: 0,
            kills: 0, deaths: 0, assists: 0, damage: 0, cs: 0, vision: 0, dur: 0, ratingSum: 0, pilots: {}
          };
        }
        const ge = globalMap[gKey];
        ge.picks += 1;
        if (isWin) ge.wins += 1; else ge.losses += 1;
        ge.kills += kills; ge.deaths += deaths; ge.assists += assists;
        ge.damage += damage; ge.cs += cs; ge.vision += vision; ge.dur += dur; ge.ratingSum += rating;
        if (p.player) ge.pilots[p.player] = (ge.pilots[p.player] || 0) + 1;
      }

      if (needsPlayerSplit && p.player) {
        const pm = (playerMap[p.player] ||= {});
        const pKey = `${champ}||${role}`;
        if (!pm[pKey]) {
          pm[pKey] = {
            champion: champ, role, archetype: arch, games: 0, wins: 0,
            kills: 0, deaths: 0, assists: 0, ratingSum: 0
          };
        }
        const pe = pm[pKey];
        pe.games += 1;
        if (isWin) pe.wins += 1;
        pe.kills += kills; pe.deaths += deaths; pe.assists += assists; pe.ratingSum += rating;
      }
    });
  });

  if (needsGlobalSplit) {
    dataset.champions = Object.values(globalMap).map(c => {
      const g = c.picks;
      const d = Math.max(1, c.dur);
      return {
        champion: c.champion,
        role: c.role,
        archetype: c.archetype,
        picks: g,
        wins: c.wins,
        losses: c.losses,
        win_rate: +((c.wins / g) * 100).toFixed(1),
        kda: +((c.kills + c.assists) / Math.max(1, c.deaths)).toFixed(2),
        avg_kills: +(c.kills / g).toFixed(1),
        avg_deaths: +(c.deaths / g).toFixed(1),
        avg_assists: +(c.assists / g).toFixed(1),
        dpm: Math.round(c.damage / d),
        cspm: +(c.cs / d).toFixed(1),
        vspm: +(c.vision / d).toFixed(2),
        avg_rating: +(c.ratingSum / g).toFixed(1),
        primary_role: c.role,
        top_pilot: Object.keys(c.pilots).sort((a, b) => c.pilots[b] - c.pilots[a])[0] || 'N/A',
        pilots: c.pilots
      };
    }).sort((a, b) => (b.picks - a.picks) || (b.win_rate - a.win_rate) || (b.avg_rating - a.avg_rating));
  }

  if (needsPlayerSplit) {
    dataset.players.forEach(pl => {
      const pm = playerMap[pl.name];
      if (!pm) return;
      pl.champion_pool = Object.values(pm).map(c => {
        const g = c.games;
        return {
          champion: c.champion,
          role: c.role,
          archetype: c.archetype,
          games: g,
          wins: c.wins,
          losses: g - c.wins,
          win_rate: +((c.wins / g) * 100).toFixed(1),
          kda: +((c.kills + c.assists) / Math.max(1, c.deaths)).toFixed(2),
          avg_kills: +(c.kills / g).toFixed(1),
          avg_deaths: +(c.deaths / g).toFixed(1),
          avg_assists: +(c.assists / g).toFixed(1),
          avg_rating: +(c.ratingSum / g).toFixed(1),
          primary_role: c.role
        };
      }).sort((a, b) => (b.games - a.games) || (b.avg_rating - a.avg_rating));
    });
  }
}

export function normalizeDatasetRoles(dataset) {
  if (!dataset || !Array.isArray(dataset.players)) return dataset;
  const squadNames = getSquadPlayerNameSet(dataset);
  const roleIndex = buildRoleMatchIndex(dataset.matches || [], squadNames);
  dataset.players.forEach(p => {
    const resolved = resolvePlayerRoles(p, roleIndex[p.name]);
    p.primary_role = resolved.primary_role;
    p.secondary_role = resolved.secondary_role;
    p.main_role = resolved.main_role;
  });
  splitLegacyChampionSummaries(dataset, squadNames);
  return dataset;
}

function normalizePayload(payload) {
  if (!payload) return payload;
  normalizeDatasetRoles(payload.live);
  normalizeDatasetRoles(payload.demo);
  return payload;
}

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
      return normalizePayload(JSON.parse(inlineEl.textContent));
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

      return normalizePayload({
        generated_at: livePayload?.generated_at || demoPayload?.generated_at || fallbackBundle.generated_at || '',
        github_repo: base?.github_repo || fallbackBundle.github_repo || 'jgdclima/5-stacker-lol',
        has_live_matches: Boolean(hasLiveMatches),
        rating_formulas: demoPayload?.rating_formulas || livePayload?.rating_formulas || fallbackBundle.rating_formulas || {},
        live: liveDataset,
        demo: demoDataset
      });
    }
  }

  // 3. Fallback to synchronous JS bundle for local `file://` usage
  if (window.__DASHBOARD_BUNDLE__) {
    return normalizePayload(window.__DASHBOARD_BUNDLE__);
  }

  throw new Error(
    'Unable to load dashboard payloads. Run `python export_dashboard.py` to generate web/data/ JSON and JS bundle files.'
  );
}
