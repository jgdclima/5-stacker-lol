/**
 * Chart.js Visualization Manager for Meta Trends & Player 6-Pillar Radar Comparisons.
 */

import { PILLAR_DEFINITIONS } from './utils.js';

let trendChartInstances = {};
let playerRadarInstance = null;

export function destroyTrendCharts() {
  Object.values(trendChartInstances).forEach(ch => ch && ch.destroy());
  trendChartInstances = {};
}

export function destroyPlayerRadarChart() {
  if (playerRadarInstance) {
    playerRadarInstance.destroy();
    playerRadarInstance = null;
  }
}

export function renderTrendsCharts(champList, filteredMatches) {
  if (typeof Chart === 'undefined') return;
  const list = champList || [];
  const matchesChrono = [...(filteredMatches || [])].reverse();

  destroyTrendCharts();

  const topPicked = [...list].sort((a, b) => (b.picks - a.picks) || (b.win_rate - a.win_rate)).slice(0, 8);
  const topRated = [...list].sort((a, b) => b.avg_rating - a.avg_rating).slice(0, 8);

  const formatChampLabel = c => {
    const r = c.role || c.primary_role;
    return r ? `${c.champion} (${r})` : c.champion;
  };

  // Chart 1: Most Picked Champions (Wins vs Losses stacked bar)
  const ctx1 = document.getElementById('chart-most-picked');
  if (ctx1) {
    trendChartInstances.c1 = new Chart(ctx1, {
      type: 'bar',
      data: {
        labels: topPicked.map(formatChampLabel),
        datasets: [
          { label: 'Wins', data: topPicked.map(c => c.wins), backgroundColor: 'rgba(46, 204, 113, 0.8)' },
          { label: 'Losses', data: topPicked.map(c => c.losses), backgroundColor: 'rgba(231, 76, 60, 0.8)' }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true, ticks: { color: '#e8e4dc' }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { stacked: true, ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.06)' } }
        },
        plugins: { legend: { labels: { color: '#e8e4dc' } } }
      }
    });
  }

  // Chart 2: Highest Holistic Rating by Champion
  const ctx2 = document.getElementById('chart-champ-ratings');
  if (ctx2) {
    trendChartInstances.c2 = new Chart(ctx2, {
      type: 'bar',
      data: {
        labels: topRated.map(formatChampLabel),
        datasets: [{
          label: 'Avg Holistic Rating (0-100)',
          data: topRated.map(c => c.avg_rating),
          backgroundColor: 'rgba(10, 200, 185, 0.75)',
          borderColor: '#0ac8b9',
          borderWidth: 1
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { min: 0, max: 100, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.06)' } },
          y: { ticks: { color: '#e8e4dc' }, grid: { display: false } }
        },
        plugins: { legend: { labels: { color: '#e8e4dc' } } }
      }
    });
  }

  // Chart 3: Kit Archetype Breakdown
  const archCounts = {};
  list.forEach(c => {
    archCounts[c.archetype] = (archCounts[c.archetype] || 0) + c.picks;
  });
  const archKeys = Object.keys(archCounts);
  const ctx3 = document.getElementById('chart-archetypes');
  if (ctx3) {
    trendChartInstances.c3 = new Chart(ctx3, {
      type: 'doughnut',
      data: {
        labels: archKeys.map(k => k.toUpperCase()),
        datasets: [{
          data: archKeys.map(k => archCounts[k]),
          backgroundColor: ['#c8aa6e', '#0ac8b9', '#3b82f6', '#2ecc71', '#9b59b6', '#f59e0b', '#ec4899', '#64748b'],
          borderColor: '#091428',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { color: '#e8e4dc', font: { size: 11 } } }
        }
      }
    });
  }

  // Chart 4: Cumulative Win Rate & Game Duration Trend
  let cumWins = 0;
  const cumWrData = [];
  const durData = [];
  const labels4 = [];
  matchesChrono.forEach((m, i) => {
    if (m.result === 'WIN') cumWins += 1;
    cumWrData.push(+((cumWins / (i + 1)) * 100).toFixed(1));
    durData.push(parseFloat(m.duration_min || 30));
    labels4.push(`G${i + 1}`);
  });

  const ctx4 = document.getElementById('chart-tempo-trend');
  if (ctx4) {
    trendChartInstances.c4 = new Chart(ctx4, {
      type: 'line',
      data: {
        labels: labels4,
        datasets: [
          {
            label: 'Cumulative Win Rate (%)',
            data: cumWrData,
            borderColor: '#c8aa6e',
            backgroundColor: 'rgba(200, 170, 110, 0.15)',
            fill: true,
            tension: 0.3
          },
          {
            label: 'Match Duration (min)',
            data: durData,
            borderColor: '#0ac8b9',
            borderDash: [5, 5],
            tension: 0.3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { min: 0, max: 100, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.06)' } }
        },
        plugins: { legend: { labels: { color: '#e8e4dc' } } }
      }
    });
  }
}

export function renderPlayerRadarChart(canvasId, player, comparePlayer, squadBenchmark) {
  if (typeof Chart === 'undefined') return;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  destroyPlayerRadarChart();

  const labels = PILLAR_DEFINITIONS.map(([, label]) => label.replace(/^[^\w]+/, '').trim());
  const keys = PILLAR_DEFINITIONS.map(([k]) => k);

  const playerValues = keys.map(k => parseFloat(player.pillars_avg?.[k] || 0));
  const baselineLabel = comparePlayer ? `${comparePlayer.name} (${comparePlayer.primary_role})` : 'Squad Average';
  const baselineValues = keys.map(k =>
    comparePlayer
      ? parseFloat(comparePlayer.pillars_avg?.[k] || 0)
      : parseFloat(squadBenchmark?.[k] || 50)
  );

  playerRadarInstance = new Chart(canvas, {
    type: 'radar',
    data: {
      labels,
      datasets: [
        {
          label: `${player.name} (${player.primary_role})`,
          data: playerValues,
          backgroundColor: 'rgba(200, 170, 110, 0.28)',
          borderColor: '#c8aa6e',
          pointBackgroundColor: '#f0e6d2',
          pointBorderColor: '#c8aa6e',
          borderWidth: 2
        },
        {
          label: baselineLabel,
          data: baselineValues,
          backgroundColor: 'rgba(10, 200, 185, 0.2)',
          borderColor: '#0ac8b9',
          pointBackgroundColor: '#0ac8b9',
          pointBorderColor: '#091428',
          borderWidth: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0,
          max: 100,
          ticks: {
            stepSize: 25,
            color: '#94a3b8',
            backdropColor: 'transparent',
            font: { size: 10 }
          },
          grid: { color: 'rgba(148, 163, 184, 0.2)' },
          angleLines: { color: 'rgba(148, 163, 184, 0.2)' },
          pointLabels: { color: '#f0e6d2', font: { size: 11, weight: '600' } }
        }
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#e8e4dc', font: { size: 11 } }
        }
      }
    }
  });
}
