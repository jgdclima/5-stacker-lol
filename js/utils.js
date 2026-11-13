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
