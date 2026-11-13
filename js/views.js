/**
 * View Rendering Modules for All Dashboard Tabs & Interactive Player Modal.
 */

import {
  escapeHtml,
  getSquadPlayerNameSet,
  gradeClass,
  isSquadLineupEntry,
  statusBadgeClass,
  PILLAR_DEFINITIONS,
  ROLES_ORDER
} from './utils.js';
import { computeExecutiveInsights, computeSquadRoleBenchmark } from './insights.js';
import {
  renderTrendsCharts,
  renderPlayerRadarChart,
  destroyPlayerRadarChart
} from './charts.js';
import { renderSquadBuilderTab } from './squad-builder.js';

export function matchPassesFilters(match, filters, squadNames = null) {
  if (filters.mode !== 'ALL') {
    const mMode = (match.mode || '').toLowerCase();
    if (filters.mode === 'Ranked 5s' && !mMode.includes('5s')) return false;
    if (filters.mode === 'Ranked Flex' && !mMode.includes('flex')) return false;
    if (filters.mode === 'Normal' && (mMode.includes('5s') || mMode.includes('flex'))) return false;
  }

  const lineup = match.lineup || {};
  const squadEntries = Object.entries(lineup).filter(([, p]) => isSquadLineupEntry(p, squadNames));

  if (filters.player !== 'ALL') {
    const hasPlayer = squadEntries.some(
      ([r, p]) => p.player === filters.player && (filters.role === 'ALL' || r === filters.role)
    );
    if (!hasPlayer) return false;
  } else if (filters.role !== 'ALL') {
    if (!isSquadLineupEntry(lineup[filters.role], squadNames)) return false;
  }

  if (filters.search) {
    const q = filters.search;
    const inMeta =
      (match.match_id || '').toLowerCase().includes(q) ||
      (match.mode || '').toLowerCase().includes(q) ||
      (match.mvp || '').toLowerCase().includes(q);
    const inLineup = squadEntries.some(([, p]) =>
      (p.player || '').toLowerCase().includes(q) ||
      (p.champion || '').toLowerCase().includes(q) ||
      (p.highlight || '').toLowerCase().includes(q)
    );
    if (!inMeta && !inLineup) return false;
  }

  return true;
}

function renderInsightsHtml(insights) {
  return (insights || []).map(ins => `
    <div class="insight-card tone-${escapeHtml(ins.tone || 'cyan')}">
      <div class="insight-header">
        <span class="insight-cat">${escapeHtml(ins.category)}</span>
        <span class="insight-metric">${escapeHtml(ins.metric)}</span>
      </div>
      <div class="insight-title">${escapeHtml(ins.title)}</div>
      <div class="insight-summary">${escapeHtml(ins.summary)}</div>
    </div>
  `).join('');
}

