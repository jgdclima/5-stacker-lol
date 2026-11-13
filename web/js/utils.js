/**
 * Shared formatting and escaping utilities for the 5-Stack Coordinator Dashboard.
 */

export function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function gradeClass(grade) {
  if (!grade || grade === 'N/A') return 'grade-NA';
  return 'grade-' + String(grade).replace('+', 'plus');
}

export function statusBadgeClass(status) {
  const s = String(status || '').toUpperCase();
  if (s === 'READY') return 'badge-ready';
  if (s === 'IN_PROGRESS') return 'badge-progress';
  if (s === 'POLLING') return 'badge-polling';
  if (s === 'CANCELLED') return 'badge-cancelled';
  return 'badge-completed';
}

export const PILLAR_DEFINITIONS = [
  ['combat', '⚔️ Combat & KDA'],
  ['damage', '🔥 Damage Output'],
  ['objective', '🐉 Objective Pressure'],
  ['frontline', '🛡️ Frontline & Tank'],
  ['utility', '✨ Utility & Peel'],
  ['macro_vision', '👁️ Vision & Economy']
];

export const ROLES_ORDER = ['Top', 'Jungle', 'Mid', 'Bot', 'Support'];

/**
 * Returns the lowercase set of verified @LOLers squad member names in a dataset.
 */
export function getSquadPlayerNameSet(data) {
  return new Set(
    (data?.players || [])
      .map(p => (p?.name || '').trim().toLowerCase())
      .filter(Boolean)
  );
}

/**
 * Returns true only if a match lineup participant belongs to the verified @LOLers squad.
 * Excludes random matchmade teammates (is_squad === false) and unlinked players.
 */
export function isSquadLineupEntry(pdata, squadNames = null) {
  if (!pdata || !pdata.player) return false;
  if (pdata.is_squad === false) return false;
  const nameLower = String(pdata.player).trim().toLowerCase();
  if (!nameLower) return false;
  if (squadNames && squadNames.size > 0) {
    return squadNames.has(nameLower);
  }
  return true;
}

/**
 * Aggregates per-player, per-role match volume, wins, ratings, and champion picks.
 */
export function buildRoleMatchIndex(matches, squadNames = null) {
  const index = {};
  (matches || []).forEach(m => {
    const isWin = m.result === 'WIN';
    Object.entries(m.lineup || {}).forEach(([role, pdata]) => {
      if (!isSquadLineupEntry(pdata, squadNames)) return;
      const pname = pdata.player;
      if (!index[pname]) index[pname] = {};
      if (!index[pname][role]) {
        index[pname][role] = { games: 0, wins: 0, ratingSum: 0, champs: {} };
      }
      const rEntry = index[pname][role];
      rEntry.games += 1;
      if (isWin) rEntry.wins += 1;
      rEntry.ratingSum += parseFloat(pdata.rating || 65);

      const champ = pdata.champion || 'Flex';
      if (!rEntry.champs[champ]) rEntry.champs[champ] = { games: 0, wins: 0, ratingSum: 0 };
      rEntry.champs[champ].games += 1;
      if (isWin) rEntry.champs[champ].wins += 1;
      rEntry.champs[champ].ratingSum += parseFloat(pdata.rating || 65);
    });
  });
  return index;
}

/**
 * Resolves a player's effective primary, secondary, and main roles, inferring
 * from match history / roles_played whenever stored roles are Flex/Fill/unset.
 */
export function resolvePlayerRoles(player, roleMatchStats = null) {
  const rolesPlayed = player?.roles_played || {};
  const ranked = ROLES_ORDER
    .map((role, idx) => {
      const mStat = roleMatchStats?.[role];
      const gamesFromMatches = mStat?.games || 0;
      const gamesFromProfile = Number(rolesPlayed[role] || 0);
      const games = Math.max(gamesFromMatches, gamesFromProfile);
      const winRate = gamesFromMatches > 0 ? (mStat.wins / gamesFromMatches) : -1;
      const avgRating = gamesFromMatches > 0 ? (mStat.ratingSum / gamesFromMatches) : -1;
      return { role, idx, games, winRate, avgRating };
    })
    .filter(r => r.games > 0)
    .sort((a, b) =>
      (b.games - a.games) ||
      (b.winRate - a.winRate) ||
      (b.avgRating - a.avgRating) ||
      (a.idx - b.idx)
    );

  const hasStandardPrimary = ROLES_ORDER.includes(player?.primary_role);
  const hasStandardMain = ROLES_ORDER.includes(player?.main_role);
  const primaryRole = hasStandardPrimary
    ? player.primary_role
    : (ranked[0]?.role || (hasStandardMain ? player.main_role : (player?.primary_role || 'Flex')));

  const hasValidSecondary = ROLES_ORDER.includes(player?.secondary_role) && player.secondary_role !== primaryRole;
  const altRole = ranked.find(r => r.role !== primaryRole)?.role;
  const secondaryRole = hasValidSecondary
    ? player.secondary_role
    : (altRole || (ROLES_ORDER.includes(primaryRole) ? 'Fill' : (player?.secondary_role || 'Flex')));

  const mainRole = hasStandardMain ? player.main_role : primaryRole;
  return { primary_role: primaryRole, secondary_role: secondaryRole, main_role: mainRole };
}
