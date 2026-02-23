/* RF Trace Viewer — Expandable Tree View Renderer */

// Store original model for re-rendering on filter changes
var _originalModel = null;
var _treeContainer = null;
var _currentFilteredSpanIds = null;

/**
 * Render the tree view into the given container.
 * @param {HTMLElement} container
 * @param {Object} model - RFRunModel with suites array
 */
function renderTree(container, model) {
  _originalModel = model;
  _treeContainer = container;
  _currentFilteredSpanIds = null; // null = show all
  
  _renderTreeWithFilter(container, model, null);

  // Set up synchronization with timeline
  setupTreeSynchronization();
  
  // Listen for filter changes
  if (window.RFTraceViewer && window.RFTraceViewer.on) {
    window.RFTraceViewer.on('filter-changed', function (data) {
      var filteredSpanIds = {};
      if (data.filteredSpans) {
        for (var i = 0; i < data.filteredSpans.length; i++) {
          filteredSpanIds[data.filteredSpans[i].id] = true;
        }
      }
      _currentFilteredSpanIds = filteredSpanIds;
      _renderTreeWithFilter(container, model, filteredSpanIds);
    });
  }
}

/**
 * Render tree with optional filtering.
 * @param {HTMLElement} container
 * @param {Object} model
 * @param {Object|null} filteredSpanIds - Map of span IDs to show, or null for all
 */

/**
 * Merge same-name sibling suites into single nodes.
 * Handles pabot traces where each worker produces a separate suite span
 * with the same name but different tests. Also applied recursively to
 * nested suites. No-op when all suite names are unique.
 */
function _mergeSameNameSuites(suites) {
  if (!suites || suites.length <= 1) return suites;

  var groups = {};
  var order = [];
  for (var i = 0; i < suites.length; i++) {
    var s = suites[i];
    var key = s.name;
    if (!groups[key]) {
      groups[key] = [];
      order.push(key);
    }
    groups[key].push(s);
  }

  var result = [];
  for (var g = 0; g < order.length; g++) {
    var group = groups[order[g]];
    if (group.length === 1) {
      // Unique name — recurse into children for nested suites
      var solo = group[0];
      solo.children = _mergeSameNameChildren(solo.children);
      result.push(solo);
    } else {
      // Multiple same-name suites — merge into one
      result.push(_mergeGroup(group));
    }
  }
  return result;
}

/** Merge children arrays, applying suite merging to any nested suites. */
function _mergeSameNameChildren(children) {
  if (!children || children.length === 0) return children;

  // Separate suites from non-suites (tests, keywords)
  var childSuites = [];
  var others = [];
  for (var i = 0; i < children.length; i++) {
    var c = children[i];
    // Suites have 'source' and 'children' but no 'keyword_type' or 'tags'
    if (c.children !== undefined && c.keyword_type === undefined && c.tags === undefined) {
      childSuites.push(c);
    } else {
      others.push(c);
    }
  }

  // Merge same-name child suites
  var mergedSuites = _mergeSameNameSuites(childSuites);

  // Recombine: merged suites first, then tests/keywords in original order
  return mergedSuites.concat(others);
}

/** Merge a group of same-name suites into a single virtual suite. */
function _mergeGroup(group) {
  var merged = {};
  var first = group[0];

  // Copy base fields from first suite
  merged.name = first.name;
  merged.id = first.id;
  merged.source = first.source;
  merged.doc = first.doc || '';
  merged.metadata = {};

  // Aggregate: earliest start, latest end, sum elapsed
  var minStart = first.start_time;
  var maxEnd = first.end_time;
  var totalElapsed = 0;
  var worstStatus = 'PASS';
  var statusPriority = { 'FAIL': 3, 'SKIP': 2, 'NOT RUN': 1, 'PASS': 0 };

  var allChildren = [];
  for (var i = 0; i < group.length; i++) {
    var s = group[i];
    if (s.start_time < minStart) minStart = s.start_time;
    if (s.end_time > maxEnd) maxEnd = s.end_time;
    totalElapsed += s.elapsed_time || 0;

    if ((statusPriority[s.status] || 0) > (statusPriority[worstStatus] || 0)) {
      worstStatus = s.status;
    }

    // Merge metadata
    if (s.metadata) {
      var keys = Object.keys(s.metadata);
      for (var k = 0; k < keys.length; k++) {
        merged.metadata[keys[k]] = s.metadata[keys[k]];
      }
    }

    // Collect children
    if (s.children) {
      for (var j = 0; j < s.children.length; j++) {
        allChildren.push(s.children[j]);
      }
    }
  }

  merged.start_time = minStart;
  merged.end_time = maxEnd;
  merged.elapsed_time = totalElapsed;
  merged.status = worstStatus;
  merged.children = _mergeSameNameChildren(allChildren);
  merged._merged_count = group.length;

  return merged;
}

