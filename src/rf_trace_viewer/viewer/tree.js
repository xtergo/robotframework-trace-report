/* RF Trace Viewer — Expandable Tree View Renderer */

/**
 * Render the tree view into the given container.
 * @param {HTMLElement} container
 * @param {Object} model - RFRunModel with suites array
 */
function renderTree(container, model) {
  console.log('renderTree called with container:', container, 'model:', model);
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
  var suites = model.suites || [];
  console.log('Rendering', suites.length, 'suites');
  for (var i = 0; i < suites.length; i++) {
    console.log('Rendering suite', i, ':', suites[i].name);
    treeRoot.appendChild(_renderSuiteNode(suites[i], 0));
  }
  container.appendChild(treeRoot);
  console.log('Tree root appended, innerHTML length:', container.innerHTML.length);

  // Set up synchronization with timeline
  setupTreeSynchronization();
}

/** Render a suite node and its children recursively. */
function _renderSuiteNode(suite, depth) {
  var hasChildren = suite.children && suite.children.length > 0;
  var node = _createTreeNode({
    type: 'suite',
    name: suite.name,
    status: suite.status,
    elapsed: suite.elapsed_time,
    hasChildren: hasChildren,
    depth: depth,
    id: suite.id
  });

  if (hasChildren) {
    var childrenEl = node.querySelector('.tree-children');
    for (var i = 0; i < suite.children.length; i++) {
      var child = suite.children[i];
      if (child.keywords !== undefined) {
        // It's a test
        childrenEl.appendChild(_renderTestNode(child, depth + 1));
      } else {
        // It's a nested suite
        childrenEl.appendChild(_renderSuiteNode(child, depth + 1));
      }
    }
  }
  return node;
}

/** Render a test node and its keywords. */
function _renderTestNode(test, depth) {
  var hasKws = test.keywords && test.keywords.length > 0;
  var node = _createTreeNode({
    type: 'test',
    name: test.name,
    status: test.status,
    elapsed: test.elapsed_time,
    hasChildren: hasKws,
    depth: depth,
    id: test.id
  });

  if (hasKws) {
    var childrenEl = node.querySelector('.tree-children');
    for (var i = 0; i < test.keywords.length; i++) {
      childrenEl.appendChild(_renderKeywordNode(test.keywords[i], depth + 1));
    }
  }
  return node;
}

/** Render a keyword node and its nested keywords. */
function _renderKeywordNode(kw, depth) {
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
    id: kw.id
  });

  // Error message for failed keywords
  if (kw.status === 'FAIL' && kw.args) {
    // We show error inline; the status message is typically in the span events
    // but for the model we rely on status + args display
  }

  if (hasChildren) {
    var childrenEl = node.querySelector('.tree-children');
    for (var i = 0; i < kw.children.length; i++) {
      childrenEl.appendChild(_renderKeywordNode(kw.children[i], depth + 1));
    }
  }
  return node;
}

/**
 * Create a single tree node DOM element.
 * @param {Object} opts - { type, name, status, elapsed, hasChildren, depth, kwType?, kwArgs?, id? }
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
  toggle.setAttribute('aria-label', opts.hasChildren ? 'Expand' : '');
  if (opts.hasChildren) {
    toggle.textContent = '\u25b6'; // ▶
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      _toggleNode(wrapper);
    });
  }
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

  // Click row to toggle
  if (opts.hasChildren) {
    row.addEventListener('click', function () { _toggleNode(wrapper); });
  }

  // Emit event when node is clicked (for timeline synchronization)
  row.addEventListener('click', function (e) {
    if (opts.id && window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('span-selected', { spanId: opts.id, source: 'tree' });
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
  var toggleBtn = nodeEl.querySelector(':scope > .tree-row > .tree-toggle');
  if (!childrenEl) return;

  var isExpanded = childrenEl.classList.contains('expanded');
  if (isExpanded) {
    childrenEl.classList.remove('expanded');
    toggleBtn.textContent = '\u25b6'; // ▶
    toggleBtn.setAttribute('aria-label', 'Expand');
  } else {
    childrenEl.classList.add('expanded');
    toggleBtn.textContent = '\u25bc'; // ▼
    toggleBtn.setAttribute('aria-label', 'Collapse');
  }
}

/** Expand or collapse all nodes in the tree. */
function _setAllExpanded(container, expand) {
  var childrenEls = container.querySelectorAll('.tree-children');
  var toggleBtns = container.querySelectorAll('.tree-toggle');

  for (var i = 0; i < childrenEls.length; i++) {
    if (expand) {
      childrenEls[i].classList.add('expanded');
    } else {
      childrenEls[i].classList.remove('expanded');
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
      // Update the toggle button
      var parentNode = parent.parentElement;
      if (parentNode && parentNode.classList.contains('tree-node')) {
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
