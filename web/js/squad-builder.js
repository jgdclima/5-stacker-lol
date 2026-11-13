/**
 * 5-Stack Lineup & Role Optimizer ("Squad Builder").
 * Evaluates all 5! = 120 role permutations across 5 selected squad members,
 * optimizing individual role proficiency + all 4 pairwise duo synergy channels.
 */

import {
  buildRoleMatchIndex,
  escapeHtml,
  getSquadPlayerNameSet,
  gradeClass,
  resolvePlayerRoles,
  ROLES_ORDER
} from './utils.js';

const SYNERGY_CHANNELS = [
  { key: 'botlane', roleA: 'Bot', roleB: 'Support', label: '🏹🛡️ Bot + Support' },
  { key: 'mid_jungle', roleA: 'Mid', roleB: 'Jungle', label: '🔮🌲 Mid + Jungle' },
  { key: 'top_jungle', roleA: 'Top', roleB: 'Jungle', label: '⚔️🌲 Top + Jungle' },
  { key: 'support_jungle', roleA: 'Support', roleB: 'Jungle', label: '🛡️🌲 Support + Jungle' }
];

let selectedPlayerNames = [];
let lastDatasetGroupSignature = '';

function clamp(val, min, max) {
  return Math.max(min, Math.min(max, val));
}

function getPermutations(arr) {
  if (arr.length <= 1) return [arr];
  const result = [];
  for (let i = 0; i < arr.length; i++) {
    const rest = arr.slice(0, i).concat(arr.slice(i + 1));
    for (const perm of getPermutations(rest)) {
      result.push([arr[i], ...perm]);
    }
  }
  return result;
}

function scorePlayerRoleFit(player, role, roleIndex) {
  const baseRating = player.games > 0 ? parseFloat(player.avg_rating || 65) : 62.0;
  const rStat = roleIndex[player.name]?.[role];
  const rGames = rStat ? rStat.games : 0;

  let perfScore = baseRating;
  if (rGames > 0) {
    const rAvg = rStat.ratingSum / rGames;
    const w = Math.min(1.0, rGames / 3);
    perfScore = w * rAvg + (1 - w) * baseRating;
  }

  const { primary_role, secondary_role } = resolvePlayerRoles(player, roleIndex[player.name]);

  let bonus = 0;
  let fitLabel = 'Proven Off-Role';
  let fitClass = 'badge-completed';

  if (primary_role === role) {
    bonus = 8.5;
    fitLabel = 'Primary Main';
    fitClass = 'badge-win';
  } else if (secondary_role === role) {
    bonus = 3.5;
    fitLabel = 'Secondary Flex';
    fitClass = 'badge-progress';
  } else if (rGames === 0) {
    bonus = -6.0;
    fitLabel = 'Off-Role Fill';
    fitClass = 'badge-polling';
  }

  const proficiency = +clamp(perfScore + bonus, 20.0, 99.5).toFixed(1);

  let recommendedChamp = 'Flex Pick';
  if (rStat && Object.keys(rStat.champs).length > 0) {
    recommendedChamp = Object.entries(rStat.champs)
      .sort((a, b) => (b[1].games - a[1].games) || (b[1].ratingSum / b[1].games - a[1].ratingSum / a[1].games))[0][0];
  } else if (player.champion_pool && player.champion_pool.length > 0) {
    const matchingRoleChamp = player.champion_pool.find(c => c.primary_role === role);
    recommendedChamp = (matchingRoleChamp || player.champion_pool[0]).champion;
  } else if (player.fav_champs && player.fav_champs.length > 0) {
    recommendedChamp = player.fav_champs[0];
  }

  return {
    playerName: player.name,
    role,
    proficiency,
    roleGames: rGames,
    roleWr: rGames > 0 ? +((rStat.wins / rGames) * 100).toFixed(0) : null,
    fitLabel,
    fitClass,
    recommendedChamp,
    overallGrade: player.grade || 'N/A'
  };
}