function _renderTreeWithFilter(container, model, filteredSpanIds) {
  container.innerHTML = '';

  // Controls: expand all / collapse all
  var controls = document.createElement('div');
  controls.className = 'tree-controls';

  var expandBtn = document.createElement('button');
  expandBtn.textContent = 'Expand All';
  expandBtn.addEventListener('click', function () { _setAllExpanded(container, true); });

  var collapseBtn = document.createElement('button');
  collapseBtn.textContent = 'Collapse All';
  collapseBtn.addEventListener('click', function () { _setAllExpanded(container, false); });

  controls.appendChild(expandBtn);
  controls.appendChild(collapseBtn);
  container.appendChild(controls);

  // Render suites
  var treeRoot = document.createElement('div');
  treeRoot.className = 'tree-root';
  var suites = _mergeSameNameSuites(model.suites || []);
  for (var i = 0; i < suites.length; i++) {
    var suiteNode = _renderSuiteNode(suites[i], 0, filteredSpanIds);
    if (suiteNode) {
      treeRoot.appendChild(suiteNode);
    }
  }
  container.appendChild(treeRoot);

  // Auto-expand root-level suites so tests are visible immediately
  var rootNodes = treeRoot.querySelectorAll(':scope > .tree-node.depth-0');
  for (var j = 0; j < rootNodes.length; j++) {
    var childrenEl = rootNodes[j].querySelector(':scope > .tree-children');
    var detailEl = rootNodes[j].querySelector(':scope > .detail-panel');
    var toggleBtn = rootNodes[j].querySelector(':scope > .tree-row > .tree-toggle');
    if (childrenEl) childrenEl.classList.add('expanded');
    if (detailEl) detailEl.classList.add('expanded');
    if (toggleBtn) {
      toggleBtn.textContent = '\u25bc'; // ▼
      toggleBtn.setAttribute('aria-label', 'Collapse');
    }
  }
}

/** Render a suite node and its children recursively. */
function _renderSuiteNode(suite, depth, filteredSpanIds) {
  // If filtering is active and this suite is not in the filtered list, skip it
  if (filteredSpanIds !== null && !filteredSpanIds[suite.id]) {
    return null;
  }

  var hasChildren = suite.children && suite.children.length > 0;
  var displayName = suite.name;
  if (suite._merged_count && suite._merged_count > 1) {
    displayName += ' (' + suite._merged_count + ' workers)';
  }
  var node = _createTreeNode({
    type: 'suite',
    name: displayName,
    status: suite.status,
    elapsed: suite.elapsed_time,
    hasChildren: hasChildren,
    depth: depth,
    id: suite.id,
    data: suite
  });

  if (hasChildren) {
    var childrenEl = node.querySelector('.tree-children');
    for (var i = 0; i < suite.children.length; i++) {
      var child = suite.children[i];
      var childNode = null;
      if (child.keyword_type !== undefined) {
        // It's a keyword (SETUP/TEARDOWN at suite level)
        childNode = _renderKeywordNode(child, depth + 1, filteredSpanIds);
      } else if (child.keywords !== undefined) {
        // It's a test
        childNode = _renderTestNode(child, depth + 1, filteredSpanIds);
      } else {
        // It's a nested suite
        childNode = _renderSuiteNode(child, depth + 1, filteredSpanIds);
      }
      if (childNode) {
        childrenEl.appendChild(childNode);
      }
    }
  }
  return node;
}