// --- TAB 1: OVERVIEW ---
export function renderOverviewTab(data, filters) {
  const squadNames = getSquadPlayerNameSet(data);
  const filteredMatches = (data.matches || []).filter(m => matchPassesFilters(m, filters, squadNames));

  // 1. Hero Active Session
  const activeSessions = (data.sessions || []).filter(s => ['IN_PROGRESS', 'READY', 'POLLING'].includes(s.status));
  const heroContainer = document.getElementById('overview-hero-session');

  if (activeSessions.length > 0) {
    const s = activeSessions[0];
    const starters = s.confirmed_players || [];
    const bench = s.bench_substitutes || [];
    const sMatches = s.session_matches || [];
    const sWins = sMatches.filter(m => m.result === 'WIN').length;
    const sLosses = sMatches.length - sWins;
    const pct = Math.min(100, Math.round((starters.length / 5) * 100));

    heroContainer.innerHTML = `
      <div class="hero-session">
        <div>
          <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
            <span class="badge ${statusBadgeClass(s.status)}">● ${escapeHtml(s.status)}</span>
            <span class="badge badge-polling">${escapeHtml(s.mode)}</span>
            <span style="font-size: 0.8rem; color: var(--text-muted);">ID: <code>${escapeHtml(s.session_id)}</code></span>
          </div>
          <h2 style="font-size: 1.35rem; color: var(--gold-bright); margin-bottom: 0.3rem;">
            📅 Next Squad Session: ${escapeHtml(s.scheduled_time)}
          </h2>
          <p style="font-size: 0.84rem; color: var(--text-muted); margin-bottom: 0.85rem;">
            Organized by <strong style="color: var(--text-main);">${escapeHtml(s.creator)}</strong> •
            ${starters.length}/5 Confirmed Starters ${starters.length >= 2 && starters.length < 5 ? '(Viable Duo/Trio/Flex Stack Ready!)' : ''}
          </p>
          <div class="progress-bar" style="margin-bottom: 0.85rem;">
            <div class="progress-fill" style="width: ${pct}%;"></div>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 0.45rem;">
            ${starters.map(p => `
              <span class="player-chip">
                <span class="role-badge">${escapeHtml(p.role_pref)}</span>
                <strong>${escapeHtml(p.name)}</strong>
              </span>
            `).join('')}
            ${bench.map(p => `
              <span class="player-chip" style="opacity: 0.75; border-style: dashed;">
                <span class="role-badge" style="background: rgba(200,170,110,0.2); color: var(--gold-primary);">BENCH</span>
                <span>${escapeHtml(p.name)} (${escapeHtml(p.role_pref)})</span>
              </span>
            `).join('')}
          </div>
        </div>
        <div style="display: flex; flex-direction: column; justify-content: space-between; background: rgba(6, 13, 24, 0.65); padding: 1rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
          <div>
            <div class="filter-label" style="margin-bottom: 0.4rem;">Live Session Activity &amp; W-L Tally</div>
            <div style="font-size: 1.1rem; font-weight: 800; color: var(--cyan-bright); margin-bottom: 0.5rem;">
              Session Record: ${sWins}W - ${sLosses}L (${sMatches.length} games)
            </div>
            <div style="font-size: 0.78rem; color: var(--text-muted); max-height: 95px; overflow-y: auto;">
              ${(s.activity_log || []).slice(-4).map(line => `<div style="margin-bottom: 0.2rem;">${escapeHtml(line)}</div>`).join('') || '<div>Waiting for lobby updates...</div>'}
            </div>
          </div>
          <div style="margin-top: 0.75rem; display: flex; justify-content: flex-end; gap: 0.5rem; flex-wrap: wrap;">
            <button class="mode-btn" style="border: 1px solid var(--border-subtle);" onclick="switchTab('builder')">🧠 Optimize Lineup</button>
            <button class="mode-btn active" onclick="switchTab('sessions')">View All ${(data.sessions || []).length} Sessions →</button>
          </div>
        </div>
      </div>
    `;
  } else {
    heroContainer.innerHTML = '';
  }

  // 2. KPI Cards
  const total = filteredMatches.length;
  const wins = filteredMatches.filter(m => m.result === 'WIN').length;
  const losses = total - wins;
  const wr = total > 0 ? ((wins / total) * 100).toFixed(1) : '0.0';

  const sortedPlayers = [...(data.players || [])].filter(p => p.games > 0)
    .sort((a, b) => (b.mvps - a.mvps) || (b.avg_rating - a.avg_rating));
  const topMvp = sortedPlayers[0] || { name: 'N/A', mvps: 0, avg_rating: 0 };

  const allSynergies = [
    ...(data.synergies?.botlane || []),
    ...(data.synergies?.mid_jungle || []),
    ...(data.synergies?.top_jungle || []),
    ...(data.synergies?.support_jungle || [])
  ].sort((a, b) => b.synergy_score - a.synergy_score);
  const bestDuo = allSynergies[0];
  const topChamp = (data.champions || [])[0];

  const streakLabel = data.kpis?.streak_count > 0
    ? `${data.kpis.streak_count}${data.kpis.streak_type === 'WIN' ? 'W' : 'L'} Streak`
    : 'No Streak';

  document.getElementById('overview-kpi-grid').innerHTML = `
    <div class="kpi-card">
      <div class="kpi-label">Filtered Matches</div>
      <div class="kpi-value">${total}</div>
      <div class="kpi-sub">${wins}W - ${losses}L Record</div>
    </div>
    <div class="kpi-card cyan-top">
      <div class="kpi-label">Squad Win Rate</div>
      <div class="kpi-value" style="color: ${parseFloat(wr) >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${wr}%</div>
      <div class="kpi-sub">Current Form: <strong>${streakLabel}</strong></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Squad MVP Leader</div>
      <div class="kpi-value">${escapeHtml(topMvp.name)}</div>
      <div class="kpi-sub">👑 ${topMvp.mvps} MVPs • ${topMvp.avg_rating} Avg Rating</div>
    </div>
    <div class="kpi-card cyan-top">
      <div class="kpi-label">Top Duo Synergy</div>
      <div class="kpi-value" style="font-size: 1.25rem;">${bestDuo ? escapeHtml(bestDuo.player_a + ' & ' + bestDuo.player_b) : 'N/A'}</div>
      <div class="kpi-sub">${bestDuo ? `${bestDuo.synergy_score} Score (${bestDuo.tier}) • ${bestDuo.win_rate}% WR` : 'Play 2+ squad games'}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Signature Comfort Pick</div>
      <div class="kpi-value">${topChamp ? escapeHtml(topChamp.champion) : 'N/A'}</div>
      <div class="kpi-sub">${topChamp ? `${escapeHtml(topChamp.role || topChamp.primary_role)} • ${topChamp.picks} Picks • ${topChamp.win_rate}% WR • ${topChamp.kda} KDA` : 'No picks logged yet'}</div>
    </div>
  `;

  // 3. Automated Executive Insights Strip
  const insightsEl = document.getElementById('overview-insights-grid');
  if (insightsEl) {
    const insights = computeExecutiveInsights(data, filteredMatches);
    insightsEl.innerHTML = renderInsightsHtml(insights);
  }

  // 4. Top Players & Top Synergies Mini Lists
  const topPlayersHtml = (data.players || []).filter(p => p.games > 0).slice(0, 5).map((p, idx) => `
    <div onclick="openPlayerModal('${escapeHtml(p.name)}')" style="display: flex; align-items: center; justify-content: space-between; padding: 0.55rem 0.65rem; border-bottom: 1px solid var(--border-subtle); cursor: pointer;">
      <div style="display: flex; align-items: center; gap: 0.65rem;">
        <span style="font-weight: 800; color: var(--gold-primary); width: 20px;">#${idx + 1}</span>
        <div>
          <div style="font-weight: 700; color: var(--text-main);">${escapeHtml(p.name)} <span class="role-badge">${escapeHtml(p.main_role)}</span></div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${p.games}G (${p.win_rate}% WR) • ${p.kda} KDA • 👑 ${p.mvps} MVP</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <span style="font-weight: 800; color: var(--gold-bright);">${p.avg_rating}</span>
        <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
      </div>
    </div>
  `).join('');
  document.getElementById('overview-top-players').innerHTML = topPlayersHtml || '<div class="empty-state">No player stats recorded yet.</div>';

  const topSynergiesHtml = allSynergies.slice(0, 5).map((s, idx) => `
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.55rem 0.65rem; border-bottom: 1px solid var(--border-subtle);">
      <div>
        <div style="font-weight: 700; color: var(--text-main);">#${idx + 1} ${escapeHtml(s.pair)}</div>
        <div style="font-size: 0.75rem; color: var(--text-muted);">
          <span class="highlight-chip">${escapeHtml(s.tag)}</span> • ${s.games}G (${s.win_rate}% WR) • ${s.combined_kda} KDA
        </div>
      </div>
      <div style="text-align: right;">
        <div style="font-weight: 800; color: var(--cyan-bright);">${s.synergy_score}</div>
        <div style="font-size: 0.7rem; color: var(--gold-primary); font-weight: 700;">${escapeHtml(s.tier)}</div>
      </div>
    </div>
  `).join('');
  document.getElementById('overview-top-synergies').innerHTML = topSynergiesHtml || '<div class="empty-state">No duo synergies calculated yet.</div>';

  // 5. Recent Matches Accordion List
  const matchesContainer = document.getElementById('overview-matches-list');
  if (filteredMatches.length === 0) {
    matchesContainer.innerHTML = '<div class="hex-card empty-state">No matches match your current filter selection.</div>';
    return;
  }

  matchesContainer.innerHTML = filteredMatches.map((m, idx) => {
    const isWin = m.result === 'WIN';
    const lineup = m.lineup || {};
    const rolesPresent = ROLES_ORDER.filter(r => lineup[r]).concat(Object.keys(lineup).filter(r => !ROLES_ORDER.includes(r)));

    const summaryPills = rolesPresent.map(r => {
      const p = lineup[r];
      const isMvp = p.player === m.mvp;
      return `
        <span class="player-chip" style="${isMvp ? 'border-color: var(--gold-primary); background: rgba(200,170,110,0.12);' : ''}">
          <span class="role-badge">${escapeHtml(r)}</span>
          <strong>${escapeHtml(p.player)}</strong>
          <span style="color: var(--gold-primary);">${escapeHtml(p.champion)}</span>
          <span style="font-size: 0.73rem; color: var(--text-muted);">${p.kills}/${p.deaths}/${p.assists}</span>
          <span class="grade-badge ${gradeClass(p.grade)}" style="transform: scale(0.88);">${escapeHtml(p.grade || 'A')}</span>
        </span>
      `;
    }).join('');

    const detailRows = rolesPresent.map(r => {
      const p = lineup[r];
      const isSquad = isSquadLineupEntry(p, squadNames);
      const kda = ((p.kills + p.assists) / Math.max(1, p.deaths)).toFixed(2);
      const isMvp = isSquad && p.player === m.mvp;
      const playerLabel = isSquad
        ? `<strong style="cursor: pointer; color: var(--gold-bright);" onclick="openPlayerModal('${escapeHtml(p.player)}')">${escapeHtml(p.player)}</strong>`
        : `<span style="color: var(--text-dim);">${escapeHtml(p.player)}</span> <span style="font-size: 0.7rem; color: var(--text-dim);">(Random)</span>`;
      return `
        <tr style="${isSquad ? '' : 'opacity: 0.65;'}">
          <td><span class="role-badge">${escapeHtml(r)}</span></td>
          <td>
            ${playerLabel}
            ${isMvp ? ' <span class="badge badge-polling">👑 MVP</span>' : ''}
          </td>
          <td>
            <strong>${escapeHtml(p.champion)}</strong>
            <span class="archetype-tag">${escapeHtml(p.archetype || '')}</span>
          </td>
          <td>${p.kills} / <span style="color: var(--loss-red);">${p.deaths}</span> / ${p.assists} <span style="color: var(--text-muted);">(${kda})</span></td>
          <td>${(p.damage || 0).toLocaleString()}</td>
          <td>${p.cs || 0}</td>
          <td>${p.vision || 0}</td>
          <td><span class="highlight-chip">${escapeHtml(p.highlight || 'Squad Contributor')}</span></td>
          <td>
            <strong style="color: var(--gold-bright); margin-right: 0.35rem;">${p.rating ?? '-'}</strong>
            <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade || '-')}</span>
          </td>
        </tr>
      `;
    }).join('');

    return `
      <div class="match-card ${isWin ? 'win' : 'loss'} ${idx === 0 ? 'expanded' : ''}" id="match-card-${idx}">
        <div class="match-header" onclick="document.getElementById('match-card-${idx}').classList.toggle('expanded')">
          <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
            <span class="badge ${isWin ? 'badge-win' : 'badge-loss'}">${isWin ? 'VICTORY' : 'DEFEAT'}</span>
            <strong style="color: var(--gold-bright);">${escapeHtml(m.mode || 'Match')}</strong>
            <span style="font-size: 0.8rem; color: var(--text-muted);">⏱️ ${m.duration_min || 30}m • 📅 ${escapeHtml(m.date || '')}</span>
            <span style="font-size: 0.8rem; color: var(--gold-primary);">👑 MVP: <strong>${escapeHtml(m.mvp || 'N/A')}</strong></span>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
            ${summaryPills}
          </div>
        </div>
        <div class="match-body">
          <div class="table-wrap" style="margin-top: 0.75rem;">
            <table class="hex-table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Player</th>
                  <th>Champion &amp; Archetype</th>
                  <th>K / D / A (Ratio)</th>
                  <th>Damage</th>
                  <th>CS</th>
                  <th>Vision</th>
                  <th>Standout Highlight</th>
                  <th>Holistic Rating</th>
                </tr>
              </thead>
              <tbody>${detailRows}</tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// --- TAB 2: SESSIONS ---
export function renderSessionsTab(data, filters) {
  const statusFilter = document.getElementById('session-status-filter').value;
  const sessions = (data.sessions || []).filter(s => {
    if (statusFilter === 'ACTIVE' && !['POLLING', 'READY', 'IN_PROGRESS'].includes(s.status)) return false;
    if (statusFilter !== 'ALL' && statusFilter !== 'ACTIVE' && s.status !== statusFilter) return false;
    if (filters.mode !== 'ALL') {
      const m = (s.mode || '').toLowerCase();
      if (filters.mode === 'Ranked 5s' && !m.includes('5s')) return false;
      if (filters.mode === 'Ranked Flex' && !m.includes('flex')) return false;
    }
    if (filters.player !== 'ALL') {
      const inStarters = (s.confirmed_players || []).some(p => p.name === filters.player);
      const inBench = (s.bench_substitutes || []).some(p => p.name === filters.player);
      if (!inStarters && !inBench && s.creator !== filters.player) return false;
    }
    if (filters.search) {
      const q = filters.search;
      const hay = `${s.session_id} ${s.scheduled_time} ${s.mode} ${s.creator} ${(s.confirmed_players || []).map(p => p.name).join(' ')}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const container = document.getElementById('sessions-grid');
  if (sessions.length === 0) {
    container.innerHTML = '<div class="hex-card empty-state">No sessions match the selected filters.</div>';
    return;
  }

  container.innerHTML = sessions.map(s => {
    const starters = s.confirmed_players || [];
    const bench = s.bench_substitutes || [];
    const declined = s.declined || [];
    const sMatches = s.session_matches || [];
    const wins = sMatches.filter(m => m.result === 'WIN').length;
    const losses = sMatches.length - wins;
    const pct = Math.min(100, Math.round((starters.length / 5) * 100));

    return `
      <div class="hex-card">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.6rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
            <span class="badge ${statusBadgeClass(s.status)}">${escapeHtml(s.status)}</span>
            <span class="badge badge-polling">${escapeHtml(s.mode)}</span>
          </div>
          <code style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(s.session_id)}</code>
        </div>

        <h3 style="color: var(--gold-bright); font-size: 1.1rem; margin-bottom: 0.25rem;">
          🕒 ${escapeHtml(s.scheduled_time)}
        </h3>
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem;">
          Created by <strong style="color: var(--text-main);">${escapeHtml(s.creator)}</strong> •
          Starters: <strong>${starters.length}/5</strong>
          ${starters.length >= 2 && starters.length < 5 ? '<span style="color: var(--cyan-bright);"> (Viable Flex/Duo/Trio)</span>' : ''}
        </div>

        <div class="progress-bar" style="margin-bottom: 0.85rem;">
          <div class="progress-fill" style="width: ${pct}%;"></div>
        </div>

        <div style="margin-bottom: 0.75rem;">
          <div class="filter-label" style="margin-bottom: 0.35rem;">Confirmed Starters (${starters.length}/5)</div>
          <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
            ${starters.length > 0 ? starters.map(p => `
              <span class="player-chip" onclick="openPlayerModal('${escapeHtml(p.name)}')" style="cursor: pointer;">
                <span class="role-badge">${escapeHtml(p.role_pref)}</span>
                <strong>${escapeHtml(p.name)}</strong>
              </span>
            `).join('') : '<span style="font-size: 0.8rem; color: var(--text-dim);">No starters confirmed yet</span>'}
          </div>
        </div>

        ${bench.length > 0 ? `
          <div style="margin-bottom: 0.75rem;">
            <div class="filter-label" style="margin-bottom: 0.35rem;">🛡️ Bench Substitutes (Auto-Promote Queue)</div>
            <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
              ${bench.map((p, idx) => `
                <span class="player-chip">
                  <span class="role-badge" style="background: rgba(200,170,110,0.2); color: var(--gold-primary);">#${idx + 1} ${escapeHtml(p.role_pref)}</span>
                  <span>${escapeHtml(p.name)}</span>
                </span>
              `).join('')}
            </div>
          </div>
        ` : ''}

        ${declined.length > 0 ? `
          <div style="font-size: 0.76rem; color: var(--text-dim); margin-bottom: 0.75rem;">
            ❌ Declined: ${declined.map(escapeHtml).join(', ')}
          </div>
        ` : ''}

        <div style="background: rgba(6, 13, 24, 0.65); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 0.7rem; font-size: 0.78rem;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem;">
            <span class="filter-label">Session Match Tally</span>
            <strong style="color: var(--cyan-bright);">${wins}W - ${losses}L (${sMatches.length} matches)</strong>
          </div>
          <div style="color: var(--text-muted); max-height: 85px; overflow-y: auto;">
            ${(s.activity_log || []).map(l => `<div style="margin-bottom: 0.15rem;">${escapeHtml(l)}</div>`).join('') || '<div>No activity logged.</div>'}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// --- TAB 3: PLAYERS & RADAR MODAL ---
export function renderPlayersTab(data, filters, playerSort) {
  let players = (data.players || []).filter(p => {
    if (filters.player !== 'ALL' && p.name !== filters.player) return false;
    if (filters.role !== 'ALL' && p.primary_role !== filters.role && p.secondary_role !== filters.role && p.main_role !== filters.role) return false;
    if (p.games > 0 && p.games < filters.minGames && filters.minGames > 1) return false;
    if (filters.search) {
      const q = filters.search;
      const hay = `${p.name} ${p.discord_tag} ${p.primary_role} ${p.secondary_role} ${(p.fav_champs || []).join(' ')}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  players.sort((a, b) => {
    const k = playerSort.key;
    const va = a[k] ?? 0;
    const vb = b[k] ?? 0;
    if (typeof va === 'string') {
      return playerSort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    return playerSort.asc ? (va - vb) : (vb - va);
  });

  const cardsGrid = document.getElementById('players-cards-grid');
  cardsGrid.innerHTML = players.map(p => {
    const riotIds = (p.accounts || []).map(a => a.riot_id).filter(Boolean);
    return `
      <div class="hex-card interactive" onclick="openPlayerModal('${escapeHtml(p.name)}')">
        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.75rem;">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div class="brand-crest" style="width: 40px; height: 40px; font-size: 1rem;">
              ${escapeHtml(p.name.slice(0, 2).toUpperCase())}
            </div>
            <div>
              <div style="font-size: 1.05rem; font-weight: 800; color: var(--gold-bright);">${escapeHtml(p.name)}</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">
                ${escapeHtml(p.discord_tag)}
                ${riotIds.length > 0 ? ` • <span style="color: var(--cyan-bright);">🎮 ${escapeHtml(riotIds[0])}</span>` : ''}
              </div>
            </div>
          </div>
          <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
        </div>

        <div style="display: flex; gap: 0.45rem; flex-wrap: wrap; margin-bottom: 0.85rem;">
          <span class="role-badge">Main: ${escapeHtml(p.primary_role)}</span>
          <span class="role-badge" style="background: rgba(200,170,110,0.15); color: var(--gold-primary);">2nd: ${escapeHtml(p.secondary_role)}</span>
          ${p.mvps > 0 ? `<span class="badge badge-polling">👑 ${p.mvps} MVP${p.mvps > 1 ? 's' : ''}</span>` : ''}
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; background: rgba(6, 13, 24, 0.65); padding: 0.65rem; border-radius: 8px; text-align: center; margin-bottom: 0.8rem;">
          <div>
            <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Win Rate</div>
            <div style="font-weight: 800; color: ${p.win_rate >= 50 ? 'var(--win-green)' : 'var(--text-main)'};">${p.win_rate}%</div>
            <div style="font-size: 0.68rem; color: var(--text-dim);">${p.wins}W-${p.losses}L</div>
          </div>
          <div>
            <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">KDA Ratio</div>
            <div style="font-weight: 800; color: var(--cyan-bright);">${p.kda}</div>
            <div style="font-size: 0.68rem; color: var(--text-dim);">${p.kills}/${p.deaths}/${p.assists}</div>
          </div>
          <div>
            <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Avg Rating</div>
            <div style="font-weight: 800; color: var(--gold-bright);">${p.avg_rating}</div>
            <div style="font-size: 0.68rem; color: var(--text-dim);">/ 100</div>
          </div>
        </div>

        <div style="font-size: 0.76rem; color: var(--text-muted);">
          <strong style="color: var(--gold-primary);">Fav Champs:</strong>
          ${(p.fav_champs || []).map(c => `<span class="archetype-tag" style="margin-left: 0.25rem;">${escapeHtml(c)}</span>`).join('')}
        </div>
      </div>
    `;
  }).join('') || '<div class="hex-card empty-state">No squad members match your filters.</div>';

  const tbody = document.getElementById('players-table-body');
  tbody.innerHTML = players.map((p, idx) => `
    <tr onclick="openPlayerModal('${escapeHtml(p.name)}')" style="cursor: pointer;">
      <td><strong>#${idx + 1}</strong></td>
      <td>
        <strong style="color: var(--gold-bright);">${escapeHtml(p.name)}</strong>
        <div style="font-size: 0.72rem; color: var(--text-muted);">${escapeHtml(p.discord_tag)}</div>
      </td>
      <td><span class="role-badge">${escapeHtml(p.primary_role)}</span> <span style="font-size: 0.75rem; color: var(--text-muted);">/ ${escapeHtml(p.secondary_role)}</span></td>
      <td>${p.games} <span style="color: var(--text-muted);">(${p.wins}W-${p.losses}L)</span></td>
      <td><strong style="color: ${p.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${p.win_rate}%</strong></td>
      <td><strong style="color: var(--cyan-bright);">${p.kda}</strong></td>
      <td>
        <strong style="color: var(--gold-bright); margin-right: 0.35rem;">${p.avg_rating}</strong>
        <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
      </td>
      <td>👑 ${p.mvps}</td>
      <td>${(p.fav_champs || []).map(c => `<span class="archetype-tag" style="margin-right: 0.25rem;">${escapeHtml(c)}</span>`).join('')}</td>
    </tr>
  `).join('');
}

export function openPlayerModal(data, playerName, compareName = '__SQUAD_AVG__') {
  const players = data.players || [];
  const p = players.find(x => x.name === playerName);
  if (!p) return;

  const squadBenchmark = computeSquadRoleBenchmark(players);
  const comparePlayer = compareName && compareName !== '__SQUAD_AVG__'
    ? players.find(x => x.name === compareName)
    : null;

  const pillars = p.pillars_avg || {};
  const pillarBarsHtml = PILLAR_DEFINITIONS.map(([k, label]) => {
    const val = pillars[k] || 0;
    const cmpVal = comparePlayer ? (comparePlayer.pillars_avg?.[k] || 0) : (squadBenchmark[k] || 50);
    const diff = (val - cmpVal).toFixed(1);
    const diffBadge = parseFloat(diff) >= 0
      ? `<span style="color: var(--win-green); font-size: 0.7rem;">(+${diff})</span>`
      : `<span style="color: var(--loss-red); font-size: 0.7rem;">(${diff})</span>`;
    return `
      <div class="pillar-row" style="grid-template-columns: 140px 1fr 82px;">
        <span style="color: var(--text-muted); font-weight: 600;">${label}</span>
        <div class="progress-bar">
          <div class="progress-fill" style="width: ${Math.min(100, val)}%;"></div>
        </div>
        <strong style="text-align: right; color: var(--gold-bright);">${val} ${diffBadge}</strong>
      </div>
    `;
  }).join('');

  const compareOptions = players
    .filter(other => other.name !== p.name && (other.games || 0) > 0)
    .map(other => `<option value="${escapeHtml(other.name)}" ${comparePlayer?.name === other.name ? 'selected' : ''}>${escapeHtml(other.name)} (${escapeHtml(other.primary_role)})</option>`)
    .join('');

  const champRows = (p.champion_pool || []).map(c => `
    <tr>
      <td><strong>${escapeHtml(c.champion)}</strong> <span class="archetype-tag">${escapeHtml(c.archetype)}</span></td>
      <td><span class="role-badge">${escapeHtml(c.role || c.primary_role)}</span></td>
      <td>${c.games} (${c.wins}W-${c.losses}L)</td>
      <td style="color: ${c.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'}; font-weight: 700;">${c.win_rate}%</td>
      <td>${c.avg_kills}/${c.avg_deaths}/${c.avg_assists} (<strong style="color: var(--cyan-bright);">${c.kda}</strong>)</td>
      <td><strong style="color: var(--gold-bright);">${c.avg_rating}</strong></td>
    </tr>
  `).join('');

  const recentRows = (p.recent_matches || []).slice(0, 8).map(m => `
    <tr>
      <td><span class="badge ${m.result === 'WIN' ? 'badge-win' : 'badge-loss'}">${m.result}</span></td>
      <td>${escapeHtml(m.date || '')}</td>
      <td><span class="role-badge">${escapeHtml(m.role)}</span> <strong>${escapeHtml(m.champion)}</strong></td>
      <td>${m.kills}/${m.deaths}/${m.assists}</td>
      <td><span class="highlight-chip">${escapeHtml(m.highlight || '')}</span> ${m.is_mvp ? '👑' : ''}</td>
      <td><strong>${m.rating}</strong> <span class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade)}</span></td>
    </tr>
  `).join('');

  const riotAccounts = (p.accounts || [])
    .map(a => `<code style="margin-right: 0.5rem; color: var(--cyan-bright);">${escapeHtml(a.riot_id)}</code>`)
    .join('') || '<span style="color: var(--text-dim);">Not linked yet (/link-riot)</span>';

  document.getElementById('player-modal-body').innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.1rem; padding-right: 2.2rem;">
      <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
        <div class="brand-crest" style="width: 54px; height: 54px; font-size: 1.35rem;">
          ${escapeHtml(p.name.slice(0, 2).toUpperCase())}
        </div>
        <div>
          <h2 style="color: var(--gold-bright); font-size: 1.45rem;">
            ${escapeHtml(p.name)}
            <span class="grade-badge ${gradeClass(p.grade)}" style="vertical-align: middle; margin-left: 0.4rem;">${escapeHtml(p.grade)}</span>
          </h2>
          <div style="font-size: 0.82rem; color: var(--text-muted);">
            Discord: <strong>${escapeHtml(p.discord_tag)}</strong> •
            Roles: <span class="role-badge">${escapeHtml(p.primary_role)}</span> / <span class="role-badge">${escapeHtml(p.secondary_role)}</span> •
            Linked Riot IDs: ${riotAccounts}
          </div>
        </div>
      </div>

      <div class="filter-group">
        <span class="filter-label">Compare Radar vs:</span>
        <select id="modal-compare-player" class="hex-select" onchange="openPlayerModal('${escapeHtml(p.name)}', this.value)">
          <option value="__SQUAD_AVG__" ${!comparePlayer ? 'selected' : ''}>Squad Average Benchmark</option>
          ${compareOptions}
        </select>
      </div>
    </div>

    <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 1.15rem;">
      <div class="kpi-card" style="padding: 0.75rem 0.9rem;">
        <div class="kpi-label">Career Win Rate</div>
        <div class="kpi-value" style="font-size: 1.25rem;">${p.win_rate}% (${p.wins}W-${p.losses}L)</div>
      </div>
      <div class="kpi-card cyan-top" style="padding: 0.75rem 0.9rem;">
        <div class="kpi-label">Holistic Rating</div>
        <div class="kpi-value" style="font-size: 1.25rem; color: var(--cyan-bright);">${p.avg_rating} / 100</div>
      </div>
      <div class="kpi-card" style="padding: 0.75rem 0.9rem;">
        <div class="kpi-label">Overall KDA</div>
        <div class="kpi-value" style="font-size: 1.25rem;">${p.kda}</div>
      </div>
      <div class="kpi-card cyan-top" style="padding: 0.75rem 0.9rem;">
        <div class="kpi-label">Match MVPs</div>
        <div class="kpi-value" style="font-size: 1.25rem;">👑 ${p.mvps}</div>
      </div>
    </div>

    <div class="grid-2" style="margin-bottom: 1.25rem;">
      <div class="hex-card" style="background: rgba(6, 13, 24, 0.7);">
        <div style="font-weight: 700; color: var(--gold-primary); margin-bottom: 0.55rem; font-size: 0.84rem; text-transform: uppercase;">
          🕸️ 6-Pillar Radar Comparison (${escapeHtml(p.name)} vs ${comparePlayer ? escapeHtml(comparePlayer.name) : 'Squad Avg'})
        </div>
        <div class="radar-box">
          <canvas id="player-radar-chart"></canvas>
        </div>
      </div>
      <div class="hex-card" style="background: rgba(6, 13, 24, 0.7); display: flex; flex-direction: column; justify-content: center;">
        <div style="font-weight: 700; color: var(--gold-primary); margin-bottom: 0.65rem; font-size: 0.84rem; text-transform: uppercase;">
          📊 Pillar Breakdown &amp; Delta vs ${comparePlayer ? escapeHtml(comparePlayer.name) : 'Squad Avg'}
        </div>
        ${pillarBarsHtml}
      </div>
    </div>

    <h3 style="color: var(--gold-bright); font-size: 1rem; margin-bottom: 0.55rem;">🐉 Personal Champion Pool</h3>
    <div class="table-wrap" style="margin-bottom: 1.25rem;">
      <table class="hex-table">
        <thead>
          <tr>
            <th>Champion</th>
            <th>Role</th>
            <th>Games</th>
            <th>Win Rate</th>
            <th>Avg K/D/A (Ratio)</th>
            <th>Avg Rating</th>
          </tr>
        </thead>
        <tbody>${champRows || '<tr><td colspan="6" class="empty-state">No champion games logged yet.</td></tr>'}</tbody>
      </table>
    </div>

    <h3 style="color: var(--gold-bright); font-size: 1rem; margin-bottom: 0.55rem;">⚔️ Recent Match Performances</h3>
    <div class="table-wrap">
      <table class="hex-table">
        <thead>
          <tr>
            <th>Outcome</th>
            <th>Date</th>
            <th>Role &amp; Champion</th>
            <th>K/D/A</th>
            <th>Highlight</th>
            <th>Rating</th>
          </tr>
        </thead>
        <tbody>${recentRows || '<tr><td colspan="6" class="empty-state">No recent matches logged yet.</td></tr>'}</tbody>
      </table>
    </div>
  `;

  document.getElementById('player-modal').classList.add('open');
  renderPlayerRadarChart('player-radar-chart', p, comparePlayer, squadBenchmark);
}

export function closePlayerModal() {
  destroyPlayerRadarChart();
  const modal = document.getElementById('player-modal');
  if (modal) modal.classList.remove('open');
}

// --- TAB 4: SYNERGIES ---
export function renderSynergiesTab(data, filters, synergyCategory, synergySort) {
  const synMap = data.synergies || {};
  const catLabels = {
    botlane: '🏹🛡️ Bot + Support',
    mid_jungle: '🔮🌲 Mid + Jungle',
    top_jungle: '⚔️🌲 Top + Jungle',
    support_jungle: '🛡️🌲 Support + Jungle'
  };

  let rows = [];
  Object.entries(catLabels).forEach(([key, label]) => {
    if (synergyCategory !== 'ALL' && synergyCategory !== key) return;
    (synMap[key] || []).forEach(item => {
      rows.push({ ...item, categoryKey: key, categoryLabel: label });
    });
  });

  rows = rows.filter(r => {
    if (r.games < filters.minGames) return false;
    if (filters.player !== 'ALL' && r.player_a !== filters.player && r.player_b !== filters.player) return false;
    if (filters.search) {
      const q = filters.search;
      const hay = `${r.pair} ${r.tag} ${r.tier} ${r.favorite_combo}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  rows.sort((a, b) => {
    const k = synergySort.key;
    return synergySort.asc ? (a[k] - b[k]) : (b[k] - a[k]);
  });

  const cardsGrid = document.getElementById('synergies-cards-grid');
  cardsGrid.innerHTML = rows.slice(0, 6).map((s, idx) => `
    <div class="hex-card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <span style="font-size: 0.75rem; color: var(--gold-primary); font-weight: 700;">${escapeHtml(s.categoryLabel)}</span>
        <span class="badge ${s.tier === 'S Tier' ? 'badge-ready' : 'badge-polling'}">${escapeHtml(s.tier)}</span>
      </div>
      <h3 style="color: var(--gold-bright); font-size: 1.05rem; margin-bottom: 0.3rem;">
        #${idx + 1} ${escapeHtml(s.player_a)} &amp; ${escapeHtml(s.player_b)}
      </h3>
      <div style="margin-bottom: 0.75rem;">
        <span class="highlight-chip">${escapeHtml(s.tag)}</span>
        <span class="archetype-tag" style="margin-left: 0.3rem;">Combo: ${escapeHtml(s.favorite_combo)}</span>
      </div>
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.4rem; background: rgba(6, 13, 24, 0.65); padding: 0.6rem; border-radius: 8px; text-align: center; font-size: 0.8rem;">
        <div>
          <div style="font-size: 0.66rem; color: var(--text-muted);">SYNERGY</div>
          <strong style="color: var(--cyan-bright); font-size: 1rem;">${s.synergy_score}</strong>
        </div>
        <div>
          <div style="font-size: 0.66rem; color: var(--text-muted);">WIN RATE</div>
          <strong style="color: var(--win-green);">${s.win_rate}%</strong>
        </div>
        <div>
          <div style="font-size: 0.66rem; color: var(--text-muted);">DUO KDA</div>
          <strong style="color: var(--gold-bright);">${s.combined_kda}</strong>
        </div>
        <div>
          <div style="font-size: 0.66rem; color: var(--text-muted);">RECORD</div>
          <strong>${s.wins}W-${s.losses}L</strong>
        </div>
      </div>
    </div>
  `).join('');

  const tbody = document.getElementById('synergies-table-body');
  tbody.innerHTML = rows.map(s => `
    <tr>
      <td><span style="font-size: 0.78rem; color: var(--gold-primary); font-weight: 600;">${escapeHtml(s.categoryLabel)}</span></td>
      <td><strong>${escapeHtml(s.pair)}</strong></td>
      <td>
        <span class="badge ${s.tier === 'S Tier' ? 'badge-ready' : 'badge-polling'}">${escapeHtml(s.tier)}</span>
        <span class="highlight-chip" style="margin-left: 0.3rem;">${escapeHtml(s.tag)}</span>
      </td>
      <td><strong style="color: var(--cyan-bright); font-size: 0.98rem;">${s.synergy_score}</strong></td>
      <td><strong style="color: ${s.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${s.win_rate}%</strong> (${s.wins}W-${s.losses}L)</td>
      <td><strong>${s.combined_kda}</strong></td>
      <td>${s.avg_duo_rating}</td>
      <td>${s.coordination_score}</td>
      <td>${s.games}</td>
      <td><span class="archetype-tag">${escapeHtml(s.favorite_combo)}</span></td>
    </tr>
  `).join('') || '<tr><td colspan="10" class="empty-state">No duo pairs match the current filter criteria.</td></tr>';
}

// --- TAB 5: SQUAD BUILDER ---
export { renderSquadBuilderTab };

// --- TAB 6: META & GAMEPLAY TRENDS ---
export function getFilteredChampionStats(data, filters, champSort) {
  const squadNames = getSquadPlayerNameSet(data);
  const filteredMatches = (data.matches || []).filter(m => matchPassesFilters(m, filters, squadNames));
  const map = {};

  filteredMatches.forEach(m => {
    const isWin = m.result === 'WIN';
    const dur = parseFloat(m.duration_min || 30);
    const lineup = m.lineup || {};
    Object.entries(lineup).forEach(([role, p]) => {
      if (!isSquadLineupEntry(p, squadNames)) return;
      if (filters.role !== 'ALL' && role !== filters.role) return;
      if (filters.player !== 'ALL' && p.player !== filters.player) return;
      if (filters.search) {
        const q = filters.search;
        const hay = `${p.champion} ${p.player} ${p.archetype} ${role}`.toLowerCase();
        if (!hay.includes(q)) return;
      }
      const c = p.champion || 'Unknown';
      const key = `${c}||${role}`;
      if (!map[key]) {
        map[key] = {
          champion: c,
          role,
          archetype: p.archetype || 'bruiser',
          picks: 0, wins: 0, losses: 0,
          kills: 0, deaths: 0, assists: 0,
          damage: 0, cs: 0, dur: 0, ratingSum: 0,
          pilots: {}
        };
      }
      const entry = map[key];
      entry.picks += 1;
      if (isWin) entry.wins += 1; else entry.losses += 1;
      entry.kills += (p.kills || 0);
      entry.deaths += (p.deaths || 0);
      entry.assists += (p.assists || 0);
      entry.damage += (p.damage || 0);
      entry.cs += (p.cs || 0);
      entry.dur += dur;
      entry.ratingSum += parseFloat(p.rating || 65);
      entry.pilots[p.player] = (entry.pilots[p.player] || 0) + 1;
    });
  });

  const list = Object.values(map).map(e => {
    const g = e.picks;
    const avgR = +(e.ratingSum / g).toFixed(1);
    const topPilot = Object.keys(e.pilots).sort((a, b) => e.pilots[b] - e.pilots[a])[0] || 'N/A';
    return {
      champion: e.champion,
      role: e.role,
      archetype: e.archetype,
      primary_role: e.role,
      picks: g,
      wins: e.wins,
      losses: e.losses,
      win_rate: +((e.wins / g) * 100).toFixed(1),
      kda: +((e.kills + e.assists) / Math.max(1, e.deaths)).toFixed(2),
      dpm: Math.round(e.damage / Math.max(1, e.dur)),
      cspm: +(e.cs / Math.max(1, e.dur)).toFixed(1),
      avg_rating: avgR,
      top_pilot: topPilot
    };
  }).filter(c => c.picks >= filters.minGames);

  list.sort((a, b) => {
    const k = champSort.key;
    const va = a[k];
    const vb = b[k];
    if (typeof va === 'string') return champSort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
    return champSort.asc ? (va - vb) : (vb - va);
  });

  return { list, filteredMatches };
}

export function renderTrendsTab(data, filters, champSort, currentTab) {
  const { list, filteredMatches } = getFilteredChampionStats(data, filters, champSort);

  // Meta Insights Banner
  const trendsInsightsEl = document.getElementById('trends-insights-grid');
  if (trendsInsightsEl) {
    const metaInsights = computeExecutiveInsights(data, filteredMatches).slice(0, 3);
    trendsInsightsEl.innerHTML = renderInsightsHtml(metaInsights);
  }

  const tbody = document.getElementById('champions-table-body');
  tbody.innerHTML = list.map(c => `
    <tr>
      <td><strong style="color: var(--gold-bright);">${escapeHtml(c.champion)}</strong></td>
      <td><span class="archetype-tag">${escapeHtml(c.archetype)}</span></td>
      <td><span class="role-badge">${escapeHtml(c.role || c.primary_role)}</span></td>
      <td><strong>${c.picks}</strong> (${c.wins}W-${c.losses}L)</td>
      <td><strong style="color: ${c.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${c.win_rate}%</strong></td>
      <td><strong style="color: var(--cyan-bright);">${c.kda}</strong></td>
      <td>${c.dpm.toLocaleString()}</td>
      <td>${c.cspm}</td>
      <td><strong style="color: var(--gold-bright);">${c.avg_rating}</strong></td>
      <td>${escapeHtml(c.top_pilot)}</td>
    </tr>
  `).join('') || '<tr><td colspan="10" class="empty-state">No champion data matches the current filters.</td></tr>';

  if (currentTab === 'trends') {
    renderTrendsCharts(list, filteredMatches);
  }
}

// --- TAB 7: FAQ SIMULATOR & GITHUB FEEDBACK BUILDER ---
export function updateWeightSimulator(rawBundle) {
  const roleEl = document.getElementById('sim-role');
  const archEl = document.getElementById('sim-arch');
  const outEl = document.getElementById('sim-weights-output');
  if (!roleEl || !archEl || !outEl) return;

  const role = roleEl.value;
  const arch = archEl.value;
  const formulas = rawBundle?.rating_formulas || {};
  const rw = (formulas.role_weights || {})[role] || {};
  const aw = (formulas.archetype_weights || {})[arch] || {};
  const dpm = (formulas.dpm_benchmarks || {})[arch] || 600;
  const cspm = (formulas.cspm_benchmarks || {})[role] || 6.5;
  const vspm = (formulas.vspm_benchmarks || {})[role] || 0.85;

  const bars = PILLAR_DEFINITIONS.map(([k, label]) => {
    const rVal = rw[k] || 0;
    const aVal = aw[k] || 0;
    const blended = ((rVal * 0.55 + aVal * 0.45) * 100).toFixed(1);
    return `
      <div class="pillar-row">
        <span style="color: var(--gold-bright); font-weight: 600;">${label}</span>
        <div class="progress-bar" style="height: 10px;">
          <div class="progress-fill" style="width: ${Math.min(100, parseFloat(blended) * 2.2)}%;"></div>
        </div>
        <strong style="text-align: right; color: var(--cyan-bright);">${blended}%</strong>
      </div>
    `;
  }).join('');

  outEl.innerHTML = `
    <div style="margin-bottom: 0.65rem; font-size: 0.82rem; color: var(--text-muted);">
      Target Benchmarks for <strong style="color: var(--gold-bright);">${escapeHtml(role)} + ${escapeHtml(arch.toUpperCase())}</strong>:
      DPM Target: <code>${dpm}/min</code> • CS Target: <code>${cspm}/min</code> • Vision Target: <code>${vspm}/min</code>
    </div>
    ${bars}
  `;
}

export function updateFeedbackPreview(rawBundle) {
  const catEl = document.getElementById('fb-category');
  const titleEl = document.getElementById('fb-title');
  const repEl = document.getElementById('fb-reporter');
  const descEl = document.getElementById('fb-desc');
  if (!catEl || !titleEl || !repEl || !descEl) return;

  const repo = rawBundle?.github_repo || 'jgdclima/5-stacker-lol';
  const cat = catEl.value;
  const rawTitle = titleEl.value.trim() || 'Dashboard / Bot Suggestion';
  const reporter = repEl.value.trim() || 'Web Dashboard User';
  const desc = descEl.value.trim() || 'Describe your feedback or issue here...';

  const catMeta = {
    bug: { prefix: '[Bug]', display: 'Bug Report', label: 'bug' },
    feature: { prefix: '[Feature]', display: 'Feature Request', label: 'enhancement' },
    ux: { prefix: '[UX]', display: 'UX / Channel Feedback', label: 'enhancement' }
  }[cat] || { prefix: '[Feature]', display: 'Feature Request', label: 'enhancement' };

  const fullTitle = rawTitle.toLowerCase().startsWith(catMeta.prefix.toLowerCase())
    ? rawTitle
    : `${catMeta.prefix} ${rawTitle}`;

  const body = [
    `### ${catMeta.display}`,
    ``,
    desc,
    ``,
    `---`,
    `#### Metadata`,
    `- **Submitted by**: \`${reporter}\``,
    `- **Category**: ${catMeta.display}`,
    `- **Source**: 5-Stack Coordinator Interactive Web Dashboard`
  ].join('\n');

  document.getElementById('fb-markdown-preview').textContent = `Title: ${fullTitle}\nLabel: ${catMeta.label}\n\n${body}`;

  const issueUrl = `https://github.com/${repo}/issues/new?title=${encodeURIComponent(fullTitle)}&body=${encodeURIComponent(body)}&labels=${encodeURIComponent(catMeta.label)}`;
  document.getElementById('fb-submit-link').href = issueUrl;
  document.getElementById('fb-view-issues-link').href = `https://github.com/${repo}/issues`;
  document.getElementById('faq-repo-link').href = `https://github.com/${repo}/issues`;
}
