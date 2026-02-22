/* RF Trace Viewer — Keyword Statistics View */

/**
 * Render keyword statistics view into the given container.
 * Aggregates all keywords by name, computes statistics, and displays
 * a sortable table. Clicking a keyword highlights it in tree and timeline.
 * 
 * @param {HTMLElement} container - The container element
 * @param {Object} model - RFRunModel with suites array
 */
function renderKeywordStats(container, model) {
  container.innerHTML = '';

  // Aggregate keywords from all suites
  var keywordStats = _aggregateKeywords(model.suites || []);

  if (keywordStats.length === 0) {
    container.innerHTML = '<p class="no-data">No keyword data available.</p>';
    return;
  }

  // Create header
  var header = document.createElement('div');
  header.className = 'keyword-stats-header';
  var title = document.createElement('h2');
  title.textContent = 'Keyword Statistics';
  header.appendChild(title);
  container.appendChild(header);

  // Create sortable table
  var tableContainer = document.createElement('div');
  tableContainer.className = 'keyword-stats-table-container';
  
  var table = document.createElement('table');
  table.className = 'keyword-stats-table';
  
  // Table header with sortable columns
  var thead = document.createElement('thead');
  var headerRow = document.createElement('tr');
  
  var columns = [
    { key: 'keyword', label: 'Keyword', sortable: true },
    { key: 'count', label: 'Count', sortable: true },
    { key: 'minDuration', label: 'Min (ms)', sortable: true },
    { key: 'maxDuration', label: 'Max (ms)', sortable: true },
    { key: 'avgDuration', label: 'Avg (ms)', sortable: true },
    { key: 'totalDuration', label: 'Total (ms)', sortable: true }
  ];
  
  var currentSort = { key: 'totalDuration', ascending: false };
  
  columns.forEach(function(col) {
    var th = document.createElement('th');
    th.textContent = col.label;
    if (col.sortable) {
      th.className = 'sortable';
      th.setAttribute('data-sort-key', col.key);
      th.style.cursor = 'pointer';
      th.addEventListener('click', function() {
        _sortTable(keywordStats, col.key, currentSort, tbody);
      });
    }
    headerRow.appendChild(th);
  });
  
  thead.appendChild(headerRow);
  table.appendChild(thead);
  
  // Table body
  var tbody = document.createElement('tbody');
  table.appendChild(tbody);
  
  // Initial sort by total duration (descending)
  _sortTable(keywordStats, 'totalDuration', currentSort, tbody);
  
  tableContainer.appendChild(table);
  container.appendChild(tableContainer);
}

/**
 * Aggregate keywords from the suite tree.
 * Returns array of keyword statistics objects.
 */
function _aggregateKeywords(suites) {
  var keywordMap = {}; // keyword name -> { count, durations[], spanIds[] }
  
  function collectKeywords(keywords) {
    keywords.forEach(function(kw) {
      var name = kw.name;
      if (!keywordMap[name]) {
        keywordMap[name] = {
          count: 0,
          durations: [],
          spanIds: []
        };
      }
      keywordMap[name].count++;
      keywordMap[name].durations.push(kw.elapsed_time);
      // Store identifier for highlighting (using name + start_time as unique ID)
      keywordMap[name].spanIds.push(kw.start_time);
      
      // Recursively collect nested keywords
      if (kw.children && kw.children.length > 0) {
        collectKeywords(kw.children);
      }
    });
  }
  
  function processTests(children) {
    children.forEach(function(child) {
      if (child.keywords !== undefined) {
        // It's a test
        collectKeywords(child.keywords);
      } else if (child.children !== undefined) {
        // It's a nested suite
        processTests(child.children);
      }
    });
  }
  
  suites.forEach(function(suite) {
    processTests(suite.children);
  });
  
  // Convert map to array with computed statistics
  var stats = [];
  for (var keyword in keywordMap) {
    if (keywordMap.hasOwnProperty(keyword)) {
      var data = keywordMap[keyword];
      var durations = data.durations;
      var minDuration = Math.min.apply(null, durations);
      var maxDuration = Math.max.apply(null, durations);
      var totalDuration = durations.reduce(function(sum, d) { return sum + d; }, 0);
      var avgDuration = totalDuration / data.count;
      
      stats.push({
        keyword: keyword,
        count: data.count,
        minDuration: minDuration,
        maxDuration: maxDuration,
        avgDuration: avgDuration,
        totalDuration: totalDuration,
        spanIds: data.spanIds
      });
    }
  }
  
  return stats;
}