/** Render a test node and its keywords. */
function _renderTestNode(test, depth, filteredSpanIds) {
  // If filtering is active and this test is not in the filtered list, skip it
  if (filteredSpanIds !== null && !filteredSpanIds[test.id]) {
    return null;
  }

  var hasKws = test.keywords && test.keywords.length > 0;
  var node = _createTreeNode({
    type: 'test',
    name: test.name,
    status: test.status,
    elapsed: test.elapsed_time,
    hasChildren: hasKws,
    depth: depth,
    id: test.id,
    data: test
  });

  if (hasKws) {
    var childrenEl = node.querySelector('.tree-children');
    for (var i = 0; i < test.keywords.length; i++) {
      var kwNode = _renderKeywordNode(test.keywords[i], depth + 1, filteredSpanIds);
      if (kwNode) {
        childrenEl.appendChild(kwNode);
      }
    }
  }
  return node;
}

/** Render a keyword node and its nested keywords. */
function _renderKeywordNode(kw, depth, filteredSpanIds) {
  // If filtering is active and this keyword is not in the filtered list, skip it
  if (filteredSpanIds !== null && !filteredSpanIds[kw.id]) {
    return null;
  }

  var hasChildren = kw.children && kw.children.length > 0;
  var node = _createTreeNode({
    type: 'keyword',
    name: kw.name,
    status: kw.status,
    elapsed: kw.elapsed_time,
    hasChildren: hasChildren,
    depth: depth,
    kwType: kw.keyword_type,
    kwArgs: kw.args,
    id: kw.id,
    data: kw
  });

  if (hasChildren) {
    var childrenEl = node.querySelector('.tree-children');
    for (var i = 0; i < kw.children.length; i++) {
      var childNode = _renderKeywordNode(kw.children[i], depth + 1, filteredSpanIds);
      if (childNode) {
        childrenEl.appendChild(childNode);
      }
    }
  }
  return node;
}

/**
 * Format a nanosecond timestamp to a readable datetime string.
 * @param {number} nanos - Timestamp in nanoseconds
 * @returns {string} Formatted datetime string
 */
function _formatTimestamp(nanos) {
  if (!nanos) return '';
  var ms = nanos / 1000000;
  var d = new Date(ms);
  if (isNaN(d.getTime())) return '';
  var year = d.getFullYear();
  var month = ('0' + (d.getMonth() + 1)).slice(-2);
  var day = ('0' + d.getDate()).slice(-2);
  var hours = ('0' + d.getHours()).slice(-2);
  var minutes = ('0' + d.getMinutes()).slice(-2);
  var seconds = ('0' + d.getSeconds()).slice(-2);
  var millis = ('00' + d.getMilliseconds()).slice(-3);
  return year + '-' + month + '-' + day + ' ' + hours + ':' + minutes + ':' + seconds + '.' + millis;
}

/**
 * Render a detail panel for a tree node based on its type.
 * Only renders fields that have actual content.
 * @param {Object} opts - { type, data, status }
 * @returns {HTMLElement} The detail panel div
 */
function _renderDetailPanel(opts) {
  var data = opts.data || {};
  var panel = document.createElement('div');
  var statusCls = _statusClass(opts.status);
  panel.className = 'detail-panel ' + opts.type + '-detail' + (statusCls ? ' ' + statusCls : '');

  if (opts.type === 'suite') {
    _renderSuiteDetail(panel, data);
  } else if (opts.type === 'test') {
    _renderTestDetail(panel, data);
  } else if (opts.type === 'keyword') {
    _renderKeywordDetail(panel, data);
  }

  return panel;
}

