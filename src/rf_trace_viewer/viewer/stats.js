/* RF Trace Viewer — Statistics Panel Renderer */

/**
 * Render the statistics panel into the given container.
 * @param {HTMLElement} container
 * @param {Object} statistics - RunStatistics from RFRunModel
 */
function renderStats(container, statistics) {
  console.log('renderStats called with container:', container, 'statistics:', statistics);
  container.innerHTML = '';

  var total = statistics.total_tests || 0;
  var passed = statistics.passed || 0;
  var failed = statistics.failed || 0;
  var skipped = statistics.skipped || 0;
  var durationMs = statistics.total_duration_ms || 0;
  var suiteStats = statistics.suite_stats || [];

  // Overall status indicator
  var overallEl = document.createElement('div');
  overallEl.className = 'stats-overall ' + (failed > 0 ? 'status-fail' : 'status-pass');
  overallEl.textContent = failed > 0 ? '\u2717 FAIL' : '\u2713 ALL PASS';
  container.appendChild(overallEl);

  // Summary cards
  var summaryEl = document.createElement('div');
  summaryEl.className = 'stats-summary';
  summaryEl.appendChild(_statCard('Total', total, ''));
  summaryEl.appendChild(_statCard(pct(passed, total) + ' Pass', passed, 'pass'));
  summaryEl.appendChild(_statCard(pct(failed, total) + ' Fail', failed, 'fail'));
  summaryEl.appendChild(_statCard(pct(skipped, total) + ' Skip', skipped, 'skip'));
  container.appendChild(summaryEl);

  // Duration
  var durEl = document.createElement('div');
  durEl.className = 'stats-duration';
  durEl.innerHTML = 'Duration: <strong>' + formatDuration(durationMs) + '</strong>';
  container.appendChild(durEl);

  // Per-suite breakdown
  if (suiteStats.length > 0) {
    var breakdownEl = document.createElement('div');
    breakdownEl.className = 'suite-breakdown';
    var heading = document.createElement('h3');
    heading.textContent = 'Per-Suite Breakdown';
    breakdownEl.appendChild(heading);

    for (var i = 0; i < suiteStats.length; i++) {
      breakdownEl.appendChild(_suiteStatRow(suiteStats[i]));
    }
    container.appendChild(breakdownEl);
  }
}

/** Create a stat card element. */
function _statCard(label, value, cls) {
  var card = document.createElement('div');
  card.className = 'stat-card' + (cls ? ' ' + cls : '');
  var valSpan = document.createElement('span');
  valSpan.className = 'stat-value';
  valSpan.textContent = String(value);
  var lblSpan = document.createElement('span');
  lblSpan.className = 'stat-label';
  lblSpan.textContent = label;
  card.appendChild(valSpan);
  card.appendChild(lblSpan);
  return card;
}

/** Create a per-suite stat row. */
function _suiteStatRow(suite) {
  var row = document.createElement('div');
  row.className = 'suite-stat-row';

  var nameEl = document.createElement('span');
  nameEl.className = 'suite-stat-name';
  nameEl.textContent = suite.suite_name;
  nameEl.title = suite.suite_name;

  var countsEl = document.createElement('span');
  countsEl.className = 'suite-stat-counts';
  countsEl.innerHTML =
    '<span class="pass">\u2713' + suite.passed + '</span>' +
    '<span class="fail">\u2717' + suite.failed + '</span>' +
    '<span class="skip">\u2298' + suite.skipped + '</span>';

  row.appendChild(nameEl);
  row.appendChild(countsEl);
  return row;
}

/** Format percentage string. */
function pct(n, total) {
  if (total === 0) return '0%';
  return Math.round((n / total) * 100) + '%';
}

/** Format duration from milliseconds to human-readable string. */
function formatDuration(ms) {
  if (ms < 1000) return ms.toFixed(0) + 'ms';
  var secs = ms / 1000;
  if (secs < 60) return secs.toFixed(1) + 's';
  var mins = Math.floor(secs / 60);
  var remSecs = (secs % 60).toFixed(0);
  if (mins < 60) return mins + 'm ' + remSecs + 's';
  var hrs = Math.floor(mins / 60);
  var remMins = mins % 60;
  return hrs + 'h ' + remMins + 'm ' + remSecs + 's';
}
