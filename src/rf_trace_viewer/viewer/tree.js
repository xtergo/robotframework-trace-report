/* RF Trace Viewer — Expandable Tree View Renderer */

/** Format duration from milliseconds to human-readable string. */
function formatDuration(ms) {
  if (typeof ms !== 'number' || ms <= 0) return '0ms';
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

// Store original model for re-rendering on filter changes
var _originalModel = null;
var _treeContainer = null;
var _currentFilteredSpanIds = null;
var _failuresOnlyActive = false;
var _filterListenerRegistered = false;

// Virtual scrolling state — only used when span count > VIRTUAL_THRESHOLD
var _virtualState = null;
var VIRTUAL_THRESHOLD = 5000;
var VIRTUAL_ROW_HEIGHT = 28;
var VIRTUAL_BUFFER = 20;

// Indentation slider state
var _indentSliders = [];  // all slider elements for sync
var _cachedIndentSize = 24;  // cached current indent value in px

// ── Root Cause Classification ──

/**
 * Control flow keyword name patterns (case-insensitive match).
 * A FAIL keyword whose name matches one of these AND has FAIL children
 * is classified as a "wrapper" — it failed only because a child failed.
 */
var CONTROL_FLOW_WRAPPERS = [
  'Run Keyword And Continue On Failure',
  'Run Keyword If',
  'Run Keyword Unless',
  'Run Keyword And Expect Error',
  'Run Keyword And Ignore Error',
  'Run Keyword And Return Status',
  'Wait Until Keyword Succeeds',
  'Repeat Keyword',
  'IF', 'ELSE IF', 'ELSE',
  'TRY', 'EXCEPT', 'FINALLY',
  'FOR', 'WHILE'
];

// Pre-compute lower-cased wrapper names for fast matching
var _wrapperNamesLower = [];
for (var _wi = 0; _wi < CONTROL_FLOW_WRAPPERS.length; _wi++) {
  _wrapperNamesLower.push(CONTROL_FLOW_WRAPPERS[_wi].toLowerCase());
}

/**
 * Classify a FAIL keyword.
 * @param {Object} kw - Keyword data with status, children, name
 * @returns {'root-cause'|'wrapper'|'none'}
 */
function _classifyFailKeyword(kw) {
  var kids = kw.children || [];
  var hasFailChild = false;
  for (var i = 0; i < kids.length; i++) {
    if (kids[i].status === 'FAIL') { hasFailChild = true; break; }
  }
  if (!hasFailChild) return 'root-cause';
  var nameLower = (kw.name || '').toLowerCase();
  for (var j = 0; j < _wrapperNamesLower.length; j++) {
    if (nameLower === _wrapperNamesLower[j]) return 'wrapper';
  }
  return 'none';
}

/**
 * Find all root cause keywords in a test's keyword tree (iterative DFS).
 * @param {Object} test - Test data with keywords array
 * @returns {Array<Object>} Root cause keyword data objects
 */
function _findRootCauseKeywords(test) {
  var results = [];
  var stack = [];
  var kws = test.keywords || [];
  for (var i = kws.length - 1; i >= 0; i--) stack.push(kws[i]);
  while (stack.length > 0) {
    var kw = stack.pop();
    if (kw.status !== 'FAIL') continue;
    var cls = _classifyFailKeyword(kw);
    if (cls === 'root-cause') {
      results.push(kw);
    } else {
      var kids = kw.children || [];
      for (var j = kids.length - 1; j >= 0; j--) stack.push(kids[j]);
    }
  }
  return results;
}

/**
 * Find the span ID path from test to the first root cause keyword (DFS).
 * @param {Object} test - Test data
 * @returns {Array<string>} Span IDs from test to first root cause
 */
function _findRootCausePath(test) {
  var stack = [];
  var kws = test.keywords || [];
  for (var i = kws.length - 1; i >= 0; i--) {
    stack.push({ node: kws[i], path: [test.id] });
  }
  while (stack.length > 0) {
    var item = stack.pop();
    var node = item.node;
    if (node.status !== 'FAIL') continue;
    var currentPath = item.path.concat([node.id]);
    var cls = _classifyFailKeyword(node);
    if (cls === 'root-cause') return currentPath;
    var kids = node.children || [];
    for (var j = kids.length - 1; j >= 0; j--) {
      if (kids[j].status === 'FAIL') {
        stack.push({ node: kids[j], path: currentPath });
        break; // follow first FAIL child only
      }
    }
  }
  return [];
}

/** Get the .rf-trace-viewer element where CSS custom properties are defined. */
function _getIndentTarget() {
  return document.querySelector('.rf-trace-viewer') || document.documentElement;
}

/**
 * Read saved indent size from localStorage and apply to CSS custom property.
 * Called before first render to avoid flash of wrong indentation.
 */
function _initIndentSize() {
  try {
    var saved = localStorage.getItem('rf-trace-indent-size');
    if (saved !== null) {
      var val = parseInt(saved, 10);
      if (val >= 8 && val <= 48) {
        _cachedIndentSize = val;
        _getIndentTarget().style.setProperty('--tree-indent-size', val + 'px');
      }
    }
  } catch (e) {
    // localStorage may be unavailable
  }
}

/**
 * Create an indentation slider control element.
 * @returns {HTMLElement} The control container element
 */
function _createIndentControl() {
  var wrapper = document.createElement('span');
  wrapper.className = 'tree-indent-control';

  var lbl = document.createElement('label');
  lbl.textContent = 'Indent:';

  var slider = document.createElement('input');
  slider.type = 'range';
  slider.min = '8';
  slider.max = '48';
  slider.step = '4';
  slider.value = String(_cachedIndentSize);
  slider.setAttribute('aria-label', 'Tree indentation size');

  var valSpan = document.createElement('span');
  valSpan.className = 'indent-value';
  valSpan.textContent = _cachedIndentSize + 'px';

  slider.addEventListener('input', function () {
    var val = parseInt(slider.value, 10);
    _cachedIndentSize = val;
    _getIndentTarget().style.setProperty('--tree-indent-size', val + 'px');
    valSpan.textContent = val + 'px';
    // Sync all other sliders
    for (var i = 0; i < _indentSliders.length; i++) {
      var entry = _indentSliders[i];
      if (entry.slider !== slider) {
        entry.slider.value = String(val);
        entry.valSpan.textContent = val + 'px';
      }
    }
    try {
      localStorage.setItem('rf-trace-indent-size', String(val));
    } catch (e) {
      // localStorage may be unavailable
    }
  });

  _indentSliders.push({ slider: slider, valSpan: valSpan });

  wrapper.appendChild(lbl);
  wrapper.appendChild(slider);
  wrapper.appendChild(valSpan);
  return wrapper;
}

/**
 * Render the tree view into the given container.
 * @param {HTMLElement} container
 * @param {Object} model - RFRunModel with suites array
 */
function renderTree(container, model) {
  _initIndentSize();
  _originalModel = model;
  _treeContainer = container;
  _currentFilteredSpanIds = null; // null = show all
  
  _renderTreeWithFilter(container, model, null);

  // Set up synchronization with timeline
  setupTreeSynchronization();
  
  // Listen for filter changes
  if (!_filterListenerRegistered && window.RFTraceViewer && window.RFTraceViewer.on) {
    _filterListenerRegistered = true;
    window.RFTraceViewer.on('filter-changed', function (data) {
      var filteredSpanIds = {};
      if (data.filteredSpans) {
        for (var i = 0; i < data.filteredSpans.length; i++) {
          filteredSpanIds[data.filteredSpans[i].id] = true;
        }
      }
      _currentFilteredSpanIds = filteredSpanIds;
      // Use _originalModel (updated on each renderTree call) instead of
      // the closure-captured model which would be stale in live mode
      if (_originalModel && _treeContainer) {
        _renderTreeWithFilter(_treeContainer, _originalModel, filteredSpanIds);
      }
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
  var stack = (model.suites || []).slice();
  while (stack.length > 0) {
    var item = stack.pop();
    count++;
    if (item.children) {
      for (var i = 0; i < item.children.length; i++) {
        stack.push(item.children[i]);
      }
    }
    if (item.keywords) {
      for (var j = 0; j < item.keywords.length; j++) {
        stack.push(item.keywords[j]);
      }
    }
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
  var stack = [item];
  while (stack.length > 0) {
    var cur = stack.pop();
    if (filteredSpanIds[cur.id]) return true;
    if (cur.children) {
      for (var i = 0; i < cur.children.length; i++) {
        stack.push(cur.children[i]);
      }
    }
    if (cur.keywords) {
      for (var j = 0; j < cur.keywords.length; j++) {
        stack.push(cur.keywords[j]);
      }
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
  var stack = [item];
  while (stack.length > 0) {
    var cur = stack.pop();
    if (cur.status === 'FAIL') return true;
    if (cur.children) {
      for (var i = 0; i < cur.children.length; i++) {
        stack.push(cur.children[i]);
      }
    }
    if (cur.keywords) {
      for (var j = 0; j < cur.keywords.length; j++) {
        stack.push(cur.keywords[j]);
      }
    }
  }
  return false;
}

/**
 * Flatten the tree data model into a flat array of row descriptors.
 * Only includes items that pass the filter and whose ancestors are expanded.
 * @param {Array} suites - Merged suite array
 * @param {Object|null} filteredSpanIds - Filter map or null for all
 * @param {Object} expandedIds - Map of expanded node IDs
 * @returns {Array} Flat array of { data, depth, type, maxSiblingDuration, id }
 */
function _flattenTree(suites, filteredSpanIds, expandedIds) {
  var result = [];
  // Use an explicit stack for iterative DFS (avoids recursion)
  // Stack items: { items: Array, index: number, depth: number, type: string, maxSiblingDuration: number }
  var stack = [{ items: suites, index: 0, depth: 0, type: 'suites', maxSiblingDuration: 0 }];

  while (stack.length > 0) {
    var frame = stack[stack.length - 1];
    if (frame.index >= frame.items.length) {
      stack.pop();
      continue;
    }
    var item = frame.items[frame.index];
    frame.index++;

    // Determine item type
    var itemType;
    if (item.keyword_type !== undefined) {
      itemType = 'keyword';
    } else if (item.keywords !== undefined) {
      itemType = 'test';
    } else {
      itemType = 'suite';
    }

    // Filter check: skip if doesn't match and has no matching descendants
    if (filteredSpanIds !== null) {
      var matchesFilter = !!filteredSpanIds[item.id];
      if (!matchesFilter && !_hasDescendantInFilter(item, filteredSpanIds)) {
        continue;
      }
    }

    // Compute maxSiblingDuration for test nodes
    var maxSibDur = 0;
    if (itemType === 'test') {
      maxSibDur = frame.maxSiblingDuration || 0;
    }

    // Build display name for suites with merged workers
    var displayName = item.name;
    if (itemType === 'suite' && item._merged_count && item._merged_count > 1) {
      displayName = item.name + ' (' + item._merged_count + ' workers)';
    }

    // Determine children
    var children = null;
    var hasChildren = false;
    if (itemType === 'suite') {
      children = item.children || [];
      hasChildren = children.length > 0;
    } else if (itemType === 'test') {
      children = item.keywords || [];
      hasChildren = children.length > 0;
    } else {
      children = item.children || [];
      hasChildren = children.length > 0 || (item.truncated && item.truncated > 0);
    }

    result.push({
      data: item,
      depth: frame.depth,
      type: itemType,
      id: item.id,
      displayName: displayName,
      hasChildren: hasChildren,
      maxSiblingDuration: maxSibDur,
      truncatedCount: (itemType === 'keyword' && item.truncated) ? item.truncated : 0,
      rootCauseClass: (itemType === 'keyword' && item.status === 'FAIL') ? _classifyFailKeyword(item) : null
    });

    // If expanded, push children onto stack
    if (hasChildren && expandedIds[item.id] && children.length > 0) {
      // Compute maxSiblingDuration for child tests
      var childMaxDur = 0;
      if (itemType === 'suite') {
        for (var c = 0; c < children.length; c++) {
          var ch = children[c];
          if (ch.keywords !== undefined && ch.elapsed_time > childMaxDur) {
            childMaxDur = ch.elapsed_time;
          }
        }
      }
      stack.push({
        items: children,
        index: 0,
        depth: frame.depth + 1,
        type: itemType,
        maxSiblingDuration: childMaxDur
      });
    }
  }
  return result;
}

/**
 * Compute failure-focused expanded IDs for a single failing test.
 * Walks the keyword tree: expands FAIL nodes, skips PASS/SKIP subtrees.
 * Follows ALL FAIL branches (not just the first).
 *
 * @param {Object} test - Test data object with keywords array, status === 'FAIL'
 * @returns {Object} Map of span IDs to expand (id → true)
 */
function _computeFailFocusedExpanded(test) {
  var expanded = {};
  if (test.status !== 'FAIL') return expanded;
  expanded[test.id] = true;
  var stack = (test.keywords || []).slice();
  while (stack.length > 0) {
    var kw = stack.pop();
    if (kw.status !== 'FAIL') continue;
    expanded[kw.id] = true;
    var kids = kw.children || [];
    for (var i = 0; i < kids.length; i++) {
      stack.push(kids[i]);
    }
  }
  return expanded;
}


/**
 * Compute the initial expanded IDs set based on failure path or root suites.
 * @param {Array} suites - Merged suite array
 * @returns {Object} Map of expanded node IDs
 */
function _computeInitialExpanded(suites) {
  var expandedIds = {};
  var hasFailure = false;

  // Walk suites to find failing tests
  var suiteStack = suites.slice();
  while (suiteStack.length > 0) {
    var suite = suiteStack.pop();
    var children = suite.children || [];
    var suiteHasFail = false;

    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child.keywords !== undefined) {
        // It's a test
        if (child.status === 'FAIL') {
          suiteHasFail = true;
          hasFailure = true;
          var testExpanded = _computeFailFocusedExpanded(child);
          for (var key in testExpanded) {
            expandedIds[key] = true;
          }
        }
      } else {
        // It's a nested suite — push for processing
        suiteStack.push(child);
      }
    }

    // Expand this suite if it has a failing descendant
    if (suiteHasFail || _hasDescendantFail(suite)) {
      expandedIds[suite.id] = true;
    }
  }

  if (!hasFailure) {
    // No failures — expand root suites only (existing behavior)
    for (var j = 0; j < suites.length; j++) {
      if (suites[j].id) expandedIds[suites[j].id] = true;
    }
  }

  return expandedIds;
}

/**
 * Render only the visible rows in the virtual scroll viewport.
 * Clears the content element and creates DOM nodes for visible rows + buffer.
 */
function _renderVisibleRows() {
  var vs = _virtualState;
  if (!vs || !vs.scrollEl || !vs.contentEl) return;

  var scrollTop = vs.scrollEl.scrollTop;
  var viewportHeight = vs.scrollEl.clientHeight;
  // Fallback if container not yet laid out
  if (viewportHeight <= 0) viewportHeight = 800;
  var totalItems = vs.flatItems.length;
  var totalHeight = totalItems * vs.ROW_HEIGHT;

  // Update sentinel height
  if (vs.sentinelEl) {
    vs.sentinelEl.style.height = totalHeight + 'px';
  }

  // Calculate visible range
  var startIdx = Math.floor(scrollTop / vs.ROW_HEIGHT) - vs.BUFFER;
  var endIdx = Math.ceil((scrollTop + viewportHeight) / vs.ROW_HEIGHT) + vs.BUFFER;
  if (startIdx < 0) startIdx = 0;
  if (endIdx > totalItems) endIdx = totalItems;

  // Skip re-render if range hasn't changed
  if (vs.renderedRange.start === startIdx && vs.renderedRange.end === endIdx) {
    return;
  }
  vs.renderedRange.start = startIdx;
  vs.renderedRange.end = endIdx;

  // Clear and rebuild content
  vs.contentEl.innerHTML = '';
  vs.contentEl.style.position = 'absolute';
  vs.contentEl.style.top = (startIdx * vs.ROW_HEIGHT) + 'px';
  vs.contentEl.style.left = '0';
  vs.contentEl.style.right = '0';

  var fragment = document.createDocumentFragment();
  for (var i = startIdx; i < endIdx; i++) {
    var item = vs.flatItems[i];
    var rowEl = _createVirtualRow(item, i);
    fragment.appendChild(rowEl);
  }
  vs.contentEl.appendChild(fragment);
}

/**
 * Create a DOM element for a single virtual row.
 * Uses _createTreeNode but strips children container (children are separate flat items).
 * @param {Object} item - Flat item descriptor
 * @param {number} index - Index in flatItems array
 * @returns {HTMLElement}
 */
function _createVirtualRow(item, index) {
  var vs = _virtualState;
  var isExpanded = !!vs.expandedIds[item.id];

  var node = _createTreeNode({
    type: item.type,
    name: item.displayName,
    status: item.data.status,
    elapsed: item.data.elapsed_time,
    hasChildren: item.hasChildren,
    depth: item.depth,
    id: item.id,
    data: item.data,
    kwType: item.data.keyword_type,
    kwArgs: item.data.args,
    maxSiblingDuration: item.maxSiblingDuration || 0
  });

  // Apply wrapper de-emphasis in virtual mode
  if (item.rootCauseClass === 'wrapper') {
    var vRow = node.querySelector(':scope > .tree-row');
    if (vRow) vRow.classList.add('kw-wrapper');
  }

  // Set fixed height for consistent virtual scrolling
  node.style.height = vs.ROW_HEIGHT + 'px';
  node.style.overflow = 'hidden';
  node.style.boxSizing = 'border-box';

  // Override toggle behavior for virtual mode
  var toggleBtn = node.querySelector(':scope > .tree-row > .tree-toggle');
  var row = node.querySelector(':scope > .tree-row');

  // Remove the children container — in virtual mode children are separate flat items
  var childrenEl = node.querySelector(':scope > .tree-children');
  if (childrenEl) {
    node.removeChild(childrenEl);
  }

  // Remove the detail panel — we handle expand differently in virtual mode
  var detailEl = node.querySelector(':scope > .detail-panel');
  if (detailEl) {
    node.removeChild(detailEl);
  }

  // Set expanded visual state on toggle button
  if (isExpanded && toggleBtn) {
    toggleBtn.textContent = '\u25bc'; // ▼
    toggleBtn.setAttribute('aria-label', 'Collapse');
  }

  // Highlight if this is the highlighted span
  if (vs.highlightedSpanId && item.id === vs.highlightedSpanId) {
    node.classList.add('highlighted');
  }

  // Replace click handlers with virtual toggle
  // Clone row to remove old listeners, then add new ones
  var newRow = row.cloneNode(true);
  node.replaceChild(newRow, row);

  // Re-get toggle button from cloned row
  var newToggle = newRow.querySelector(':scope > .tree-toggle');

  // Add virtual toggle handler to toggle button
  if (newToggle) {
    newToggle.addEventListener('click', function (e) {
      e.stopPropagation();
      // Emit navigate-to-span BEFORE toggle (toggle rebuilds DOM)
      if (item.id && window.RFTraceViewer && window.RFTraceViewer.emit) {
        window.RFTraceViewer.emit('navigate-to-span', { spanId: item.id, source: 'tree' });
      }
      _virtualToggle(item.id);
    });
  }

  // Add click handler to row for toggle + navigate
  newRow.addEventListener('click', function () {
    // Emit navigate-to-span BEFORE toggle (toggle rebuilds DOM)
    if (item.id && window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('navigate-to-span', { spanId: item.id, source: 'tree' });
    }
    _virtualToggle(item.id);
  });

  return node;
}

/**
 * Toggle expand/collapse for a node in virtual mode.
 * Rebuilds the flat list and re-renders visible rows.
 * @param {string} nodeId - The span ID to toggle
 */
function _virtualToggle(nodeId) {
  var vs = _virtualState;
  if (!vs) return;

  if (vs.expandedIds[nodeId]) {
    delete vs.expandedIds[nodeId];
  } else {
    vs.expandedIds[nodeId] = true;
  }

  // Rebuild flat list
  vs.flatItems = _flattenTree(vs.mergedSuites, vs.filteredSpanIds, vs.expandedIds);

  // Force re-render by resetting rendered range
  vs.renderedRange.start = -1;
  vs.renderedRange.end = -1;
  _renderVisibleRows();
}

/**
 * Find the index of a span ID in the flat items list.
 * @param {string} spanId
 * @returns {number} Index or -1 if not found
 */
function _findFlatIndex(spanId) {
  var vs = _virtualState;
  if (!vs) return -1;
  for (var i = 0; i < vs.flatItems.length; i++) {
    if (vs.flatItems[i].id === spanId) return i;
  }
  return -1;
}

/**
 * Expand ancestors of a target span in virtual mode.
 * Walks the data model to find the ancestor path, adds all to expandedIds.
 * @param {string} targetId - The span ID to reveal
 */
function _virtualExpandAncestors(targetId) {
  var vs = _virtualState;
  if (!vs) return;

  // Use merged model for ancestor path (flat list is built from merged suites)
  var mergedModel = { suites: vs.mergedSuites };
  var ancestorPath = _findAncestorPath(mergedModel, targetId);
  if (ancestorPath) {
    for (var i = 0; i < ancestorPath.length; i++) {
      vs.expandedIds[ancestorPath[i]] = true;
    }
  }
  // Rebuild flat list
  vs.flatItems = _flattenTree(vs.mergedSuites, vs.filteredSpanIds, vs.expandedIds);
}

function _renderTreeWithFilter(container, model, filteredSpanIds) {
  var t0 = Date.now();
  var spanCount = _countSpans(model);

  // For large trees, use virtual scrolling
  if (spanCount > VIRTUAL_THRESHOLD) {
    _renderTreeVirtual(container, model, filteredSpanIds);
    var elapsed = Date.now() - t0;
    console.log('[Tree] Rendered ' + spanCount + ' spans in ' + elapsed + 'ms (virtual scrolling)');
    return;
  }

  // Original path for small trees
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
  controls.appendChild(_createIndentControl());
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

  var elapsed2 = Date.now() - t0;
  console.log('[Tree] Rendered ' + spanCount + ' spans in ' + elapsed2 + 'ms (lazy children enabled)');
}

/**
 * Render the tree using virtual scrolling for large traces.
 * Only creates DOM nodes for visible rows + buffer.
 * @param {HTMLElement} container
 * @param {Object} model
 * @param {Object|null} filteredSpanIds
 */
function _renderTreeVirtual(container, model, filteredSpanIds) {
  var mergedSuites = _mergeSameNameSuites(model.suites || []);

  // Determine if this is a re-render (filter change) or first render
  var isReRender = _virtualState && _virtualState.container === container;

  if (!isReRender) {
    // First render — set up DOM structure
    container.innerHTML = '';

    // Controls bar
    var controls = document.createElement('div');
    controls.className = 'tree-controls';

    var expandBtn = document.createElement('button');
    expandBtn.textContent = 'Expand All';
    expandBtn.addEventListener('click', function () { _virtualSetAllExpanded(true); });

    var collapseBtn = document.createElement('button');
    collapseBtn.textContent = 'Collapse All';
    collapseBtn.addEventListener('click', function () { _virtualSetAllExpanded(false); });

    var failuresBtn = document.createElement('button');
    failuresBtn.textContent = 'Failures Only';
    failuresBtn.className = 'failures-only-toggle' + (_failuresOnlyActive ? ' active' : '');
    failuresBtn.setAttribute('aria-pressed', _failuresOnlyActive ? 'true' : 'false');
    failuresBtn.title = _failuresOnlyActive ? 'Show all test results' : 'Show only failing tests';
    failuresBtn.addEventListener('click', function () {
      _failuresOnlyActive = !_failuresOnlyActive;
      if (_failuresOnlyActive) {
        if (typeof window.setFilterState === 'function') {
          window.setFilterState({ testStatuses: ['FAIL'] });
        }
        _syncStatusCheckboxes(['FAIL']);
      } else {
        if (typeof window.setFilterState === 'function') {
          window.setFilterState({ testStatuses: ['PASS', 'FAIL', 'SKIP'] });
        }
        _syncStatusCheckboxes(['PASS', 'FAIL', 'SKIP']);
      }
    });

    controls.appendChild(expandBtn);
    controls.appendChild(collapseBtn);
    controls.appendChild(failuresBtn);
    controls.appendChild(_createIndentControl());
    container.appendChild(controls);

    // Scroll viewport — this is the tree-root equivalent
    var scrollEl = document.createElement('div');
    scrollEl.className = 'tree-root tree-virtual-scroll';
    scrollEl.style.position = 'relative';

    // Sentinel for total height (normal flow, sets scrollbar range on panel-tree)
    var sentinelEl = document.createElement('div');
    sentinelEl.className = 'tree-virtual-sentinel';
    sentinelEl.style.width = '100%';
    sentinelEl.style.pointerEvents = 'none';
    scrollEl.appendChild(sentinelEl);

    // Content container for visible rows (positioned over sentinel)
    var contentEl = document.createElement('div');
    contentEl.className = 'tree-virtual-content';
    contentEl.style.position = 'absolute';
    contentEl.style.top = '0';
    contentEl.style.left = '0';
    contentEl.style.right = '0';
    scrollEl.appendChild(contentEl);

    container.appendChild(scrollEl);

    // Compute initial expanded state
    var expandedIds = _computeInitialExpanded(mergedSuites);

    // Initialize virtual state
    _virtualState = {
      flatItems: [],
      expandedIds: expandedIds,
      container: container,
      scrollEl: container,  // panel-tree is the scroll container (has overflow-y: auto)
      contentEl: contentEl,
      sentinelEl: sentinelEl,
      controlsEl: controls,
      model: model,
      filteredSpanIds: filteredSpanIds,
      mergedSuites: mergedSuites,
      ROW_HEIGHT: VIRTUAL_ROW_HEIGHT,
      BUFFER: VIRTUAL_BUFFER,
      renderedRange: { start: -1, end: -1 },
      highlightedSpanId: null,
      scrollViewEl: scrollEl
    };

    // Attach scroll listener to the panel-tree container
    var scrollHandler = function () {
      requestAnimationFrame(function () {
        _renderVisibleRows();
      });
    };
    container.addEventListener('scroll', scrollHandler);
    _virtualState._scrollHandler = scrollHandler;
  } else {
    // Re-render (filter change) — update state, keep DOM structure
    _virtualState.filteredSpanIds = filteredSpanIds;
    _virtualState.mergedSuites = mergedSuites;
    _virtualState.model = model;

    // Update failures button state
    var existingFailBtn = container.querySelector('.failures-only-toggle');
    if (existingFailBtn) {
      existingFailBtn.className = 'failures-only-toggle' + (_failuresOnlyActive ? ' active' : '');
      existingFailBtn.setAttribute('aria-pressed', _failuresOnlyActive ? 'true' : 'false');
      existingFailBtn.title = _failuresOnlyActive ? 'Show all test results' : 'Show only failing tests';
    }
  }

  // Build flat list and render
  _virtualState.flatItems = _flattenTree(mergedSuites, filteredSpanIds, _virtualState.expandedIds);
  _virtualState.renderedRange.start = -1;
  _virtualState.renderedRange.end = -1;
  _renderVisibleRows();
}

/**
 * Expand or collapse all nodes in virtual mode.
 * @param {boolean} expand - true to expand all, false to collapse all
 */
function _virtualSetAllExpanded(expand) {
  var vs = _virtualState;
  if (!vs) return;

  if (expand) {
    // Add ALL node IDs to expandedIds by walking the data model
    var stack = (vs.mergedSuites || []).slice();
    while (stack.length > 0) {
      var item = stack.pop();
      if (item.id) {
        vs.expandedIds[item.id] = true;
      }
      if (item.children) {
        for (var i = 0; i < item.children.length; i++) {
          stack.push(item.children[i]);
        }
      }
      if (item.keywords) {
        for (var j = 0; j < item.keywords.length; j++) {
          stack.push(item.keywords[j]);
        }
      }
    }
  } else {
    // Collapse all — clear expandedIds
    vs.expandedIds = {};
  }

  // Rebuild and re-render
  vs.flatItems = _flattenTree(vs.mergedSuites, vs.filteredSpanIds, vs.expandedIds);
  vs.renderedRange.start = -1;
  vs.renderedRange.end = -1;
  _renderVisibleRows();
}

/**
 * Find the first failure path through the DATA model.
 * Returns an array of span IDs from root to the first FAIL leaf.
 * @param {Array} suites - Array of suite data objects
 * @returns {Array} Array of span IDs forming the failure path, or empty array
 */
function _findFirstFailPath(suites) {
  // Iterative DFS to find the first FAIL path from root to deepest failing node.
  // Each stack item: { node, path }
  var stack = [];
  for (var i = suites.length - 1; i >= 0; i--) {
    stack.push({ node: suites[i], path: [] });
  }
  while (stack.length > 0) {
    var item = stack.pop();
    var node = item.node;
    var path = item.path;
    if (node.status !== 'FAIL') continue;
    var currentPath = path.concat([node.id]);
    // Try to go deeper into children/keywords
    var kids = node.children || node.keywords || [];
    var pushed = false;
    for (var j = 0; j < kids.length; j++) {
      if (kids[j].status === 'FAIL') {
        stack.push({ node: kids[j], path: currentPath });
        pushed = true;
        break; // only follow the first failing child
      }
    }
    if (!pushed) {
      // This is the deepest failing node on this path
      return currentPath;
    }
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
  var expandSet = _computeInitialExpanded(suites);
  var ids = Object.keys(expandSet);

  if (ids.length === 0) {
    // No failures — expand root suites only (original behavior)
    var rootNodes = treeRoot.querySelectorAll(':scope > .tree-node.depth-0');
    for (var j = 0; j < rootNodes.length; j++) {
      _materializeIfNeeded(rootNodes[j]);
      _expandNodeOnly(rootNodes[j]);
    }
    return;
  }

  // Materialize and expand each node in the expand set
  for (var i = 0; i < ids.length; i++) {
    var node = treeRoot.querySelector('.tree-node[data-span-id="' + ids[i] + '"]');
    if (!node) continue;
    _materializeIfNeeded(node);
    _expandNodeOnly(node);
  }

  // Find the first root cause keyword to scroll to.
  // Walk suites to find the first FAIL test, then get its root cause keywords.
  var scrollTarget = null;
  var suiteStack = suites.slice();
  while (suiteStack.length > 0 && !scrollTarget) {
    var suite = suiteStack.shift();
    var children = suite.children || [];
    for (var c = 0; c < children.length; c++) {
      var child = children[c];
      if (child.keywords !== undefined) {
        // It's a test
        if (child.status === 'FAIL') {
          var rootCauses = _findRootCauseKeywords(child);
          if (rootCauses.length > 0) {
            scrollTarget = treeRoot.querySelector(
              '.tree-node[data-span-id="' + rootCauses[0].id + '"]'
            );
          }
          if (!scrollTarget) {
            // Fallback: scroll to the test node itself
            scrollTarget = treeRoot.querySelector(
              '.tree-node[data-span-id="' + child.id + '"]'
            );
          }
          break;
        }
      } else {
        // Nested suite
        suiteStack.push(child);
      }
    }
  }

  // Scroll the target node into view after the DOM settles
  if (scrollTarget) {
    requestAnimationFrame(function () {
      var treePanel = scrollTarget.closest('.panel-tree');
      if (treePanel) {
        var panelRect = treePanel.getBoundingClientRect();
        var nodeRect = scrollTarget.getBoundingClientRect();
        var scrollOffset = nodeRect.top - panelRect.top - panelRect.height / 3 + nodeRect.height / 2;
        treePanel.scrollBy({ top: scrollOffset, behavior: 'smooth' });
      } else {
        scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
    if (lazy.truncatedCount > 0) {
      var truncEl = document.createElement('div');
      truncEl.className = 'tree-truncated-indicator';
      truncEl.style.paddingLeft = (lazy.depth * _cachedIndentSize + 24) + 'px';
      truncEl.textContent = '\u2026 ' + lazy.truncatedCount + ' keyword' + (lazy.truncatedCount === 1 ? '' : 's') + ' hidden';
      fragment.appendChild(truncEl);
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

  var hasChildren = (kw.children && kw.children.length > 0) || kw.truncated > 0;

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

  // Apply wrapper de-emphasis for FAIL keywords classified as wrappers
  if (kw.status === 'FAIL') {
    var kwClass = _classifyFailKeyword(kw);
    if (kwClass === 'wrapper') {
      var kwRow = node.querySelector(':scope > .tree-row');
      if (kwRow) kwRow.classList.add('kw-wrapper');
    }
  }

  // Store lazy children data instead of rendering them now
  if (hasChildren) {
    node._lazyChildren = {
      items: kw.children || [],
      type: 'keyword',
      filteredSpanIds: filteredSpanIds,
      depth: depth + 1,
      truncatedCount: kw.truncated || 0
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
  if (data.execution_id) {
    _addBadgeRow(panel, 'Execution ID', data.execution_id);
  }
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
  if (data.execution_id) {
    _addBadgeRow(panel, 'Execution ID', data.execution_id);
  }
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
  // Root cause summary section
  if (data.status === 'FAIL') {
    var rootCauses = _findRootCauseKeywords(data);
    if (rootCauses.length > 0) {
      var summary = document.createElement('div');
      summary.className = 'root-cause-summary';
      var title = document.createElement('div');
      title.className = 'root-cause-summary-title';
      title.textContent = 'Root Cause' + (rootCauses.length > 1 ? 's (' + rootCauses.length + ')' : '');
      summary.appendChild(title);
      for (var ri = 0; ri < rootCauses.length; ri++) {
        (function (rc) {
          var entry = document.createElement('div');
          entry.className = 'root-cause-entry';
          var nameSpan = document.createElement('div');
          nameSpan.className = 'root-cause-entry-name';
          nameSpan.textContent = rc.name;
          entry.appendChild(nameSpan);
          if (rc.status_message) {
            var msgSpan = document.createElement('div');
            msgSpan.className = 'root-cause-entry-msg';
            msgSpan.textContent = rc.status_message;
            entry.appendChild(msgSpan);
          }
          entry.addEventListener('click', function () {
            if (rc.id) highlightNodeInTree(rc.id);
          });
          summary.appendChild(entry);
        })(rootCauses[ri]);
      }
      panel.appendChild(summary);
    }
  }
}

/**
 * Create toggle pill buttons for keyword detail panel fields.
 * Reads/writes visibility state from localStorage key 'rf-trace-detail-fields'.
 * @param {HTMLElement} panel - The detail panel element to prepend pills into.
 */
function _createFieldTogglePills(panel) {
  var STORAGE_KEY = 'rf-trace-detail-fields';
  var FIELDS = ['args', 'doc', 'events', 'source'];

  // Read persisted state, falling back to all-visible defaults
  var state = { args: true, doc: true, events: true, source: true };
  try {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        for (var i = 0; i < FIELDS.length; i++) {
          var f = FIELDS[i];
          if (typeof parsed[f] === 'boolean') {
            state[f] = parsed[f];
          }
        }
      }
    }
  } catch (e) {
    // Invalid JSON or localStorage unavailable — use defaults
  }

  var container = document.createElement('div');
  container.className = 'detail-field-pills';

  FIELDS.forEach(function (field) {
    var pill = document.createElement('button');
    pill.className = 'detail-field-pill' + (state[field] ? ' active' : '');
    pill.textContent = field;
    pill.setAttribute('data-toggle-field', field);

    pill.addEventListener('click', function () {
      state[field] = !state[field];

      // Update pill appearance
      if (state[field]) {
        pill.classList.add('active');
      } else {
        pill.classList.remove('active');
      }

      // Toggle matching data-field containers within the panel
      var targets = panel.querySelectorAll('[data-field="' + field + '"]');
      for (var j = 0; j < targets.length; j++) {
        targets[j].style.display = state[field] ? '' : 'none';
      }

      // Persist to localStorage
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      } catch (e) {
        // Storage full or unavailable — silently ignore
      }
    });

    container.appendChild(pill);
  });

  // Prepend pill bar to the panel
  if (panel.firstChild) {
    panel.insertBefore(container, panel.firstChild);
  } else {
    panel.appendChild(container);
  }

  // Apply initial visibility to data-field containers
  FIELDS.forEach(function (field) {
    var targets = panel.querySelectorAll('[data-field="' + field + '"]');
    for (var j = 0; j < targets.length; j++) {
      targets[j].style.display = state[field] ? '' : 'none';
    }
  });
}


/** Render keyword-specific detail rows. */
function _renderKeywordDetail(panel, data) {
  if (data.keyword_type) {
    _addBadgeRow(panel, 'Type', data.keyword_type);
  }
  // Root cause / wrapper classification badge
  if (data.status === 'FAIL') {
    var kwCls = _classifyFailKeyword(data);
    if (kwCls === 'root-cause') {
      var rcBadge = document.createElement('span');
      rcBadge.className = 'root-cause-badge';
      rcBadge.textContent = 'Root Cause';
      panel.appendChild(rcBadge);
    } else if (kwCls === 'wrapper') {
      var wBadge = document.createElement('span');
      wBadge.className = 'wrapper-badge';
      wBadge.textContent = 'Wrapper';
      panel.appendChild(wBadge);
    }
  }
  if (data.library) {
    _addBadgeRow(panel, 'Library', data.library);
  }
  if (data.suite_name) {
    _addDetailRow(panel, 'Suite', data.suite_name);
  }
  if (data.suite_source) {
    _addDetailRow(panel, 'Source File', data.suite_source);
  }
  if (data.args) {
    var argsWrap = document.createElement('div');
    argsWrap.setAttribute('data-field', 'args');
    _addDetailRow(argsWrap, 'Arguments', data.args);
    panel.appendChild(argsWrap);
  }
  if (data.doc) {
    var docWrap = document.createElement('div');
    docWrap.setAttribute('data-field', 'doc');
    _addDetailRow(docWrap, 'Documentation', data.doc);
    panel.appendChild(docWrap);
  }
  if (data.lineno && data.lineno > 0) {
    var sourceText = data.source ? data.source + ':' + data.lineno : 'Line ' + data.lineno;
    var sourceWrap = document.createElement('div');
    sourceWrap.setAttribute('data-field', 'source');
    _addDetailRow(sourceWrap, 'Source', sourceText);
    panel.appendChild(sourceWrap);
  }
  _addCompactInfoBar(panel, data);
  if (data.status === 'FAIL' && data.status_message) {
    _addErrorBlock(panel, data.status_message);
  }
  if (data.events && data.events.length > 0) {
    var eventsWrap = document.createElement('div');
    eventsWrap.setAttribute('data-field', 'events');
    _renderEventsSection(eventsWrap, data.events);
    panel.appendChild(eventsWrap);
  }
  _createFieldTogglePills(panel);
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

  // Setup/teardown visual distinction
  if (opts.kwType === 'SETUP') {
    row.classList.add('kw-setup');
  } else if (opts.kwType === 'TEARDOWN') {
    row.classList.add('kw-teardown');
  }

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

  // Library prefix (e.g. "BuiltIn . Set Variable")
  if (opts.data && opts.data.library) {
    var libSpan = document.createElement('span');
    libSpan.className = 'kw-library';
    libSpan.textContent = opts.data.library;
    nameEl.appendChild(libSpan);
  }

  nameEl.appendChild(document.createTextNode(opts.name));

  // Keyword args inline
  if (opts.kwArgs) {
    var argsEl = document.createElement('span');
    argsEl.className = 'kw-args';
    argsEl.textContent = opts.kwArgs;
    nameEl.appendChild(argsEl);
  }

  // Execution ID badge (for suites and tests)
  if (opts.data && opts.data.execution_id) {
    var execBadge = document.createElement('span');
    execBadge.className = 'exec-id-badge';
    execBadge.textContent = opts.data.execution_id;
    execBadge.title = 'Execution ID: ' + opts.data.execution_id;
    nameEl.appendChild(execBadge);
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
    // For test nodes, bubble up the first root cause error message
    var snippetMsg = opts.data.status_message;
    if (opts.type === 'test') {
      var rootCauses = _findRootCauseKeywords(opts.data);
      if (rootCauses.length > 0 && rootCauses[0].status_message) {
        snippetMsg = rootCauses[0].status_message;
      }
    }
    var truncated = snippetMsg;
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

  // Failure-focused expand when clicking a FAIL test node
  if (opts.type === 'test' && opts.status === 'FAIL') {
    row.addEventListener('click', function () {
      // Only apply when toggling OPEN (not when collapsing)
      var childrenEl = wrapper.querySelector(':scope > .tree-children');
      if (!childrenEl || !childrenEl.classList.contains('expanded')) return;

      // Compute the set of FAIL-path node IDs to expand
      var failExpanded = _computeFailFocusedExpanded(opts.data);

      // Materialize the test's immediate children first
      _materializeIfNeeded(wrapper);

      // Walk the test's subtree: expand FAIL path nodes, collapse PASS/SKIP siblings
      var queue = [];
      var directChildren = childrenEl.querySelectorAll(':scope > .tree-node');
      for (var ci = 0; ci < directChildren.length; ci++) {
        queue.push(directChildren[ci]);
      }

      while (queue.length > 0) {
        var node = queue.shift();
        var nodeId = node.getAttribute('data-span-id');
        if (!nodeId) continue;

        if (failExpanded[nodeId]) {
          // This node is on the FAIL path — materialize and expand
          _materializeIfNeeded(node);
          _expandNodeOnly(node);
          var nodeChildren = node.querySelector(':scope > .tree-children');
          if (nodeChildren) {
            nodeChildren.classList.add('expanded');
            // Queue this node's children for processing
            var nested = nodeChildren.querySelectorAll(':scope > .tree-node');
            for (var ni = 0; ni < nested.length; ni++) {
              queue.push(nested[ni]);
            }
          }
        } else {
          // PASS/SKIP node — collapse it
          var collapseChildren = node.querySelector(':scope > .tree-children');
          var collapseToggle = node.querySelector(':scope > .tree-row > .tree-toggle');
          if (collapseChildren) collapseChildren.classList.remove('expanded');
          if (collapseToggle) {
            collapseToggle.textContent = '\u25b6'; // ▶
            collapseToggle.setAttribute('aria-label', 'Expand');
          }
        }
      }
    });
  }

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
  // If in virtual mode, delegate to virtual handler
  if (_virtualState) {
    _virtualSetAllExpanded(expand);
    return;
  }

  // Original mode — DOM-based expand/collapse
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
  // Virtual mode handling
  if (_virtualState) {
    _virtualHighlight(spanId);
    return;
  }

  // Original mode — DOM-based highlighting
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

  if (!targetNode) {
    // Span not in tree model (e.g., truncated keywords) — try nearest ancestor
    var fallbackId = _findNearestTreeAncestor(spanId);
    if (fallbackId) {
      var fallbackAncestors = _findAncestorPath(_originalModel, fallbackId);
      if (fallbackAncestors) {
        for (var fa = 0; fa < fallbackAncestors.length; fa++) {
          var faNode = document.querySelector('.tree-node[data-span-id="' + fallbackAncestors[fa] + '"]');
          if (faNode) {
            _materializeIfNeeded(faNode);
            _expandNodeOnly(faNode);
            var faChEl = faNode.querySelector(':scope > .tree-children');
            if (faChEl) faChEl.classList.add('expanded');
          }
        }
      }
      targetNode = document.querySelector('.tree-node[data-span-id="' + fallbackId + '"]');
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
 * Find the nearest ancestor of a span that exists in the tree model.
 * Uses the timeline's flatSpans parent chain to walk up from the target.
 * Falls back when the target span is in a truncated subtree.
 * @param {string} spanId - The span ID to find an ancestor for
 * @returns {string|null} The ID of the nearest ancestor in the tree, or null
 */
function _findNearestTreeAncestor(spanId) {
  // Use timeline's flatSpans to walk up the parent chain
  var ts = window.timelineState;
  if (!ts || !ts.flatSpans) return null;

  // Find the span in flatSpans
  var span = null;
  for (var i = 0; i < ts.flatSpans.length; i++) {
    if (ts.flatSpans[i].id === spanId) {
      span = ts.flatSpans[i];
      break;
    }
  }
  if (!span) return null;

  // Determine which model to search (merged if virtual, original otherwise)
  var searchModel = _virtualState
    ? { suites: _virtualState.mergedSuites }
    : _originalModel;
  if (!searchModel) return null;

  // Walk up parent chain, checking if each ancestor is in the tree model
  var current = span.parent;
  while (current) {
    var path = _findAncestorPath(searchModel, current.id);
    if (path !== null) {
      return current.id;
    }
    // Also check if it's a root suite
    var suites = searchModel.suites || [];
    for (var s = 0; s < suites.length; s++) {
      if (suites[s].id === current.id) return current.id;
    }
    current = current.parent;
  }
  return null;
}

/**
 * Highlight a span in virtual mode by expanding ancestors and scrolling to it.
 * @param {string} spanId
 */
function _virtualHighlight(spanId) {
  var vs = _virtualState;
  if (!vs) return;

  // Clear previous highlight
  vs.highlightedSpanId = spanId;

  // Find the item in flat list
  var idx = _findFlatIndex(spanId);

  // If not found, expand ancestors and rebuild
  if (idx < 0) {
    _virtualExpandAncestors(spanId);
    idx = _findFlatIndex(spanId);
  }

  // If still not found, try to find via timeline parent chain
  if (idx < 0) {
    var fallbackId = _findNearestTreeAncestor(spanId);
    if (fallbackId) {
      _virtualExpandAncestors(fallbackId);
      idx = _findFlatIndex(fallbackId);
      if (idx >= 0) {
        vs.highlightedSpanId = fallbackId;
      }
    }
  }

  if (idx < 0) {
    // Can't find span or any ancestor — just re-render current view
    vs.renderedRange.start = -1;
    vs.renderedRange.end = -1;
    _renderVisibleRows();
    return;
  }

  // Scroll to the item
  var scrollTarget = idx * vs.ROW_HEIGHT;
  var viewportH = vs.scrollEl.clientHeight;
  if (viewportH <= 0) viewportH = 800;
  vs.scrollEl.scrollTop = Math.max(0, scrollTarget - viewportH / 2);

  // Force re-render at the new scroll position
  vs.renderedRange.start = -1;
  vs.renderedRange.end = -1;
  _renderVisibleRows();
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