/** Render suite-specific detail rows. */
function _renderSuiteDetail(panel, data) {
  if (data.source) {
    _addDetailRow(panel, 'Source', data.source);
  }
  if (data.doc) {
    _addDetailRow(panel, 'Documentation', data.doc);
  }
  if (data.metadata && Object.keys(data.metadata).length > 0) {
    _addMetadataTable(panel, data.metadata);
  }
  _addStatusRow(panel, data.status);
  if (data.start_time) {
    _addDetailRow(panel, 'Start', _formatTimestamp(data.start_time));
  }
  if (data.end_time) {
    _addDetailRow(panel, 'End', _formatTimestamp(data.end_time));
  }
  _addDetailRow(panel, 'Duration', formatDuration(data.elapsed_time || 0));
  if (data.status === 'FAIL' && data.status_message) {
    _addErrorBlock(panel, data.status_message);
  }
}

/** Render test-specific detail rows. */
function _renderTestDetail(panel, data) {
  if (data.doc) {
    _addDetailRow(panel, 'Documentation', data.doc);
  }
  if (data.tags && data.tags.length > 0) {
    _addTagsRow(panel, data.tags);
  }
  _addStatusRow(panel, data.status);
  if (data.start_time) {
    _addDetailRow(panel, 'Start', _formatTimestamp(data.start_time));
  }
  if (data.end_time) {
    _addDetailRow(panel, 'End', _formatTimestamp(data.end_time));
  }
  _addDetailRow(panel, 'Duration', formatDuration(data.elapsed_time || 0));
  if (data.status === 'FAIL' && data.status_message) {
    _addErrorBlock(panel, data.status_message);
  }
}

/** Render keyword-specific detail rows. */
function _renderKeywordDetail(panel, data) {
  if (data.keyword_type) {
    _addBadgeRow(panel, 'Type', data.keyword_type);
  }
  if (data.args) {
    _addDetailRow(panel, 'Arguments', data.args);
  }
  if (data.doc) {
    _addDetailRow(panel, 'Documentation', data.doc);
  }
  if (data.lineno && data.lineno > 0) {
    var sourceText = data.source ? data.source + ':' + data.lineno : 'Line ' + data.lineno;
    _addDetailRow(panel, 'Source', sourceText);
  }
  _addStatusRow(panel, data.status);
  _addDetailRow(panel, 'Duration', formatDuration(data.elapsed_time || 0));
  if (data.status === 'FAIL' && data.status_message) {
    _addErrorBlock(panel, data.status_message);
  }
  if (data.events && data.events.length > 0) {
    _renderEventsSection(panel, data.events);
  }
}

/** Add a label/value row to the detail panel. */
function _addDetailRow(panel, label, value) {
  var row = document.createElement('div');
  row.className = 'detail-panel-row';
  var labelEl = document.createElement('span');
  labelEl.className = 'detail-label';
  labelEl.textContent = label + ':';
  var valueEl = document.createElement('span');
  valueEl.className = 'detail-value';
  valueEl.textContent = value;
  row.appendChild(labelEl);
  row.appendChild(valueEl);
  panel.appendChild(row);
}

/** Add a status badge row. */
function _addStatusRow(panel, status) {
  var row = document.createElement('div');
  row.className = 'detail-panel-row';
  var labelEl = document.createElement('span');
  labelEl.className = 'detail-label';
  labelEl.textContent = 'Status:';
  var badge = document.createElement('span');
  badge.className = 'detail-badge ' + _statusClass(status);
  badge.textContent = status || 'NOT_RUN';
  row.appendChild(labelEl);
  row.appendChild(badge);
  panel.appendChild(row);
}

/** Add a badge row (for keyword type etc). */
function _addBadgeRow(panel, label, value) {
  var row = document.createElement('div');
  row.className = 'detail-panel-row';
  var labelEl = document.createElement('span');
  labelEl.className = 'detail-label';
  labelEl.textContent = label + ':';
  var badge = document.createElement('span');
  badge.className = 'detail-badge' + (label === 'Type' ? ' kw-type-' + value.toLowerCase() : '');
  badge.textContent = value;
  row.appendChild(labelEl);
  row.appendChild(badge);
  panel.appendChild(row);
}

