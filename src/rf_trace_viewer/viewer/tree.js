/* RF Trace Viewer — Expandable Tree View Renderer */

// Store original model for re-rendering on filter changes
var _originalModel = null;
var _treeContainer = null;
var _currentFilteredSpanIds = null;
var _failuresOnlyActive = false;

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

/**
 * Count total spans in the model for performance logging.
 * @param {Object} model - RFRunModel with suites array
 * @returns {number} Total span count
 */
function _countSpans(model) {
  var count = 0;
  function countSuite(suite) {
    count++;
    if (suite.children) {
      for (var i = 0; i < suite.children.length; i++) {
        var child = suite.children[i];
        if (child.keyword_type !== undefined) {
          countKeyword(child);
        } else if (child.keywords !== undefined) {
          countTest(child);
        } else {
          countSuite(child);
        }
      }
    }
  }
  function countTest(test) {
    count++;
    if (test.keywords) {
      for (var i = 0; i < test.keywords.length; i++) {
        countKeyword(test.keywords[i]);
      }
    }
  }
  function countKeyword(kw) {
    count++;
    if (kw.children) {
      for (var i = 0; i < kw.children.length; i++) {
        countKeyword(kw.children[i]);
      }
    }
  }
  var suites = model.suites || [];
  for (var i = 0; i < suites.length; i++) {
    countSuite(suites[i]);
  }
  return count;
}

/**
 * Check if any descendant of a data item matches the filter.
 * Works on the DATA model, not the DOM.
 * @param {Object} item - suite, test, or keyword data object
 * @param {Object} filteredSpanIds - Map of span IDs to show
 * @returns {boolean}
 */
function _hasDescendantInFilter(item, filteredSpanIds) {
  if (filteredSpanIds[item.id]) return true;
  // Check children (suites and keywords)
  if (item.children) {
    for (var i = 0; i < item.children.length; i++) {
      if (_hasDescendantInFilter(item.children[i], filteredSpanIds)) return true;
    }
  }
  // Check keywords (tests)
  if (item.keywords) {
    for (var j = 0; j < item.keywords.length; j++) {
      if (_hasDescendantInFilter(item.keywords[j], filteredSpanIds)) return true;
    }
  }
  return false;
}

/**
 * Check if any descendant of a data item has FAIL status.
 * Works on the DATA model to find failure paths without DOM.
 * @param {Object} item - suite, test, or keyword data object
 * @returns {boolean}
 */
function _hasDescendantFail(item) {
  if (item.status === 'FAIL') return true;
  if (item.children) {
    for (var i = 0; i < item.children.length; i++) {
      if (_hasDescendantFail(item.children[i])) return true;
    }
  }
  if (item.keywords) {
    for (var j = 0; j < item.keywords.length; j++) {
      if (_hasDescendantFail(item.keywords[j])) return true;
    }
  }
  return false;
}

function _renderTreeWithFilter(container, model, filteredSpanIds) {
  var t0 = Date.now();
  container.innerHTML = '';

  // Controls: expand all / collapse all / failures only
  var controls = document.createElement('div');
  controls.className = 'tree-controls';

  var expandBtn = document.createElement('button');
  expandBtn.textContent = 'Expand All';
  expandBtn.addEventListener('click', function () { _setAllExpanded(container, true); });

  var collapseBtn = document.createElement('button');
  collapseBtn.textContent = 'Collapse All';
  collapseBtn.addEventListener('click', function () { _setAllExpanded(container, false); });

  var failuresBtn = document.createElement('button');
  failuresBtn.textContent = 'Failures Only';
  failuresBtn.className = 'failures-only-toggle' + (_failuresOnlyActive ? ' active' : '');
  failuresBtn.setAttribute('aria-pressed', _failuresOnlyActive ? 'true' : 'false');
  failuresBtn.title = _failuresOnlyActive ? 'Show all test results' : 'Show only failing tests';
  failuresBtn.addEventListener('click', function () {
    _failuresOnlyActive = !_failuresOnlyActive;
    if (_failuresOnlyActive) {
      // Set filter to show only FAIL status
      if (typeof window.setFilterState === 'function') {
        window.setFilterState({ testStatuses: ['FAIL'] });
      }
      // Sync sidebar checkboxes
      _syncStatusCheckboxes(['FAIL']);
    } else {
      // Restore filter to show all statuses
      if (typeof window.setFilterState === 'function') {
        window.setFilterState({ testStatuses: ['PASS', 'FAIL', 'SKIP'] });
      }
      // Sync sidebar checkboxes
      _syncStatusCheckboxes(['PASS', 'FAIL', 'SKIP']);
    }
  });

  controls.appendChild(expandBtn);
  controls.appendChild(collapseBtn);
  controls.appendChild(failuresBtn);
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

  // Auto-expand failure path or root suites on initial load
  _autoExpandFirstFailure(treeRoot, suites);

  var elapsed = Date.now() - t0;
  var spanCount = _countSpans(model);
  console.log('[Tree] Rendered ' + spanCount + ' spans in ' + elapsed + 'ms (lazy children enabled)');
}

