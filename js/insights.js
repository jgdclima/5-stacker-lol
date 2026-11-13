/**
 * Automated Executive Insights & Statistical Benchmark Engine.
 * Computes data-driven callouts from squad roster, match telemetry, and 4-pair synergies.
 */

import { PILLAR_DEFINITIONS, ROLES_ORDER } from './utils.js';

export function computeSquadRoleBenchmark(players) {
  const active = (players || []).filter(p => (p.games || 0) > 0 && p.pillars_avg);
  const benchmark = {};
  for (const [key] of PILLAR_DEFINITIONS) {
    if (active.length === 0) {
      benchmark[key] = 50.0;
    } else {
      const sum = active.reduce((acc, p) => acc + (parseFloat(p.pillars_avg?.[key]) || 0), 0);
      benchmark[key] = +(sum / active.length).toFixed(1);
    }
  }
  return benchmark;
}

export function computeExecutiveInsights(data, filteredMatchesOpt = null) {
  const players = data?.players || [];
  const matches = filteredMatchesOpt || data?.matches || [];
  const insights = [];

  // 1. Role Scarcity & On-Role Performance Lift
  if (players.length > 0) {
    const primaryCounts = Object.fromEntries(ROLES_ORDER.map(r => [r, 0]));
    const flexCounts = Object.fromEntries(ROLES_ORDER.map(r => [r, 0]));
    players.forEach(p => {
      if (primaryCounts[p.primary_role] !== undefined) primaryCounts[p.primary_role] += 1;
      if (flexCounts[p.secondary_role] !== undefined) flexCounts[p.secondary_role] += 1;
    });

    const sortedByScarcity = [...ROLES_ORDER].sort(
      (a, b) => (primaryCounts[a] - primaryCounts[b]) || (flexCounts[a] - flexCounts[b])
    );
    const scarcestRole = sortedByScarcity[0];
    const richestRole = sortedByScarcity[sortedByScarcity.length - 1];

    // Check on-role vs off-role performance across matches
    const playerMap = Object.fromEntries(players.map(p => [p.name, p]));
    let onRoleRatings = [];
    let offRoleRatings = [];
    matches.forEach(m => {
      Object.entries(m.lineup || {}).forEach(([role, pdata]) => {
        if (!pdata || pdata.rating == null) return;
        const prof = playerMap[pdata.player];
        if (!prof) return;
        if (prof.primary_role === role) {
          onRoleRatings.push(parseFloat(pdata.rating));
        } else if (prof.primary_role && prof.primary_role !== 'Flex') {
          offRoleRatings.push(parseFloat(pdata.rating));
        }
      });
    });

    let liftCopy = `${players.length} roster members tracked; ${richestRole} has ${primaryCounts[richestRole]} primary mains while ${scarcestRole} has ${primaryCounts[scarcestRole]} primary (+${flexCounts[scarcestRole]} secondary flex).`;
    if (onRoleRatings.length > 0 && offRoleRatings.length > 0) {
      const onAvg = onRoleRatings.reduce((a, b) => a + b, 0) / onRoleRatings.length;
      const offAvg = offRoleRatings.reduce((a, b) => a + b, 0) / offRoleRatings.length;
      const delta = (onAvg - offAvg).toFixed(1);
      const sign = parseFloat(delta) >= 0 ? '+' : '';
      liftCopy += ` Playing primary role averages ${onAvg.toFixed(1)} rating (${sign}${delta} vs off-role).`;
    }

    insights.push({
      id: 'role-scarcity',
      category: 'Roster & Role Coverage',
      metric: `${scarcestRole}: ${primaryCounts[scarcestRole]} Main${primaryCounts[scarcestRole] === 1 ? '' : 's'}`,
      title: primaryCounts[scarcestRole] <= 1
        ? `Role Bottleneck Detected in ${scarcestRole}`
        : `Balanced 5-Role Roster Depth`,
      summary: liftCopy,
      tone: primaryCounts[scarcestRole] <= 1 ? 'warn' : 'gold'
    });
  } else {
    insights.push({
      id: 'role-scarcity-empty',
      category: 'Roster & Role Coverage',
      metric: '0 Members',
      title: 'Awaiting @LOLers Roster Sync',
      summary: 'Link Riot IDs via /link-riot or switch to Demo Preview to inspect role coverage bottlenecks.',
      tone: 'gold'
    });
  }

  // 2. Kit Archetype Marginal Win-Rate Lift
  if (matches.length > 0) {
    const totalWins = matches.filter(m => m.result === 'WIN').length;
    const baselineWr = (totalWins / matches.length) * 100;
    const archMap = {};

    matches.forEach(m => {
      const isWin = m.result === 'WIN';
      Object.values(m.lineup || {}).forEach(p => {
        if (!p || !p.archetype) return;
        const arch = p.archetype;
        if (!archMap[arch]) {
          archMap[arch] = { archetype: arch, picks: 0, wins: 0, ratingSum: 0 };
        }
        archMap[arch].picks += 1;
        if (isWin) archMap[arch].wins += 1;
        archMap[arch].ratingSum += parseFloat(p.rating || 65);
      });
    });

    const candidates = Object.values(archMap)
      .map(a => ({
        ...a,
        wr: (a.wins / a.picks) * 100,
        avgRating: a.ratingSum / a.picks
      }))
      .filter(a => a.picks >= (matches.length >= 4 ? 2 : 1))
      .sort((a, b) => (b.wr - baselineWr) - (a.wr - baselineWr) || (b.avgRating - a.avgRating));

    const bestArch = candidates[0];
    if (bestArch) {
      const lift = bestArch.wr - baselineWr;
      const liftStr = `${lift >= 0 ? '+' : ''}${lift.toFixed(1)}% vs Squad WR`;
      const label = bestArch.archetype.charAt(0).toUpperCase() + bestArch.archetype.slice(1);
      insights.push({
        id: 'archetype-lift',
        category: 'Draft & Kit Meta',
        metric: liftStr,
        title: `${label} Picks Drive Highest Win Conversion`,
        summary: `${label} champions hold a ${bestArch.wr.toFixed(1)}% win rate (${bestArch.wins}W-${bestArch.picks - bestArch.wins}L across ${bestArch.picks} picks) with a ${bestArch.avgRating.toFixed(1)} avg holistic rating.`,
        tone: lift >= 0 ? 'green' : 'cyan'
      });
    }
  } else {
    insights.push({
      id: 'archetype-lift-empty',
      category: 'Draft & Kit Meta',
      metric: 'No Matches',
      title: 'Archetype Win-Rate Lift Pending',
      summary: 'Once squad games are logged, champion kit archetypes are benchmarked against squad baseline win rate.',
      tone: 'cyan'
    });
  }

  // 3. Top Map Partnership Anchor
  const synLabels = {
    botlane: 'Bot + Support',
    mid_jungle: 'Mid + Jungle',
    top_jungle: 'Top + Jungle',
    support_jungle: 'Support + Jungle'
  };
  const allSynergies = [];
  Object.entries(synLabels).forEach(([k, label]) => {
    (data?.synergies?.[k] || []).forEach(s => {
      allSynergies.push({ ...s, categoryLabel: label });
    });
  });

  if (allSynergies.length > 0) {
    allSynergies.sort((a, b) => (b.synergy_score - a.synergy_score) || (b.games - a.games));
    const top = allSynergies[0];
    insights.push({
      id: 'top-duo-anchor',
      category: 'Duo Chemistry Anchor',
      metric: `${top.synergy_score} Synergy (${top.tier})`,
      title: `${top.player_a} & ${top.player_b} Lead ${top.categoryLabel}`,
      summary: `Tagged "${top.tag}" with ${top.win_rate}% WR over ${top.games} game(s) (${top.combined_kda} duo KDA). Signature pairing: ${top.favorite_combo}.`,
      tone: 'cyan'
    });
  } else {
    insights.push({
      id: 'top-duo-empty',
      category: 'Duo Chemistry Anchor',
      metric: '0 Duos',
      title: 'Living Duo Chemistry Ready',
      summary: 'Play 2+ games with linked @LOLers members to populate the 4 Bayesian-dampened map partnership leaderboards.',
      tone: 'cyan'
    });
  }

  // 4. 6-Pillar Standout Outlier
  const activePlayers = players.filter(p => (p.games || 0) > 0 && p.pillars_avg);
  if (activePlayers.length > 0) {
    const benchmark = computeSquadRoleBenchmark(activePlayers);
    let bestOutlier = null;

    activePlayers.forEach(p => {
      PILLAR_DEFINITIONS.forEach(([pk, pLabel]) => {
        const val = parseFloat(p.pillars_avg?.[pk] || 0);
        const diff = val - (benchmark[pk] || 50);
        if (!bestOutlier || diff > bestOutlier.diff || (diff === bestOutlier.diff && val > bestOutlier.val)) {
          bestOutlier = { player: p, pillarKey: pk, pillarLabel: pLabel, val, avg: benchmark[pk], diff };
        }
      });
    });

    if (bestOutlier) {
      const cleanLabel = bestOutlier.pillarLabel.replace(/^[^\w]+/, '').trim();
      insights.push({
        id: 'pillar-outlier',
        category: '6-Pillar Statistical Outlier',
        metric: `+${bestOutlier.diff.toFixed(1)} vs Squad Avg`,
        title: `${bestOutlier.player.name} Dominates ${cleanLabel}`,
        summary: `Scores ${bestOutlier.val.toFixed(1)}/100 in ${cleanLabel} compared to the squad average of ${bestOutlier.avg.toFixed(1)}, anchoring their ${bestOutlier.player.grade} (${bestOutlier.player.avg_rating}) overall grade.`,
        tone: 'gold'
      });
    }
  } else {
    insights.push({
      id: 'pillar-outlier-empty',
      category: '6-Pillar Statistical Outlier',
      metric: '6 Pillars',
      title: 'Role-Normalized Performance Model',
      summary: 'Blends 55% assigned role weights with 45% champion kit archetype weights so tanks, enchanters, and splitpushers compete fairly for MVP.',
      tone: 'gold'
    });
  }

  return insights;
}