/** Add tags as badges. */
function _addTagsRow(panel, tags) {
  var row = document.createElement('div');
  row.className = 'detail-panel-row';
  var labelEl = document.createElement('span');
  labelEl.className = 'detail-label';
  labelEl.textContent = 'Tags:';
  var tagsContainer = document.createElement('span');
  tagsContainer.className = 'detail-tags';
  for (var i = 0; i < tags.length; i++) {
    var badge = document.createElement('span');
    badge.className = 'detail-badge tag-badge';
    badge.textContent = tags[i];
    tagsContainer.appendChild(badge);
  }
  row.appendChild(labelEl);
  row.appendChild(tagsContainer);
  panel.appendChild(row);
}

/** Add a metadata table for suites. */
function _addMetadataTable(panel, metadata) {
  var row = document.createElement('div');
  row.className = 'detail-panel-row';
  var labelEl = document.createElement('span');
  labelEl.className = 'detail-label';
  labelEl.textContent = 'Metadata:';
  row.appendChild(labelEl);
  panel.appendChild(row);

  var table = document.createElement('table');
  table.className = 'detail-metadata-table';
  var keys = Object.keys(metadata);
  for (var i = 0; i < keys.length; i++) {
    var tr = document.createElement('tr');
    var th = document.createElement('th');
    th.textContent = keys[i];
    var td = document.createElement('td');
    td.textContent = metadata[keys[i]];
    tr.appendChild(th);
    tr.appendChild(td);
    table.appendChild(tr);
  }
  panel.appendChild(table);
}

/** Add a red error message block. */
function _addErrorBlock(panel, message) {
  var errorEl = document.createElement('div');
  errorEl.className = 'detail-error';
  var preEl = document.createElement('pre');
  preEl.className = 'detail-error-pre';
  preEl.textContent = message;
  errorEl.appendChild(preEl);
  panel.appendChild(errorEl);
}

/**
 * Render span events as a collapsible log entries section.
 * Collapsed by default if more than 5 events.
 * @param {HTMLElement} panel - The detail panel to append to
 * @param {Array} events - Array of OTLP event objects
 */
function _renderEventsSection(panel, events) {
  var section = document.createElement('div');
  section.className = 'events-section';

  var header = document.createElement('button');
  header.className = 'events-header';
  var collapsed = events.length > 5;
  header.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  header.innerHTML = '<span class="events-toggle">' + (collapsed ? '\u25b6' : '\u25bc') + '</span> Log Messages (' + events.length + ')';
  header.addEventListener('click', function (e) {
    e.stopPropagation();
    var list = section.querySelector('.events-list');
    var isHidden = list.style.display === 'none';
    list.style.display = isHidden ? 'block' : 'none';
    var toggleSpan = header.querySelector('.events-toggle');
    toggleSpan.textContent = isHidden ? '\u25bc' : '\u25b6';
    header.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
  });
  section.appendChild(header);

  var list = document.createElement('div');
  list.className = 'events-list';
  list.style.display = collapsed ? 'none' : 'block';

  for (var i = 0; i < events.length; i++) {
    var evt = events[i];
    var entry = document.createElement('div');

    // Extract level from event name or attributes
    var level = _extractEventLevel(evt);
    entry.className = 'event-entry event-level-' + level.toLowerCase();

    // Timestamp
    var timeStr = '';
    if (evt.time_unix_nano) {
      timeStr = _formatTimestamp(evt.time_unix_nano);
    } else if (evt.timeUnixNano) {
      timeStr = _formatTimestamp(evt.timeUnixNano);
    }

    // Message from attributes
    var message = _extractEventMessage(evt);

    var timeEl = document.createElement('span');
    timeEl.className = 'event-time';
    timeEl.textContent = timeStr;
    entry.appendChild(timeEl);

    var levelEl = document.createElement('span');
    levelEl.className = 'event-level';
    levelEl.textContent = level;
    entry.appendChild(levelEl);

    var msgEl = document.createElement('span');
    msgEl.className = 'event-message';
    msgEl.textContent = message;
    entry.appendChild(msgEl);

    list.appendChild(entry);
  }

  section.appendChild(list);
  panel.appendChild(section);
}