/**
 * Find the first failure path through the DATA model.
 * Returns an array of span IDs from root to the first FAIL leaf.
 * @param {Array} suites - Array of suite data objects
 * @returns {Array} Array of span IDs forming the failure path, or empty array
 */
function _findFirstFailPath(suites) {
  function walkSuite(suite) {
    if (suite.status !== 'FAIL') return null;
    var path = [suite.id];
    if (suite.children) {
      for (var i = 0; i < suite.children.length; i++) {
        var child = suite.children[i];
        var childPath = null;
        if (child.keyword_type !== undefined) {
          childPath = walkKeyword(child);
        } else if (child.keywords !== undefined) {
          childPath = walkTest(child);
        } else {
          childPath = walkSuite(child);
        }
        if (childPath) return path.concat(childPath);
      }
    }
    return path;
  }
  function walkTest(test) {
    if (test.status !== 'FAIL') return null;
    var path = [test.id];
    if (test.keywords) {
      for (var i = 0; i < test.keywords.length; i++) {
        var kwPath = walkKeyword(test.keywords[i]);
        if (kwPath) return path.concat(kwPath);
      }
    }
    return path;
  }
  function walkKeyword(kw) {
    if (kw.status !== 'FAIL') return null;
    var path = [kw.id];
    if (kw.children) {
      for (var i = 0; i < kw.children.length; i++) {
        var childPath = walkKeyword(kw.children[i]);
        if (childPath) return path.concat(childPath);
      }
    }
    return path;
  }
  for (var i = 0; i < suites.length; i++) {
    var result = walkSuite(suites[i]);
    if (result) return result;
  }
  return [];
}

/**
 * Auto-expand the path to the first failure on initial load.
 * Uses the DATA model to find the failure path, then materializes
 * lazy children along that path before expanding.
 * If no failures exist, expand only root-level suites (default behavior).
 * @param {HTMLElement} treeRoot - The .tree-root container element
 * @param {Array} suites - The merged suite data array
 */