export function evaluateOptimalLineups(chosenPlayers, data, roleIndexOpt = null) {
  if (!chosenPlayers || chosenPlayers.length !== 5) return [];

  const roleIndex = roleIndexOpt || buildRoleMatchIndex(data.matches || [], getSquadPlayerNameSet(data));
  const synLookup = {};
  SYNERGY_CHANNELS.forEach(ch => {
    synLookup[ch.key] = {};
    (data.synergies?.[ch.key] || []).forEach(s => {
      synLookup[ch.key][`${s.player_a}||${s.player_b}`] = s;
    });
  });

  // Precompute player x role table for speed
  const fitCache = {};
  chosenPlayers.forEach(p => {
    fitCache[p.name] = {};
    ROLES_ORDER.forEach(r => {
      fitCache[p.name][r] = scorePlayerRoleFit(p, r, roleIndex);
    });
  });

  const perms = getPermutations(chosenPlayers);
  const scored = perms.map(perm => {
    const assignment = {};
    let roleSum = 0;
    let primaryHits = 0;

    ROLES_ORDER.forEach((role, idx) => {
      const p = perm[idx];
      const fit = fitCache[p.name][role];
      assignment[role] = fit;
      roleSum += fit.proficiency;
      if (fit.fitLabel === 'Primary Main') primaryHits += 1;
    });

    const avgRoleScore = roleSum / 5;

    let synSum = 0;
    let historicalPairs = 0;
    const duoBreakdown = SYNERGY_CHANNELS.map(ch => {
      const aFit = assignment[ch.roleA];
      const bFit = assignment[ch.roleB];
      const key = `${aFit.playerName}||${bFit.playerName}`;
      const record = synLookup[ch.key][key];

      if (record) {
        historicalPairs += 1;
        synSum += record.synergy_score;
        return {
          label: ch.label,
          playerA: aFit.playerName,
          playerB: bFit.playerName,
          score: record.synergy_score,
          games: record.games,
          winRate: record.win_rate,
          tier: record.tier,
          tag: record.tag,
          combo: record.favorite_combo,
          isEstimated: false
        };
      }

      const estScore = +clamp(((aFit.proficiency + bFit.proficiency) / 2) * 0.9, 45.0, 76.0).toFixed(1);
      synSum += estScore;
      return {
        label: ch.label,
        playerA: aFit.playerName,
        playerB: bFit.playerName,
        score: estScore,
        games: 0,
        winRate: null,
        tier: 'Est.',
        tag: 'Untested Pairing',
        combo: `${aFit.recommendedChamp} + ${bFit.recommendedChamp}`,
        isEstimated: true
      };
    });

    const avgSynergyScore = synSum / SYNERGY_CHANNELS.length;
    const totalScore = +(0.58 * avgRoleScore + 0.42 * avgSynergyScore).toFixed(1);
    const predictedWinProb = clamp(+(50 + (totalScore - 68) * 0.85).toFixed(1), 30.0, 84.0);

    return {
      assignment,
      duoBreakdown,
      avgRoleScore: +avgRoleScore.toFixed(1),
      avgSynergyScore: +avgSynergyScore.toFixed(1),
      totalScore,
      predictedWinProb,
      primaryHits,
      historicalPairs
    };
  });

  scored.sort((a, b) =>
    (b.totalScore - a.totalScore) ||
    (b.primaryHits - a.primaryHits) ||
    (b.avgRoleScore - a.avgRoleScore)
  );

  return scored;
}

export function ensureBuilderSelectionSynced(data) {
  const players = data?.players || [];
  const sig = `${data?.is_demo ? 'demo' : 'live'}:${players.map(p => p.name).join(',')}`;
  if (sig === lastDatasetGroupSignature) return;
  lastDatasetGroupSignature = sig;

  // Auto-seed with active session starters or top 5 rated players for immediate interactivity
  const validSet = new Set(players.map(p => p.name));
  const activeSessions = (data?.sessions || []).filter(s => ['IN_PROGRESS', 'READY', 'POLLING'].includes(s.status));
  const firstStarters = activeSessions[0]?.confirmed_players?.map(p => p.name).filter(n => validSet.has(n)) || [];

  if (firstStarters.length === 5) {
    selectedPlayerNames = firstStarters;
  } else {
    selectedPlayerNames = players.slice(0, 5).map(p => p.name);
  }
}

export function toggleBuilderPlayer(playerName, data, onUpdate) {
  const idx = selectedPlayerNames.indexOf(playerName);
  if (idx >= 0) {
    selectedPlayerNames.splice(idx, 1);
  } else if (selectedPlayerNames.length < 5) {
    selectedPlayerNames.push(playerName);
  } else {
    // Replace oldest selection so users don't get stuck clicking a 6th player
    selectedPlayerNames.shift();
    selectedPlayerNames.push(playerName);
  }
  if (onUpdate) onUpdate();
}

export function selectBuilderPreset(preset, data, onUpdate) {
  const players = data?.players || [];
  if (preset === 'clear') {
    selectedPlayerNames = [];
  } else if (preset === 'top5') {
    selectedPlayerNames = [...players]
      .sort((a, b) => (b.avg_rating - a.avg_rating) || (b.win_rate - a.win_rate))
      .slice(0, 5)
      .map(p => p.name);
  } else if (preset === 'session') {
    const validSet = new Set(players.map(p => p.name));
    const sess = (data?.sessions || []).find(s => (s.confirmed_players || []).length >= 5) || (data?.sessions || [])[0];
    if (sess) {
      const fromSess = (sess.confirmed_players || []).map(p => p.name).filter(n => validSet.has(n));
      const bench = (sess.bench_substitutes || []).map(p => p.name).filter(n => validSet.has(n) && !fromSess.includes(n));
      selectedPlayerNames = [...fromSess, ...bench].slice(0, 5);
    }
  }
  if (onUpdate) onUpdate();
}