/**
 * Extract log level from an OTLP event.
 * Checks event name and attributes for level indicators.
 * @param {Object} evt - OTLP event object
 * @returns {string} Log level: INFO, WARN, ERROR, FAIL, or DEBUG
 */
function _extractEventLevel(evt) {
  var name = (evt.name || '').toLowerCase();

  // Check event name for level hints
  if (name.indexOf('fail') !== -1 || name.indexOf('error') !== -1) return 'ERROR';
  if (name.indexOf('warn') !== -1) return 'WARN';
  if (name.indexOf('debug') !== -1) return 'DEBUG';

  // Check attributes for rf.status or level
  var attrs = evt.attributes;
  if (attrs) {
    // Attributes may be OTLP array format or already flattened dict
    if (Array.isArray(attrs)) {
      for (var i = 0; i < attrs.length; i++) {
        var key = attrs[i].key;
        if (key === 'rf.status' || key === 'level') {
          var val = '';
          if (attrs[i].value && attrs[i].value.string_value) {
            val = attrs[i].value.string_value;
          } else if (typeof attrs[i].value === 'string') {
            val = attrs[i].value;
          }
          val = val.toUpperCase();
          if (val === 'FAIL' || val === 'ERROR') return 'ERROR';
          if (val === 'WARN' || val === 'WARNING') return 'WARN';
          if (val === 'DEBUG') return 'DEBUG';
          if (val === 'PASS' || val === 'INFO') return 'INFO';
        }
      }
    } else if (typeof attrs === 'object') {
      var rfStatus = attrs['rf.status'] || attrs['level'] || '';
      rfStatus = rfStatus.toUpperCase();
      if (rfStatus === 'FAIL' || rfStatus === 'ERROR') return 'ERROR';
      if (rfStatus === 'WARN' || rfStatus === 'WARNING') return 'WARN';
      if (rfStatus === 'DEBUG') return 'DEBUG';
    }
  }

  return 'INFO';
}

/**
 * Extract the message body from an OTLP event.
 * @param {Object} evt - OTLP event object
 * @returns {string} The event message
 */
function _extractEventMessage(evt) {
  var attrs = evt.attributes;
  if (attrs) {
    if (Array.isArray(attrs)) {
      for (var i = 0; i < attrs.length; i++) {
        if (attrs[i].key === 'message') {
          if (attrs[i].value && attrs[i].value.string_value) {
            return attrs[i].value.string_value;
          }
          if (typeof attrs[i].value === 'string') {
            return attrs[i].value;
          }
        }
      }
    } else if (typeof attrs === 'object' && attrs.message) {
      return String(attrs.message);
    }
  }
  // Fallback to event name
  return evt.name || '';
}

/**
 * Create a single tree node DOM element.
 * @param {Object} opts - { type, name, status, elapsed, hasChildren, depth, kwType?, kwArgs?, id?, data? }
 */