function _autoExpandFirstFailure(treeRoot, suites) {
  var failPath = _findFirstFailPath(suites);

  if (!failPath || failPath.length === 0) {
    // No failures — expand root suites only (original behavior)
    var rootNodes = treeRoot.querySelectorAll(':scope > .tree-node.depth-0');
    for (var j = 0; j < rootNodes.length; j++) {
      _materializeIfNeeded(rootNodes[j]);
      _expandNodeOnly(rootNodes[j]);
    }
    return;
  }

  // Materialize and expand each node along the failure path
  var failNode = null;
  for (var i = 0; i < failPath.length; i++) {
    var spanId = failPath[i];
    var node = treeRoot.querySelector('.tree-node[data-span-id="' + spanId + '"]');
    if (!node) break;
    failNode = node;
    _materializeIfNeeded(node);
    _expandNodeOnly(node);
    // Also expand the .tree-children container
    var childrenEl = node.querySelector(':scope > .tree-children');
    if (childrenEl) childrenEl.classList.add('expanded');
  }

  // Scroll the failing node into view after the DOM settles
  if (failNode) {
    requestAnimationFrame(function () {
      var treePanel = failNode.closest('.panel-tree');
      if (treePanel) {
        var panelRect = treePanel.getBoundingClientRect();
        var nodeRect = failNode.getBoundingClientRect();
        var scrollOffset = nodeRect.top - panelRect.top - panelRect.height / 3 + nodeRect.height / 2;
        treePanel.scrollBy({ top: scrollOffset, behavior: 'smooth' });
      } else {
        failNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }
}

/**
 * Expand a single tree node (toggle arrow + children container) without toggling.
 * Does NOT expand detail panels — only structural children.
 * @param {HTMLElement} nodeEl - A .tree-node element
 */
function _expandNodeOnly(nodeEl) {
  var childrenEl = nodeEl.querySelector(':scope > .tree-children');
  var toggleBtn = nodeEl.querySelector(':scope > .tree-row > .tree-toggle');
  if (childrenEl) childrenEl.classList.add('expanded');
  if (toggleBtn) {
    toggleBtn.textContent = '\u25bc'; // ▼
    toggleBtn.setAttribute('aria-label', 'Collapse');
  }
}

/**
 * Materialize lazy children for a node if they haven't been rendered yet.
 * @param {HTMLElement} nodeEl - A .tree-node element
 */
function _materializeIfNeeded(nodeEl) {
  if (!nodeEl._lazyChildren) return;
  _materializeChildren(nodeEl);
}

/**
 * Render lazy children into a DocumentFragment and append to the node's .tree-children element.
 * @param {HTMLElement} nodeEl - A .tree-node element with _lazyChildren data
 */
function _materializeChildren(nodeEl) {
  var lazy = nodeEl._lazyChildren;
  if (!lazy) return;

  var childrenEl = nodeEl.querySelector(':scope > .tree-children');
  if (!childrenEl) return;

  var fragment = document.createDocumentFragment();

  if (lazy.type === 'suite') {
    for (var i = 0; i < lazy.items.length; i++) {
      var child = lazy.items[i];
      var childNode = null;
      if (child.keyword_type !== undefined) {
        childNode = _renderKeywordNode(child, lazy.depth, lazy.filteredSpanIds);
      } else if (child.keywords !== undefined) {
        childNode = _renderTestNode(child, lazy.depth, lazy.filteredSpanIds, lazy.maxSiblingDuration);
      } else {
        childNode = _renderSuiteNode(child, lazy.depth, lazy.filteredSpanIds);
      }
      if (childNode) {
        fragment.appendChild(childNode);
      }
    }
  } else if (lazy.type === 'test') {
    for (var j = 0; j < lazy.items.length; j++) {
      var kwNode = _renderKeywordNode(lazy.items[j], lazy.depth, lazy.filteredSpanIds);
      if (kwNode) {
        fragment.appendChild(kwNode);
      }
    }
  } else if (lazy.type === 'keyword') {
    for (var k = 0; k < lazy.items.length; k++) {
      var nestedNode = _renderKeywordNode(lazy.items[k], lazy.depth, lazy.filteredSpanIds);
      if (nestedNode) {
        fragment.appendChild(nestedNode);
      }
    }
  }

  childrenEl.appendChild(fragment);
  nodeEl._lazyChildren = null;
}

/** Render a suite node with lazy children (children rendered on first expand). */
function _renderSuiteNode(suite, depth, filteredSpanIds) {
  // If filtering is active and this suite is not in the filtered list,
  // still render it if any descendant matches (so the tree structure is preserved).
  var suiteMatchesFilter = (filteredSpanIds === null || filteredSpanIds[suite.id]);

  var hasChildren = suite.children && suite.children.length > 0;
  var displayName = suite.name;
  if (suite._merged_count && suite._merged_count > 1) {
    displayName += ' (' + suite._merged_count + ' workers)';
  }

  // Compute max test duration among sibling tests for sparkline bars
  var maxTestDuration = 0;
  if (hasChildren) {
    for (var j = 0; j < suite.children.length; j++) {
      var c = suite.children[j];
      if (c.keywords !== undefined && c.elapsed_time > maxTestDuration) {
        maxTestDuration = c.elapsed_time;
      }
    }
  }

  // Check if any descendant matches the filter (using DATA model, not DOM)
  var hasMatchingDescendant = false;
  if (hasChildren && filteredSpanIds !== null) {
    hasMatchingDescendant = _hasDescendantInFilter(suite, filteredSpanIds);
  }

  // Skip this suite if it doesn't match and has no matching descendants
  if (!suiteMatchesFilter && !hasMatchingDescendant) {
    return null;
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

  // Store lazy children data instead of rendering them now
  if (hasChildren) {
    node._lazyChildren = {
      items: suite.children,
      type: 'suite',
      filteredSpanIds: filteredSpanIds,
      depth: depth + 1,
      maxSiblingDuration: maxTestDuration
    };
  }

  return node;
}

/** Render a test node with lazy keyword children. */
function _renderTestNode(test, depth, filteredSpanIds, maxSiblingDuration) {
  var testMatchesFilter = (filteredSpanIds === null || filteredSpanIds[test.id]);

  var hasKws = test.keywords && test.keywords.length > 0;

  // Check if any descendant keyword matches the filter (using DATA model)
  var hasMatchingDescendant = false;
  if (hasKws && filteredSpanIds !== null) {
    hasMatchingDescendant = _hasDescendantInFilter(test, filteredSpanIds);
  }

  // Skip this test if it doesn't match and has no matching descendants
  if (!testMatchesFilter && !hasMatchingDescendant) {
    return null;
  }

  var node = _createTreeNode({
    type: 'test',
    name: test.name,
    status: test.status,
    elapsed: test.elapsed_time,
    hasChildren: hasKws,
    depth: depth,
    id: test.id,
    data: test,
    maxSiblingDuration: maxSiblingDuration || 0
  });

  // Store lazy children data instead of rendering them now
  if (hasKws) {
    node._lazyChildren = {
      items: test.keywords,
      type: 'test',
      filteredSpanIds: filteredSpanIds,
      depth: depth + 1
    };
  }

  return node;
}

/** Render a keyword node with lazy nested keyword children. */
function _renderKeywordNode(kw, depth, filteredSpanIds) {
  var kwMatchesFilter = (filteredSpanIds === null || filteredSpanIds[kw.id]);

  var hasChildren = kw.children && kw.children.length > 0;

  // Check if any descendant matches the filter (using DATA model)
  var hasMatchingDescendant = false;
  if (hasChildren && filteredSpanIds !== null) {
    hasMatchingDescendant = _hasDescendantInFilter(kw, filteredSpanIds);
  }

  // Skip this keyword if it doesn't match and has no matching descendants
  if (!kwMatchesFilter && !hasMatchingDescendant) {
    return null;
  }

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

  // Store lazy children data instead of rendering them now
  if (hasChildren) {
    node._lazyChildren = {
      items: kw.children,
      type: 'keyword',
      filteredSpanIds: filteredSpanIds,
      depth: depth + 1
    };
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
  _addCompactInfoBar(panel, data);
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
  _addCompactInfoBar(panel, data);
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
  _addCompactInfoBar(panel, data);
  if (data.status === 'FAIL' && data.status_message) {
    _addErrorBlock(panel, data.status_message);
  }
  if (data.events && data.events.length > 0) {
    _renderEventsSection(panel, data.events);
  }
}

/** Add a compact info bar with status, duration, and timestamps on one line. */
function _addCompactInfoBar(panel, data) {
  var bar = document.createElement('div');
  bar.className = 'detail-info-bar';

  // Status badge
  var statusCls = _statusClass(data.status);
  var badge = document.createElement('span');
  badge.className = 'detail-badge' + (statusCls ? ' ' + statusCls : '');
  badge.textContent = data.status || 'UNKNOWN';
  bar.appendChild(badge);

  // Duration
  var dur = document.createElement('span');
  dur.className = 'detail-info-item';
  dur.textContent = formatDuration(data.elapsed_time || 0);
  bar.appendChild(dur);

  // Timestamps (compact)
  if (data.start_time) {
    var timeSpan = document.createElement('span');
    timeSpan.className = 'detail-info-time';
    var startStr = _formatTimestamp(data.start_time);
    var endStr = data.end_time ? _formatTimestamp(data.end_time) : '';
    timeSpan.textContent = startStr + (endStr ? ' \u2192 ' + endStr : '');
    bar.appendChild(timeSpan);
  }

  panel.appendChild(bar);
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
  toggle.className = 'tree-toggle toggle-' + opts.type + ' ' + _statusClass(opts.status);
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

  // Mini-timeline sparkline for test nodes
  if (opts.type === 'test' && opts.maxSiblingDuration > 0) {
    var sparkline = document.createElement('span');
    sparkline.className = 'tree-sparkline';
    var pct = Math.round(((opts.elapsed || 0) / opts.maxSiblingDuration) * 100);
    if (pct < 1 && (opts.elapsed || 0) > 0) pct = 1;
    var barColor = 'var(--status-pass)';
    if (opts.status === 'FAIL') barColor = 'var(--status-fail)';
    else if (opts.status === 'SKIP') barColor = 'var(--status-skip)';
    sparkline.style.width = pct + '%';
    sparkline.style.backgroundColor = barColor;
    row.appendChild(sparkline);
  }

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
      console.log('[Tree] Emitting navigate-to-span event for id:', capturedId);
      window.RFTraceViewer.emit('navigate-to-span', { spanId: capturedId, source: 'tree' });
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

/** Toggle expand/collapse on a tree node. Materializes lazy children on first expand. */
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
    // Materialize lazy children on first expand
    if (nodeEl._lazyChildren) {
      _materializeChildren(nodeEl);
    }
    if (childrenEl) childrenEl.classList.add('expanded');
    if (detailEl) detailEl.classList.add('expanded');
    if (toggleBtn) {
      toggleBtn.textContent = '\u25bc'; // ▼
      toggleBtn.setAttribute('aria-label', 'Collapse');
    }
    // Scroll so the clicked node is at the top of the visible area,
    // revealing its newly expanded children below.
    // Only scrolls if the node would otherwise be near the bottom;
    // never scrolls the node above the top of the scroll container.
    requestAnimationFrame(function () {
      var row = nodeEl.querySelector(':scope > .tree-row');
      if (!row) return;
      var scrollParent = row.closest('.panel-tree') || row.parentElement;
      if (!scrollParent) return;
      var containerRect = scrollParent.getBoundingClientRect();
      var rowRect = row.getBoundingClientRect();
      // If the row is in the bottom half of the container, scroll it to the top
      if (rowRect.top > containerRect.top + containerRect.height * 0.4) {
        var offset = rowRect.top - containerRect.top + scrollParent.scrollTop;
        scrollParent.scrollTo({ top: offset, behavior: 'smooth' });
      }
    });
  }
}

/**
 * Expand or collapse all nodes in the tree using requestAnimationFrame batching.
 * Materializes lazy children when expanding. Processes ~100 nodes per frame.
 */
function _setAllExpanded(container, expand) {
  // First, if expanding, materialize all lazy children
  if (expand) {
    var allNodes = container.querySelectorAll('.tree-node');
    var lazyQueue = [];
    for (var n = 0; n < allNodes.length; n++) {
      if (allNodes[n]._lazyChildren) {
        lazyQueue.push(allNodes[n]);
      }
    }
    // Materialize all lazy nodes first (this may create new lazy nodes)
    // Keep materializing until no more lazy nodes remain
    while (lazyQueue.length > 0) {
      var node = lazyQueue.shift();
      if (node._lazyChildren) {
        _materializeChildren(node);
      }
      // Check for newly created lazy children
      var newChildren = node.querySelectorAll('.tree-node');
      for (var nc = 0; nc < newChildren.length; nc++) {
        if (newChildren[nc]._lazyChildren) {
          lazyQueue.push(newChildren[nc]);
        }
      }
    }
  }

  // Now collect all elements to toggle
  var childrenEls = container.querySelectorAll('.tree-children');
  var detailEls = container.querySelectorAll('.detail-panel');
  var toggleBtns = container.querySelectorAll('.tree-toggle');

  // Combine all operations into a single list for batching
  var ops = [];
  for (var i = 0; i < childrenEls.length; i++) {
    ops.push({ el: childrenEls[i], kind: 'class' });
  }
  for (var j = 0; j < detailEls.length; j++) {
    ops.push({ el: detailEls[j], kind: 'class' });
  }
  for (var k = 0; k < toggleBtns.length; k++) {
    ops.push({ el: toggleBtns[k], kind: 'toggle' });
  }

  var BATCH_SIZE = 100;
  var idx = 0;

  function processBatch() {
    var end = Math.min(idx + BATCH_SIZE, ops.length);
    for (var b = idx; b < end; b++) {
      var op = ops[b];
      if (op.kind === 'class') {
        if (expand) {
          op.el.classList.add('expanded');
        } else {
          op.el.classList.remove('expanded');
        }
      } else if (op.kind === 'toggle') {
        if (op.el.textContent) {
          op.el.textContent = expand ? '\u25bc' : '\u25b6';
          op.el.setAttribute('aria-label', expand ? 'Collapse' : 'Expand');
        }
      }
    }
    idx = end;
    if (idx < ops.length) {
      requestAnimationFrame(processBatch);
    }
  }

  if (ops.length > 0) {
    requestAnimationFrame(processBatch);
  }
}

/**
 * Sync sidebar test-status checkboxes to match the given active statuses.
 * Keeps the filter panel UI consistent when Failures Only toggle changes state.
 */
function _syncStatusCheckboxes(activeStatuses) {
  var checkboxes = document.querySelectorAll('.filter-checkbox-group input[type="checkbox"]');
  for (var i = 0; i < checkboxes.length; i++) {
    var cb = checkboxes[i];
    // Only sync test-status checkboxes (PASS, FAIL, SKIP)
    if (cb.value === 'PASS' || cb.value === 'FAIL' || cb.value === 'SKIP') {
      cb.checked = activeStatuses.indexOf(cb.value) !== -1;
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
 * Materializes lazy ancestors if the target node is not yet in the DOM.
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

  // If not found, the node may be inside a lazy (unmaterialized) subtree.
  // Walk the original model to find the ancestor path, materialize along the way.
  if (!targetNode && _originalModel) {
    var ancestorPath = _findAncestorPath(_originalModel, spanId);
    if (ancestorPath) {
      for (var a = 0; a < ancestorPath.length; a++) {
        var ancestorNode = document.querySelector('.tree-node[data-span-id="' + ancestorPath[a] + '"]');
        if (ancestorNode) {
          _materializeIfNeeded(ancestorNode);
          _expandNodeOnly(ancestorNode);
          var chEl = ancestorNode.querySelector(':scope > .tree-children');
          if (chEl) chEl.classList.add('expanded');
        }
      }
      // Try finding the target again after materialization
      targetNode = document.querySelector('.tree-node[data-span-id="' + spanId + '"]');
    }
  }

  if (!targetNode) return;

  // Expand all parent nodes to make the target visible
  var parent = targetNode.parentElement;
  while (parent) {
    if (parent.classList.contains('tree-children')) {
      parent.classList.add('expanded');
      // Also expand sibling detail panels
      var parentNode = parent.parentElement;
      if (parentNode && parentNode.classList.contains('tree-node')) {
        _materializeIfNeeded(parentNode);
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

  // Scroll only within the tree panel container (not the whole page)
  var treePanel = document.querySelector('.panel-tree');
  if (treePanel) {
    var panelRect = treePanel.getBoundingClientRect();
    var nodeRect = targetNode.getBoundingClientRect();
    var scrollOffset = nodeRect.top - panelRect.top - panelRect.height / 2 + nodeRect.height / 2;
    treePanel.scrollBy({ top: scrollOffset, behavior: 'smooth' });
  } else {
    targetNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

/**
 * Find the ancestor path (array of span IDs) from root to the target span
 * by walking the data model. Returns null if not found.
 * @param {Object} model - RFRunModel
 * @param {string} targetId - The span ID to find
 * @returns {Array|null} Array of ancestor span IDs (excluding target), or null
 */
function _findAncestorPath(model, targetId) {
  function walkSuite(suite, path) {
    if (suite.id === targetId) return path;
    var newPath = path.concat([suite.id]);
    if (suite.children) {
      for (var i = 0; i < suite.children.length; i++) {
        var child = suite.children[i];
        var result = null;
        if (child.keyword_type !== undefined) {
          result = walkKeyword(child, newPath);
        } else if (child.keywords !== undefined) {
          result = walkTest(child, newPath);
        } else {
          result = walkSuite(child, newPath);
        }
        if (result) return result;
      }
    }
    return null;
  }
  function walkTest(test, path) {
    if (test.id === targetId) return path;
    var newPath = path.concat([test.id]);
    if (test.keywords) {
      for (var i = 0; i < test.keywords.length; i++) {
        var result = walkKeyword(test.keywords[i], newPath);
        if (result) return result;
      }
    }
    return null;
  }
  function walkKeyword(kw, path) {
    if (kw.id === targetId) return path;
    var newPath = path.concat([kw.id]);
    if (kw.children) {
      for (var i = 0; i < kw.children.length; i++) {
        var result = walkKeyword(kw.children[i], newPath);
        if (result) return result;
      }
    }
    return null;
  }
  var suites = model.suites || [];
  for (var i = 0; i < suites.length; i++) {
    var result = walkSuite(suites[i], []);
    if (result) return result;
  }
  return null;
}

/**
 * Set up event listeners for timeline synchronization.
 * Should be called after the tree is rendered.
 */
function setupTreeSynchronization() {
  if (window.RFTraceViewer && window.RFTraceViewer.on) {
    window.RFTraceViewer.on('navigate-to-span', function (data) {
      // Only respond when the event didn't originate from the tree
      if (data.source !== 'tree' && data.spanId) {
        highlightNodeInTree(data.spanId);
      }
    });
  }
}

// Expose public API
window.highlightNodeInTree = highlightNodeInTree;
window.setupTreeSynchronization = setupTreeSynchronization;