/**
 * Sort the table by the given key and re-render tbody.
 */
function _sortTable(keywordStats, sortKey, currentSort, tbody) {
  // Toggle sort direction if clicking the same column
  var ascending = currentSort.key === sortKey ? !currentSort.ascending : false;
  currentSort.key = sortKey;
  currentSort.ascending = ascending;
  
  // Sort the data
  keywordStats.sort(function(a, b) {
    var valA = a[sortKey];
    var valB = b[sortKey];
    
    // String comparison for keyword name
    if (sortKey === 'keyword') {
      valA = valA.toLowerCase();
      valB = valB.toLowerCase();
      if (valA < valB) return ascending ? -1 : 1;
      if (valA > valB) return ascending ? 1 : -1;
      return 0;
    }
    
    // Numeric comparison for all other columns
    if (ascending) {
      return valA - valB;
    } else {
      return valB - valA;
    }
  });
  
  // Re-render tbody
  _renderTableBody(tbody, keywordStats);
  
  // Update sort indicators in header
  var table = tbody.parentElement;
  var headers = table.querySelectorAll('th.sortable');
  headers.forEach(function(th) {
    var key = th.getAttribute('data-sort-key');
    th.classList.remove('sort-asc', 'sort-desc');
    if (key === sortKey) {
      th.classList.add(ascending ? 'sort-asc' : 'sort-desc');
    }
  });
}

/**
 * Render table body rows from sorted keyword stats.
 */
function _renderTableBody(tbody, keywordStats) {
  tbody.innerHTML = '';
  
  keywordStats.forEach(function(stat) {
    var row = document.createElement('tr');
    row.className = 'keyword-stat-row';
    row.style.cursor = 'pointer';
    
    // Add click handler to highlight keyword in tree and timeline
    row.addEventListener('click', function() {
      _highlightKeyword(stat);
    });
    
    // Keyword name
    var nameCell = document.createElement('td');
    nameCell.className = 'keyword-name';
    nameCell.textContent = stat.keyword;
    nameCell.title = stat.keyword;
    row.appendChild(nameCell);
    
    // Count
    var countCell = document.createElement('td');
    countCell.className = 'keyword-count';
    countCell.textContent = stat.count;
    row.appendChild(countCell);
    
    // Min duration
    var minCell = document.createElement('td');
    minCell.className = 'keyword-duration';
    minCell.textContent = _formatDuration(stat.minDuration);
    row.appendChild(minCell);
    
    // Max duration
    var maxCell = document.createElement('td');
    maxCell.className = 'keyword-duration';
    maxCell.textContent = _formatDuration(stat.maxDuration);
    row.appendChild(maxCell);
    
    // Avg duration
    var avgCell = document.createElement('td');
    avgCell.className = 'keyword-duration';
    avgCell.textContent = _formatDuration(stat.avgDuration);
    row.appendChild(avgCell);
    
    // Total duration
    var totalCell = document.createElement('td');
    totalCell.className = 'keyword-duration keyword-total';
    totalCell.textContent = _formatDuration(stat.totalDuration);
    row.appendChild(totalCell);
    
    tbody.appendChild(row);
  });
}

/**
 * Highlight all occurrences of a keyword in tree view and timeline.
 */
function _highlightKeyword(stat) {
  // Emit event via the global event bus
  if (window.RFTraceViewer && window.RFTraceViewer.emit) {
    window.RFTraceViewer.emit('keyword-selected', {
      keyword: stat.keyword,
      spanIds: stat.spanIds,
      count: stat.count
    });
  }
}

/**
 * Format duration in milliseconds to a readable string.
 * Always displays in milliseconds for consistency with table headers.
 */
function _formatDuration(ms) {
  if (ms < 0.01) {
    return '< 0.01';
  } else if (ms < 1000) {
    return ms.toFixed(2);
  } else if (ms < 60000) {
    return (ms / 1000).toFixed(2) + 's';
  } else {
    var mins = Math.floor(ms / 60000);
    var secs = ((ms % 60000) / 1000).toFixed(1);
    return mins + 'm ' + secs + 's';
  }
}