function _createTreeNode(opts) {
  var wrapper = document.createElement('div');
  wrapper.className = 'tree-node depth-' + opts.depth;
  if (opts.id) {
    wrapper.setAttribute('data-span-id', opts.id);
  }

  var row = document.createElement('div');
  row.className = 'tree-row';

  // Toggle arrow (or spacer)
  var toggle = document.createElement('button');
  toggle.className = 'tree-toggle';
  toggle.textContent = '\u25b6'; // ▶
  toggle.setAttribute('aria-label', 'Expand');
  toggle.addEventListener('click', function (e) {
    e.stopPropagation();
    _toggleNode(wrapper);
  });
  row.appendChild(toggle);

  // Status icon
  var statusIcon = document.createElement('span');
  statusIcon.className = 'tree-status-icon ' + _statusClass(opts.status);
  statusIcon.textContent = _statusIcon(opts.status);
  statusIcon.setAttribute('aria-label', opts.status || 'NOT_RUN');
  row.appendChild(statusIcon);

  // Name
  var nameEl = document.createElement('span');
  nameEl.className = 'tree-name';

  var typeLabel = document.createElement('span');
  typeLabel.className = 'node-type';
  typeLabel.textContent = opts.kwType || opts.type;
  nameEl.appendChild(typeLabel);

  nameEl.appendChild(document.createTextNode(opts.name));

  // Keyword args inline
  if (opts.kwArgs) {
    var argsEl = document.createElement('span');
    argsEl.className = 'kw-args';
    argsEl.textContent = opts.kwArgs;
    nameEl.appendChild(argsEl);
  }
  row.appendChild(nameEl);

  // Duration
  var durEl = document.createElement('span');
  durEl.className = 'tree-duration';
  durEl.textContent = formatDuration(opts.elapsed || 0);
  row.appendChild(durEl);

  wrapper.appendChild(row);

  // Inline error snippet for FAIL nodes (always visible, truncated)
  if (opts.status === 'FAIL' && opts.data && opts.data.status_message) {
    var errorSnippet = document.createElement('div');
    errorSnippet.className = 'tree-error-snippet';
    var truncated = opts.data.status_message;
    // Truncate to first line, max 150 chars
    var newlineIdx = truncated.indexOf('\n');
    if (newlineIdx !== -1) {
      truncated = truncated.substring(0, newlineIdx);
    }
    if (truncated.length > 150) {
      truncated = truncated.substring(0, 150) + '\u2026';
    }
    errorSnippet.textContent = truncated;
    wrapper.appendChild(errorSnippet);
  }

  // Detail panel — inserted between row and children
  var detailPanel = _renderDetailPanel({
    type: opts.type,
    status: opts.status,
    data: opts.data
  });
  wrapper.appendChild(detailPanel);

  // Click row to toggle (all nodes have detail panels)
  row.addEventListener('click', function () { _toggleNode(wrapper); });

  // Emit event when node is clicked (for timeline synchronization)
  row.addEventListener('click', function (e) {
    var capturedId = opts.id;
    var capturedName = opts.name;
    console.log('[Tree] Node clicked:', capturedName, 'id:', capturedId);
    console.log('[Tree] opts object:', JSON.stringify({ id: opts.id, name: opts.name, type: opts.type }));
    if (capturedId && window.RFTraceViewer && window.RFTraceViewer.emit) {
      console.log('[Tree] Emitting span-selected event for id:', capturedId);
      window.RFTraceViewer.emit('span-selected', { spanId: capturedId, source: 'tree' });
    } else {
      console.warn('[Tree] Cannot emit event - missing id or RFTraceViewer:', { 
        hasId: !!capturedId, 
        hasRFTraceViewer: !!window.RFTraceViewer,
        hasEmit: !!(window.RFTraceViewer && window.RFTraceViewer.emit)
      });
    }
  });

  // Children container
  if (opts.hasChildren) {
    var childrenEl = document.createElement('div');
    childrenEl.className = 'tree-children';
    wrapper.appendChild(childrenEl);
  }

  return wrapper;
}

/** Toggle expand/collapse on a tree node. */
function _toggleNode(nodeEl) {
  var childrenEl = nodeEl.querySelector(':scope > .tree-children');
  var detailEl = nodeEl.querySelector(':scope > .detail-panel');
  var toggleBtn = nodeEl.querySelector(':scope > .tree-row > .tree-toggle');
  // Need either children or detail panel to toggle
  if (!childrenEl && !detailEl) return;

  var isExpanded = (childrenEl && childrenEl.classList.contains('expanded')) ||
                   (detailEl && detailEl.classList.contains('expanded'));
  if (isExpanded) {
    if (childrenEl) childrenEl.classList.remove('expanded');
    if (detailEl) detailEl.classList.remove('expanded');
    if (toggleBtn) {
      toggleBtn.textContent = '\u25b6'; // ▶
      toggleBtn.setAttribute('aria-label', 'Expand');
    }
  } else {
    if (childrenEl) childrenEl.classList.add('expanded');
    if (detailEl) detailEl.classList.add('expanded');
    if (toggleBtn) {
      toggleBtn.textContent = '\u25bc'; // ▼
      toggleBtn.setAttribute('aria-label', 'Collapse');
    }
  }
}