export function renderSquadBuilderTab(data) {
  ensureBuilderSelectionSynced(data);
  const players = data?.players || [];
  const container = document.getElementById('squad-builder-root');
  if (!container) return;

  if (players.length < 5) {
    container.innerHTML = `
      <div class="hex-card empty-state">
        <h3 style="color: var(--gold-bright); margin-bottom: 0.5rem;">Need at Least 5 Roster Members for Combinatorial Optimization</h3>
        <p style="margin-bottom: 1rem;">Currently ${players.length} squad player(s) in this dataset. Link more members via <code>/link-riot</code> or switch to <strong>Demo Preview</strong> to test the 120-permutation 5-Stack Optimizer.</p>
        <button class="mode-btn active" onclick="setDatasetMode('demo')">Explore Demo Preview</button>
      </div>
    `;
    return;
  }

  const roleIndex = buildRoleMatchIndex(data?.matches || [], getSquadPlayerNameSet(data));
  const chosenPlayers = players.filter(p => selectedPlayerNames.includes(p.name));
  const playerButtonsHtml = players.map(p => {
    const isSelected = selectedPlayerNames.includes(p.name);
    const { primary_role, secondary_role } = resolvePlayerRoles(p, roleIndex[p.name]);
    return `
      <button class="builder-player-btn ${isSelected ? 'selected' : ''}" onclick="toggleBuilderPlayer('${escapeHtml(p.name)}')">
        <div>
          <div style="font-weight: 700; color: var(--gold-bright);">${isSelected ? '✅ ' : ''}${escapeHtml(p.name)}</div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">${escapeHtml(primary_role)} / ${escapeHtml(secondary_role)}</div>
        </div>
        <div style="text-align: right;">
          <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
          <div style="font-size: 0.68rem; color: var(--cyan-bright); margin-top: 2px;">${p.avg_rating}</div>
        </div>
      </button>
    `;
  }).join('');

  let resultsHtml = '';
  if (chosenPlayers.length < 5) {
    resultsHtml = `
      <div class="hex-card empty-state">
        Select <strong>${5 - chosenPlayers.length} more player(s)</strong> above to evaluate all <code>5! = 120</code> role assignments and 4-duo synergy combinations.
      </div>
    `;
  } else {
    const ranked = evaluateOptimalLineups(chosenPlayers, data, roleIndex);
    const best = ranked[0];
    const runnersUp = ranked.slice(1, 4);

    const laneCardsHtml = ROLES_ORDER.map(role => {
      const slot = best.assignment[role];
      return `
        <div class="lane-card">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="role-badge">${escapeHtml(role)}</span>
            <span class="badge ${slot.fitClass}">${escapeHtml(slot.fitLabel)}</span>
          </div>
          <div style="font-size: 1.08rem; font-weight: 800; color: var(--gold-bright); margin-top: 0.25rem; cursor: pointer;" onclick="openPlayerModal('${escapeHtml(slot.playerName)}')">
            ${escapeHtml(slot.playerName)}
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">
            Role Fit Score: <strong style="color: var(--cyan-bright);">${slot.proficiency}</strong>
            ${slot.roleGames > 0 ? ` • ${slot.roleGames}G (${slot.roleWr}% WR)` : ' • Unplayed in role'}
          </div>
          <div style="font-size: 0.76rem; color: var(--gold-primary); margin-top: auto; padding-top: 0.35rem; border-top: 1px solid var(--border-subtle);">
            Rec. Pick: <strong>${escapeHtml(slot.recommendedChamp)}</strong>
          </div>
        </div>
      `;
    }).join('');

    const duoCardsHtml = best.duoBreakdown.map(d => `
      <div class="duo-chem-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
          <span style="font-size: 0.73rem; font-weight: 700; color: var(--gold-primary);">${escapeHtml(d.label)}</span>
          <span class="badge ${d.isEstimated ? 'badge-completed' : (d.tier === 'S Tier' ? 'badge-ready' : 'badge-polling')}">
            ${d.isEstimated ? 'Estimated' : escapeHtml(d.tier)}
          </span>
        </div>
        <div style="font-weight: 700; color: var(--text-main); font-size: 0.9rem;">
          ${escapeHtml(d.playerA)} &amp; ${escapeHtml(d.playerB)}
        </div>
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 0.35rem;">
          <strong style="font-size: 1.15rem; color: var(--cyan-bright);">${d.score}</strong>
          <span style="font-size: 0.74rem; color: var(--text-muted);">
            ${d.isEstimated ? 'No shared history' : `${d.games}G • ${d.winRate}% WR`}
          </span>
        </div>
      </div>
    `).join('');

    const runnerRowsHtml = runnersUp.map((r, i) => {
      const delta = (r.totalScore - best.totalScore).toFixed(1);
      const lineStr = ROLES_ORDER.map(role => `<strong>${role}:</strong> ${escapeHtml(r.assignment[role].playerName)}`).join(' &nbsp;|&nbsp; ');
      return `
        <tr>
          <td><strong>#${i + 2}</strong></td>
          <td style="font-size: 0.8rem;">${lineStr}</td>
          <td><strong style="color: var(--gold-bright);">${r.totalScore}</strong> <span style="color: var(--loss-red); font-size: 0.75rem;">(${delta})</span></td>
          <td>${r.avgRoleScore}</td>
          <td>${r.avgSynergyScore}</td>
          <td>${r.primaryHits}/5 Main Roles</td>
        </tr>
      `;
    }).join('');

    resultsHtml = `
      <div class="hex-card" style="border-color: var(--border-gold); margin-bottom: 1.35rem;">
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.8rem;">
          <div>
            <span class="badge badge-ready">🏆 Optimal #1 Permutation (of 120 Evaluated)</span>
            <h3 style="color: var(--gold-bright); font-size: 1.25rem; margin-top: 0.35rem;">
              Recommended 5-Stack Role Assignment
            </h3>
            <p style="font-size: 0.82rem; color: var(--text-muted);">
              Maximizes <code>58% Role Proficiency</code> + <code>42% 4-Pair Map Synergy</code> (${best.primaryHits}/5 on primary role, ${best.historicalPairs}/4 proven duo histories).
            </p>
          </div>
          <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            <div style="background: rgba(6,13,24,0.8); border: 1px solid var(--border-gold); border-radius: 10px; padding: 0.65rem 1rem; text-align: center;">
              <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Composite Score</div>
              <div style="font-size: 1.45rem; font-weight: 800; color: var(--gold-bright);">${best.totalScore}</div>
            </div>
            <div style="background: rgba(6,13,24,0.8); border: 1px solid rgba(10,200,185,0.45); border-radius: 10px; padding: 0.65rem 1rem; text-align: center;">
              <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Projected Win Prob</div>
              <div style="font-size: 1.45rem; font-weight: 800; color: var(--cyan-bright);">${best.predictedWinProb}%</div>
            </div>
          </div>
        </div>

        <div class="builder-lanes-grid">
          ${laneCardsHtml}
        </div>

        <div class="filter-label" style="margin: 1rem 0 0.55rem 0;">Predicted 4-Quadrant Duo Chemistry</div>
        <div class="duo-chem-grid">
          ${duoCardsHtml}
        </div>
      </div>

      <div class="section-header">
        <div class="section-title">🔄 Alternative Lineup Permutations (#2 – #4 Trade-Offs)</div>
      </div>
      <div class="table-wrap">
        <table class="hex-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>5-Role Assignment</th>
              <th>Composite Score</th>
              <th>Role Fit Avg</th>
              <th>4-Duo Synergy Avg</th>
              <th>Primary Role Hits</th>
            </tr>
          </thead>
          <tbody>${runnerRowsHtml}</tbody>
        </table>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="hex-card" style="margin-bottom: 1.35rem;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.8rem; margin-bottom: 0.9rem;">
        <div>
          <div class="section-title" style="margin: 0;">🧠 5-Stack Lineup &amp; Role Optimizer</div>
          <p style="font-size: 0.84rem; color: var(--text-muted); margin-top: 0.25rem;">
            Pick any <strong>5 available squad members</strong> (${selectedPlayerNames.length}/5 selected) to solve all <code>5! = 120</code> lane permutations across individual role performance and 4-pair map synergy.
          </p>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
          <button class="role-pill active" onclick="selectBuilderPreset('top5')">🏆 Top 5 by Rating</button>
          <button class="role-pill active" onclick="selectBuilderPreset('session')">📅 Load Session Starters</button>
          <button class="reset-btn" onclick="selectBuilderPreset('clear')">Clear (${selectedPlayerNames.length}/5)</button>
        </div>
      </div>
      <div class="builder-roster-grid">
        ${playerButtonsHtml}
      </div>
    </div>
    ${resultsHtml}
  `;
}
