/* Date Range Picker — uses Flatpickr v4.6.13 (MIT license)
   See THIRD_PARTY_LICENSES for full license text. */

(function () {
  'use strict';

  var ns = window.RFTraceViewer = window.RFTraceViewer || {};

  /* ── Preset configuration ──────────────────────────────────────── */

  var PICKER_PRESETS = [
    { key: 'last-15m',  label: 'Last 15 min',   seconds: 900 },
    { key: 'last-1h',   label: 'Last 1 hour',   seconds: 3600 },
    { key: 'last-6h',   label: 'Last 6 hours',  seconds: 21600 },
    { key: 'last-24h',  label: 'Last 24 hours',  seconds: 86400 },
    { key: 'today',     label: 'Today',          seconds: null, compute: 'today' },
    { key: 'this-week', label: 'This week',      seconds: null, compute: 'this-week' }
  ];

  /* ── Pure-logic helper functions ───────────────────────────────── */

  var MONTHS_SHORT = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
  ];

  /**
   * Zero-pad a number to two digits.
   */
  function _pad2(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  /**
   * Format epoch seconds to "YYYY-MM-DD HH:MM:SS" in local timezone.
   */
  function formatEpochToEntry(epochSec) {
    var d = new Date(epochSec * 1000);
    return d.getFullYear() + '-' +
      _pad2(d.getMonth() + 1) + '-' +
      _pad2(d.getDate()) + ' ' +
      _pad2(d.getHours()) + ':' +
      _pad2(d.getMinutes()) + ':' +
      _pad2(d.getSeconds());
  }

  /**
   * Parse "YYYY-MM-DD HH:MM:SS" string to epoch seconds, or null if invalid.
   */
  function parseEntryToEpoch(str) {
    if (typeof str !== 'string') return null;
    var m = str.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/);
    if (!m) return null;
    var year  = parseInt(m[1], 10);
    var month = parseInt(m[2], 10);
    var day   = parseInt(m[3], 10);
    var hour  = parseInt(m[4], 10);
    var min   = parseInt(m[5], 10);
    var sec   = parseInt(m[6], 10);
    // Validate ranges
    if (month < 1 || month > 12) return null;
    if (day < 1 || day > 31) return null;
    if (hour > 23 || min > 59 || sec > 59) return null;
    var d = new Date(year, month - 1, day, hour, min, sec);
    // Check the date components round-trip (catches invalid dates like Feb 30)
    if (d.getFullYear() !== year ||
        d.getMonth() !== month - 1 ||
        d.getDate() !== day ||
        d.getHours() !== hour ||
        d.getMinutes() !== min ||
        d.getSeconds() !== sec) {
      return null;
    }
    return Math.floor(d.getTime() / 1000);
  }

  /**
   * Validate a manual entry string.
   * Returns {valid: bool, error: string|null}.
   */
  function validateManualEntry(str) {
    if (typeof str !== 'string' || str === '') {
      return { valid: false, error: 'Expected format: YYYY-MM-DD HH:MM:SS' };
    }
    var formatRe = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;
    if (!formatRe.test(str)) {
      return { valid: false, error: 'Expected format: YYYY-MM-DD HH:MM:SS' };
    }
    var epoch = parseEntryToEpoch(str);
    if (epoch === null) {
      return { valid: false, error: 'Invalid date' };
    }
    return { valid: true, error: null };
  }

  /**
   * Returns true only when both entries are valid and start < end.
   */
  function isApplyEnabled(startEpoch, endEpoch, startValid, endValid) {
    if (!startValid || !endValid) return false;
    if (startEpoch == null || endEpoch == null) return false;
    if (typeof startEpoch !== 'number' || typeof endEpoch !== 'number') return false;
    return startEpoch < endEpoch;
  }

  /**
   * Format a range summary string like:
   *   "Jun 10, 14:30:00 — Jun 11, 09:00:00 (18h 30m)"
   *
   * Duration formatting:
   *   < 1 minute:  "{s}s"
   *   < 1 hour:    "{m}m {s}s"
   *   < 24 hours:  "{h}h {m}m"
   *   >= 24 hours: "{d}d {h}h"
   */
  function formatRangeSummary(startEpoch, endEpoch) {
    var startDate = new Date(startEpoch * 1000);
    var endDate   = new Date(endEpoch * 1000);

    var startStr = MONTHS_SHORT[startDate.getMonth()] + ' ' +
      startDate.getDate() + ', ' +
      _pad2(startDate.getHours()) + ':' +
      _pad2(startDate.getMinutes()) + ':' +
      _pad2(startDate.getSeconds());

    var endStr = MONTHS_SHORT[endDate.getMonth()] + ' ' +
      endDate.getDate() + ', ' +
      _pad2(endDate.getHours()) + ':' +
      _pad2(endDate.getMinutes()) + ':' +
      _pad2(endDate.getSeconds());

    var diffSec = endEpoch - startEpoch;
    var duration = _formatDuration(diffSec);

    return startStr + ' \u2014 ' + endStr + ' (' + duration + ')';
  }

  /**
   * Format a duration in seconds to a human-readable string.
   */
  function _formatDuration(totalSec) {
    var absSec = Math.abs(Math.floor(totalSec));
    var days  = Math.floor(absSec / 86400);
    var hours = Math.floor((absSec % 86400) / 3600);
    var mins  = Math.floor((absSec % 3600) / 60);
    var secs  = absSec % 60;

    if (absSec >= 86400) {
      return days + 'd ' + hours + 'h';
    }
    if (absSec >= 3600) {
      return hours + 'h ' + mins + 'm';
    }
    if (absSec >= 60) {
      return mins + 'm ' + secs + 's';
    }
    return secs + 's';
  }

  /**
   * Compute a preset range given a preset key and the current time.
   * Returns {start, end} in epoch seconds.
   */
  function computePresetRange(presetKey, nowEpoch) {
    var preset = null;
    for (var i = 0; i < PICKER_PRESETS.length; i++) {
      if (PICKER_PRESETS[i].key === presetKey) {
        preset = PICKER_PRESETS[i];
        break;
      }
    }
    if (!preset) return { start: nowEpoch, end: nowEpoch };

    // Duration-based presets
    if (preset.seconds != null) {
      return { start: nowEpoch - preset.seconds, end: nowEpoch };
    }

    // Calendar-relative presets
    var now = new Date(nowEpoch * 1000);

    if (preset.compute === 'today') {
      var todayMidnight = new Date(
        now.getFullYear(), now.getMonth(), now.getDate(),
        0, 0, 0, 0
      );
      return { start: Math.floor(todayMidnight.getTime() / 1000), end: nowEpoch };
    }

    if (preset.compute === 'this-week') {
      // getDay(): 0=Sun, 1=Mon, ..., 6=Sat
      // We want Monday as start of week
      var dayOfWeek = now.getDay();
      var daysFromMonday = (dayOfWeek === 0) ? 6 : dayOfWeek - 1;
      var monday = new Date(
        now.getFullYear(), now.getMonth(), now.getDate() - daysFromMonday,
        0, 0, 0, 0
      );
      return { start: Math.floor(monday.getTime() / 1000), end: nowEpoch };
    }

    return { start: nowEpoch, end: nowEpoch };
  }

  /* ── DateRangePicker constructor ─────────────────────────────── */

  /**
   * DateRangePicker — unified panel with dual calendars, presets,
   * manual entry, and Apply/Cancel actions.
   *
   * @param {Object} options
   * @param {Element} options.anchorEl      - calendar button element
   * @param {Element} options.containerEl   - parent to append panel to
   * @param {Function} options.onApply      - callback(startEpoch, endEpoch)
   * @param {Function} options.onCancel     - callback()
   * @param {Function} options.getViewWindow - returns {start, end} epoch secs
   * @param {Element} options.themeRootEl   - element with CSS custom properties
   */
  function DateRangePicker(options) {
    this._opts = options;
    this._flatpickrInstance = null;
    this._initialized = false;
    this._panelEl = null;
    this._isOpen = false;
    this._startEpoch = null;
    this._endEpoch = null;
    this._activePreset = null;
    this._startInput = null;
    this._endInput = null;
    this._summaryEl = null;
    this._applyBtn = null;
    this._startError = null;
    this._endError = null;
    this._presetButtons = [];
    this._escHandler = null;
    this._resizeHandler = null;
    this._tabTrapHandler = null;
    this._fallbackMode = false;
    this._cancelBtn = null;

    this._buildPanel();
    /* Append to .rf-trace-viewer so CSS custom properties are inherited,
       but use position:fixed to escape overflow:auto clipping. */
    var themeRoot = document.querySelector('.rf-trace-viewer') || document.body;
    themeRoot.appendChild(this._panelEl);
  }

  /**
   * Build the full panel DOM structure.
   */
  DateRangePicker.prototype._buildPanel = function () {
    var self = this;

    /* ── Root panel ─────────────────────────────────────────────── */
    var panel = document.createElement('div');
    panel.className = 'date-range-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Select date range');
    panel.style.display = 'none';

    /* ── Sidebar with preset buttons ───────────────────────────── */
    var sidebar = document.createElement('div');
    sidebar.className = 'drp-sidebar';

    for (var i = 0; i < PICKER_PRESETS.length; i++) {
      var preset = PICKER_PRESETS[i];
      var btn = document.createElement('button');
      btn.className = 'drp-preset';
      btn.setAttribute('aria-label', preset.label);
      btn.textContent = preset.label;
      btn.dataset.presetKey = preset.key;
      sidebar.appendChild(btn);
      self._presetButtons.push(btn);

      /* Wire preset click handler */
      (function(presetBtn) {
        presetBtn.addEventListener('click', function() {
          self._applyPreset(presetBtn.dataset.presetKey);
        });
      })(btn);
    }

    panel.appendChild(sidebar);

    /* ── Main area ─────────────────────────────────────────────── */
    var main = document.createElement('div');
    main.className = 'drp-main';

    /* Calendar container */
    var calContainer = document.createElement('div');
    calContainer.className = 'drp-calendar-container';
    var fpHost = document.createElement('div');
    fpHost.id = 'drp-flatpickr-host';
    calContainer.appendChild(fpHost);
    main.appendChild(calContainer);

    /* Manual entry row */
    var manualRow = document.createElement('div');
    manualRow.className = 'drp-manual-row';

    // Start field
    var startField = document.createElement('div');
    startField.className = 'drp-field';
    var startLabel = document.createElement('label');
    startLabel.textContent = 'Start';
    var startInput = document.createElement('input');
    startInput.className = 'drp-manual-input';
    startInput.type = 'text';
    startInput.setAttribute('aria-label', 'Start date and time');
    startInput.placeholder = 'YYYY-MM-DD HH:MM:SS';
    var startError = document.createElement('div');
    startError.className = 'drp-field-error';
    startField.appendChild(startLabel);
    startField.appendChild(startInput);
    startField.appendChild(startError);
    manualRow.appendChild(startField);

    // End field
    var endField = document.createElement('div');
    endField.className = 'drp-field';
    var endLabel = document.createElement('label');
    endLabel.textContent = 'End';
    var endInput = document.createElement('input');
    endInput.className = 'drp-manual-input';
    endInput.type = 'text';
    endInput.setAttribute('aria-label', 'End date and time');
    endInput.placeholder = 'YYYY-MM-DD HH:MM:SS';
    var endError = document.createElement('div');
    endError.className = 'drp-field-error';
    endField.appendChild(endLabel);
    endField.appendChild(endInput);
    endField.appendChild(endError);
    manualRow.appendChild(endField);

    /* ── Wire manual entry event listeners ─────────────────────── */
    startInput.addEventListener('blur', function () { self._handleManualEntry(); });
    startInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') self._handleManualEntry();
    });
    startInput.addEventListener('input', function () { self._startError.textContent = ''; });

    endInput.addEventListener('blur', function () { self._handleManualEntry(); });
    endInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') self._handleManualEntry();
    });
    endInput.addEventListener('input', function () { self._endError.textContent = ''; });

    main.appendChild(manualRow);

    /* Summary */
    var summary = document.createElement('div');
    summary.className = 'drp-summary';
    summary.setAttribute('aria-live', 'polite');
    main.appendChild(summary);

    /* Action buttons */
    var actions = document.createElement('div');
    actions.className = 'drp-actions';
    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'drp-cancel';
    cancelBtn.setAttribute('aria-label', 'Cancel date selection');
    cancelBtn.textContent = 'Cancel';
    var applyBtn = document.createElement('button');
    applyBtn.className = 'drp-apply';
    applyBtn.setAttribute('aria-label', 'Apply selected date range');
    applyBtn.textContent = 'Apply';
    applyBtn.disabled = true;
    actions.appendChild(cancelBtn);
    actions.appendChild(applyBtn);

    /* Wire Apply button */
    applyBtn.addEventListener('click', function() {
      if (!self._applyBtn.disabled && self._startEpoch != null && self._endEpoch != null) {
        self._opts.onApply(self._startEpoch, self._endEpoch);
        self.close();
      }
    });

    /* Wire Cancel button */
    cancelBtn.addEventListener('click', function() {
      self._opts.onCancel();
      self.close();
    });

    main.appendChild(actions);

    panel.appendChild(main);

    /* ── Store references ──────────────────────────────────────── */
    this._panelEl = panel;
    this._startInput = startInput;
    this._endInput = endInput;
    this._summaryEl = summary;
    this._applyBtn = applyBtn;
    this._cancelBtn = cancelBtn;
    this._startError = startError;
    this._endError = endError;
  };

  /**
   * Lazy-initialize Flatpickr on first panel open (singleton pattern).
   * Falls back to native datetime-local inputs if Flatpickr is not available.
   */
  DateRangePicker.prototype._initFlatpickr = function () {
    if (this._initialized) return;
    this._initialized = true;

    var self = this;
    var fpHost = this._panelEl.querySelector('#drp-flatpickr-host');

    if (!window.flatpickr) {
      this._fallbackMode = true;
      console.warn('[DateRangePicker] Flatpickr not available, using fallback inputs');

      /* Build fallback panel with two datetime-local inputs */
      fpHost.innerHTML = '';

      var fallbackContainer = document.createElement('div');
      fallbackContainer.className = 'drp-fallback-container';

      var startLabel = document.createElement('label');
      startLabel.textContent = 'Start';
      startLabel.setAttribute('aria-label', 'Fallback start date and time');
      var startInput = document.createElement('input');
      startInput.type = 'datetime-local';
      startInput.className = 'drp-fallback-input';
      startInput.setAttribute('aria-label', 'Fallback start date and time');
      startInput.step = '1';

      var endLabel = document.createElement('label');
      endLabel.textContent = 'End';
      endLabel.setAttribute('aria-label', 'Fallback end date and time');
      var endInput = document.createElement('input');
      endInput.type = 'datetime-local';
      endInput.className = 'drp-fallback-input';
      endInput.setAttribute('aria-label', 'Fallback end date and time');
      endInput.step = '1';

      fallbackContainer.appendChild(startLabel);
      fallbackContainer.appendChild(startInput);
      fallbackContainer.appendChild(endLabel);
      fallbackContainer.appendChild(endInput);
      fpHost.appendChild(fallbackContainer);

      this._fallbackStartInput = startInput;
      this._fallbackEndInput = endInput;
      return;
    }

    /* Initialize Flatpickr in inline range mode */
    this._flatpickrInstance = window.flatpickr(fpHost, {
      mode: 'range',
      inline: true,
      showMonths: 2,
      enableTime: true,
      enableSeconds: true,
      time_24hr: true,
      dateFormat: 'Y-m-d H:i:S',
      defaultDate: null,
      onChange: function (selectedDates) {
        self._syncFromFlatpickr(selectedDates);
      },
      onMonthChange: function () {
        // Range highlight is maintained by Flatpickr's built-in CSS classes
        // (inRange, startRange, endRange) — no manual re-application needed
        // for inline mode. This hook is available for future customization.
      }
    });
  };

  /**
   * Sync internal state from Flatpickr's onChange callback.
   * @param {Date[]} selectedDates - 0, 1, or 2 Date objects from Flatpickr range mode
   */
  DateRangePicker.prototype._syncFromFlatpickr = function (selectedDates) {
    var i;

    /* ── Clear active preset ──────────────────────────────────── */
    this._activePreset = null;
    for (i = 0; i < this._presetButtons.length; i++) {
      this._presetButtons[i].classList.remove('active');
    }

    /* ── Clear validation errors ──────────────────────────────── */
    this._startError.textContent = '';
    this._endError.textContent = '';

    if (selectedDates.length === 0) {
      /* No selection — clear state */
      this._startEpoch = null;
      this._endEpoch = null;
      this._startInput.value = '';
      this._endInput.value = '';
      this._summaryEl.textContent = '';
      this._applyBtn.disabled = true;
    } else if (selectedDates.length === 1) {
      /* Incomplete selection — start date only */
      this._startEpoch = Math.floor(selectedDates[0].getTime() / 1000);
      this._endEpoch = null;
      this._startInput.value = formatEpochToEntry(this._startEpoch);
      this._endInput.value = '';
      this._summaryEl.textContent = formatEpochToEntry(this._startEpoch) + ' — …';
      this._applyBtn.disabled = true;
    } else {
      /* Complete range — both dates selected */
      this._startEpoch = Math.floor(selectedDates[0].getTime() / 1000);
      this._endEpoch = Math.floor(selectedDates[1].getTime() / 1000);
      this._startInput.value = formatEpochToEntry(this._startEpoch);
      this._endInput.value = formatEpochToEntry(this._endEpoch);
      this._summaryEl.textContent = formatRangeSummary(this._startEpoch, this._endEpoch);
      this._applyBtn.disabled = !isApplyEnabled(this._startEpoch, this._endEpoch, true, true);
    }
  };

  /* ── Quick-select preset logic ─────────────────────────────── */

  /**
   * Apply a quick-select preset by key.
   * Updates internal state, manual entry fields, summary, Flatpickr,
   * Apply button, and highlights the active preset button.
   *
   * @param {string} presetKey - one of the PICKER_PRESETS keys
   */
  DateRangePicker.prototype._applyPreset = function (presetKey) {
    var i;
    var range = computePresetRange(presetKey, Math.floor(Date.now() / 1000));

    /* Update internal state */
    this._startEpoch = range.start;
    this._endEpoch = range.end;

    /* Update manual entry fields */
    this._startInput.value = formatEpochToEntry(range.start);
    this._endInput.value = formatEpochToEntry(range.end);

    /* Update range summary */
    this._summaryEl.textContent = formatRangeSummary(range.start, range.end);

    /* Enable/disable Apply */
    this._applyBtn.disabled = !isApplyEnabled(range.start, range.end, true, true);

    /* Sync Flatpickr selection if available */
    if (this._flatpickrInstance) {
      this._flatpickrInstance.setDate(
        [new Date(range.start * 1000), new Date(range.end * 1000)],
        false
      );
    }

    /* Highlight active preset button */
    for (i = 0; i < this._presetButtons.length; i++) {
      this._presetButtons[i].classList.remove('active');
    }
    for (i = 0; i < this._presetButtons.length; i++) {
      if (this._presetButtons[i].dataset.presetKey === presetKey) {
        this._presetButtons[i].classList.add('active');
        break;
      }
    }
    this._activePreset = presetKey;

    /* Clear validation errors */
    this._startError.textContent = '';
    this._endError.textContent = '';
  };

  /* ── Manual entry validation and sync ──────────────────────── */

  /**
   * Validate both manual entry fields, update internal state,
   * sync Flatpickr, update summary, and enable/disable Apply.
   * Called on blur and Enter key for either input.
   */
  DateRangePicker.prototype._handleManualEntry = function () {
    var i;
    var startVal = validateManualEntry(this._startInput.value);
    var endVal = validateManualEntry(this._endInput.value);

    /* Show/clear per-field errors */
    this._startError.textContent = startVal.valid ? '' : startVal.error;
    this._endError.textContent = endVal.valid ? '' : endVal.error;

    var startEpoch = startVal.valid ? parseEntryToEpoch(this._startInput.value) : null;
    var endEpoch = endVal.valid ? parseEntryToEpoch(this._endInput.value) : null;

    /* Cross-field validation: start must be before end */
    if (startEpoch !== null && endEpoch !== null && startEpoch >= endEpoch) {
      this._startError.textContent = 'Start must be before end';
    }

    this._startEpoch = startEpoch;
    this._endEpoch = endEpoch;

    /* Update summary when both are valid and start < end */
    if (startEpoch !== null && endEpoch !== null && startEpoch < endEpoch) {
      this._summaryEl.textContent = formatRangeSummary(startEpoch, endEpoch);
    }

    /* Enable/disable Apply */
    var canApply = isApplyEnabled(startEpoch, endEpoch, startVal.valid, endVal.valid);
    if (startEpoch !== null && endEpoch !== null && startEpoch >= endEpoch) canApply = false;
    this._applyBtn.disabled = !canApply;

    /* Sync Flatpickr if both dates are valid and in order */
    if (canApply && this._flatpickrInstance) {
      this._flatpickrInstance.setDate(
        [new Date(startEpoch * 1000), new Date(endEpoch * 1000)], false
      );
    }

    /* Clear active preset — any manual modification clears it */
    this._activePreset = null;
    for (i = 0; i < this._presetButtons.length; i++) {
      this._presetButtons[i].classList.remove('active');
    }
  };

  /* ── Panel positioning ──────────────────────────────────────── */

  /**
   * Position the panel below (or above) the anchor element,
   * shifting left if it would overflow the viewport.
   */
  DateRangePicker.prototype._positionPanel = function () {
    var anchor = this._opts.anchorEl;
    var panel = this._panelEl;
    var rect = anchor.getBoundingClientRect();

    panel.style.position = 'fixed';
    panel.style.left = rect.left + 'px';
    panel.style.top = (rect.bottom + 4) + 'px';

    /* Measure panel after making it visible (display already set by caller) */
    var panelRect = panel.getBoundingClientRect();
    var vw = window.innerWidth || document.documentElement.clientWidth;
    var vh = window.innerHeight || document.documentElement.clientHeight;

    /* Shift left if overflowing right edge */
    if (panelRect.right > vw) {
      panel.style.left = Math.max(0, vw - panelRect.width) + 'px';
    }

    /* If overflowing bottom, position above the anchor instead */
    if (panelRect.bottom > vh) {
      panel.style.top = Math.max(0, rect.top - panelRect.height - 4) + 'px';
    }
  };

  /* ── Focus trap ───────────────────────────────────────────────── */

  /**
   * Collect all focusable elements inside the panel in tab order:
   * presets → start input → end input → (Flatpickr internals) → Apply → Cancel
   */
  DateRangePicker.prototype._getFocusableEls = function () {
    var els = [];
    var i;
    /* Preset buttons */
    for (i = 0; i < this._presetButtons.length; i++) {
      els.push(this._presetButtons[i]);
    }
    /* Manual entry inputs */
    els.push(this._startInput);
    els.push(this._endInput);
    /* Flatpickr time inputs (hour/minute/second spinners) */
    var fpInputs = this._panelEl.querySelectorAll(
      '.flatpickr-calendar input, .flatpickr-calendar select'
    );
    for (i = 0; i < fpInputs.length; i++) {
      els.push(fpInputs[i]);
    }
    /* Action buttons */
    if (!this._applyBtn.disabled) els.push(this._applyBtn);
    els.push(this._cancelBtn);
    return els;
  };

  /* ── Public lifecycle methods ─────────────────────────────────── */

  /**
   * Open the picker panel, populating from the current view window.
   */
  DateRangePicker.prototype.open = function () {
    var self = this;

    /* Lazy-init Flatpickr on first open */
    this._initFlatpickr();

    /* Read current view window */
    var vw = this._opts.getViewWindow();
    this._startEpoch = vw.start;
    this._endEpoch = vw.end;

    /* Populate manual entry fields */
    this._startInput.value = formatEpochToEntry(vw.start);
    this._endInput.value = formatEpochToEntry(vw.end);

    /* Clear any validation errors */
    this._startError.textContent = '';
    this._endError.textContent = '';

    /* Update range summary */
    this._summaryEl.textContent = formatRangeSummary(vw.start, vw.end);

    /* Enable/disable Apply */
    this._applyBtn.disabled = !isApplyEnabled(
      this._startEpoch, this._endEpoch, true, true
    );

    /* Sync Flatpickr or fallback inputs */
    if (!this._fallbackMode && this._flatpickrInstance) {
      this._flatpickrInstance.setDate(
        [new Date(vw.start * 1000), new Date(vw.end * 1000)],
        false
      );
    } else if (this._fallbackMode && this._fallbackStartInput) {
      /* Populate fallback datetime-local inputs */
      this._fallbackStartInput.value = _epochToDatetimeLocal(vw.start);
      this._fallbackEndInput.value = _epochToDatetimeLocal(vw.end);
    }

    /* Position and show */
    this._panelEl.style.display = '';
    this._positionPanel();
    this._isOpen = true;

    /* Escape key listener */
    this._escHandler = function (e) {
      if (e.key === 'Escape' || e.keyCode === 27) {
        self._opts.onCancel();
        self.close();
      }
    };
    document.addEventListener('keydown', this._escHandler);

    /* Window resize listener for repositioning */
    this._resizeHandler = function () {
      self._positionPanel();
    };
    window.addEventListener('resize', this._resizeHandler);

    /* Focus trap: Tab/Shift+Tab cycle within the panel */
    this._tabTrapHandler = function (e) {
      if (e.key !== 'Tab' && e.keyCode !== 9) return;
      var focusable = self._getFocusableEls();
      if (focusable.length === 0) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    this._panelEl.addEventListener('keydown', this._tabTrapHandler);

    /* Move focus into the panel (first preset button) */
    var focusable = this._getFocusableEls();
    if (focusable.length > 0) {
      focusable[0].focus();
    }
  };

  /**
   * Close the picker panel.
   */
  DateRangePicker.prototype.close = function () {
    this._panelEl.style.display = 'none';
    this._isOpen = false;

    /* Remove Escape key listener */
    if (this._escHandler) {
      document.removeEventListener('keydown', this._escHandler);
      this._escHandler = null;
    }

    /* Remove resize listener */
    if (this._resizeHandler) {
      window.removeEventListener('resize', this._resizeHandler);
      this._resizeHandler = null;
    }

    /* Remove focus trap */
    if (this._tabTrapHandler) {
      this._panelEl.removeEventListener('keydown', this._tabTrapHandler);
      this._tabTrapHandler = null;
    }

    /* Return focus to the anchor element */
    if (this._opts.anchorEl) {
      this._opts.anchorEl.focus();
    }

    this._activePreset = null;
  };

  /**
   * Returns whether the panel is currently open.
   */
  DateRangePicker.prototype.isOpen = function () {
    return this._isOpen;
  };

  /**
   * Tear down the picker: close, destroy Flatpickr, remove DOM.
   */
  DateRangePicker.prototype.destroy = function () {
    if (this._isOpen) {
      this.close();
    }

    if (this._flatpickrInstance) {
      this._flatpickrInstance.destroy();
      this._flatpickrInstance = null;
    }

    if (this._panelEl && this._panelEl.parentNode) {
      this._panelEl.parentNode.removeChild(this._panelEl);
    }

    /* Null out references */
    this._panelEl = null;
    this._startInput = null;
    this._endInput = null;
    this._summaryEl = null;
    this._applyBtn = null;
    this._cancelBtn = null;
    this._startError = null;
    this._endError = null;
    this._presetButtons = [];
    this._initialized = false;
    this._fallbackMode = false;
  };

  /**
   * Update the picker's selection from an external source (e.g., zoom bar preset).
   * Called when a preset is applied while the panel is open.
   */
  DateRangePicker.prototype.updateSelection = function (startEpoch, endEpoch) {
    this._startEpoch = startEpoch;
    this._endEpoch = endEpoch;

    /* Update manual entry fields */
    this._startInput.value = formatEpochToEntry(startEpoch);
    this._endInput.value = formatEpochToEntry(endEpoch);

    /* Clear validation errors */
    this._startError.textContent = '';
    this._endError.textContent = '';

    /* Update summary */
    this._summaryEl.textContent = formatRangeSummary(startEpoch, endEpoch);

    /* Enable/disable Apply */
    this._applyBtn.disabled = !isApplyEnabled(startEpoch, endEpoch, true, true);

    /* Sync Flatpickr if available */
    if (this._flatpickrInstance) {
      this._flatpickrInstance.setDate(
        [new Date(startEpoch * 1000), new Date(endEpoch * 1000)], false
      );
    }

    /* Clear active preset (the external preset is different from our internal presets) */
    this._activePreset = null;
    for (var i = 0; i < this._presetButtons.length; i++) {
      this._presetButtons[i].classList.remove('active');
    }
  };

  /* ── Helper: epoch → datetime-local value ────────────────────── */

  function _epochToDatetimeLocal(epochSec) {
    var d = new Date(epochSec * 1000);
    return d.getFullYear() + '-' +
      _pad2(d.getMonth() + 1) + '-' +
      _pad2(d.getDate()) + 'T' +
      _pad2(d.getHours()) + ':' +
      _pad2(d.getMinutes()) + ':' +
      _pad2(d.getSeconds());
  }

  ns.DateRangePicker = DateRangePicker;

  /* ── Expose helpers for testability ────────────────────────────── */

  ns.DateRangePickerHelpers = {
    formatEpochToEntry: formatEpochToEntry,
    parseEntryToEpoch: parseEntryToEpoch,
    validateManualEntry: validateManualEntry,
    isApplyEnabled: isApplyEnabled,
    formatRangeSummary: formatRangeSummary,
    computePresetRange: computePresetRange,
    PICKER_PRESETS: PICKER_PRESETS
  };

})();