/** Expand or collapse all nodes in the tree. */
function _setAllExpanded(container, expand) {
  var childrenEls = container.querySelectorAll('.tree-children');
  var detailEls = container.querySelectorAll('.detail-panel');
  var toggleBtns = container.querySelectorAll('.tree-toggle');

  for (var i = 0; i < childrenEls.length; i++) {
    if (expand) {
      childrenEls[i].classList.add('expanded');
    } else {
      childrenEls[i].classList.remove('expanded');
    }
  }
  for (var i = 0; i < detailEls.length; i++) {
    if (expand) {
      detailEls[i].classList.add('expanded');
    } else {
      detailEls[i].classList.remove('expanded');
    }
  }
  for (var j = 0; j < toggleBtns.length; j++) {
    if (toggleBtns[j].textContent) {
      toggleBtns[j].textContent = expand ? '\u25bc' : '\u25b6';
      toggleBtns[j].setAttribute('aria-label', expand ? 'Collapse' : 'Expand');
    }
  }
}

/** Map status string to CSS class. */
function _statusClass(status) {
  switch (status) {
    case 'PASS': return 'pass';
    case 'FAIL': return 'fail';
    case 'SKIP': return 'skip';
    default: return 'not-run';
  }
}

/** Map status string to icon character. */
function _statusIcon(status) {
  switch (status) {
    case 'PASS': return '\u2713'; // ✓
    case 'FAIL': return '\u2717'; // ✗
    case 'SKIP': return '\u2298'; // ⊘
    default: return '\u25cb';     // ○
  }
}

/**
 * Highlight and scroll to a tree node by span ID.
 * Called when a span is clicked in the timeline.
 * @param {string} spanId - The span ID to highlight
 */
function highlightNodeInTree(spanId) {
  // Clear previous highlights
  var previousHighlights = document.querySelectorAll('.tree-node.highlighted');
  for (var i = 0; i < previousHighlights.length; i++) {
    previousHighlights[i].classList.remove('highlighted');
  }

  // Find the node with the matching span ID
  var targetNode = document.querySelector('.tree-node[data-span-id="' + spanId + '"]');
  if (!targetNode) return;

  // Expand all parent nodes to make the target visible
  var parent = targetNode.parentElement;
  while (parent) {
    if (parent.classList.contains('tree-children')) {
      parent.classList.add('expanded');
      // Also expand sibling detail panels
      var parentNode = parent.parentElement;
      if (parentNode && parentNode.classList.contains('tree-node')) {
        var detailEl = parentNode.querySelector(':scope > .detail-panel');
        if (detailEl) detailEl.classList.add('expanded');
        var toggleBtn = parentNode.querySelector(':scope > .tree-row > .tree-toggle');
        if (toggleBtn) {
          toggleBtn.textContent = '\u25bc'; // ▼
          toggleBtn.setAttribute('aria-label', 'Collapse');
        }
      }
    }
    parent = parent.parentElement;
  }

  // Highlight the target node
  targetNode.classList.add('highlighted');

  // Scroll the node into view
  targetNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/**
 * Set up event listeners for timeline synchronization.
 * Should be called after the tree is rendered.
 */
function setupTreeSynchronization() {
  if (window.RFTraceViewer && window.RFTraceViewer.on) {
    window.RFTraceViewer.on('span-selected', function (data) {
      // Only respond to events from the timeline
      if (data.source === 'timeline' && data.spanId) {
        highlightNodeInTree(data.spanId);
      } else if (data.source === 'tree' && data.spanId) {
        // Tree node was clicked, highlight in timeline
        if (window.highlightSpanInTimeline) {
          window.highlightSpanInTimeline(data.spanId);
        }
      }
    });
  }
}

// Expose public API
window.highlightNodeInTree = highlightNodeInTree;
window.setupTreeSynchronization = setupTreeSynchronization;
