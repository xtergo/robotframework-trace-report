# Requirements Document

## Introduction

This feature extends the RF Trace Viewer with a timeline-based span viewer that gives the user control over which time period is loaded, how spans are packed visually, and how services are toggled on/off with intelligent cache management. The feature introduces a "load window" with a draggable marker for incrementally fetching older spans, a compact layout button to reduce vertical space, a service toggle with delayed fetching and cache eviction, and a "Fit All" button that zooms to visible spans within the loaded window.

## Glossary

- **Timeline_Module**: The IIFE `timeline.js` that renders spans on a canvas-based timeline with zoom, pan, and lane assignment.
- **Live_Module**: The IIFE `live.js` that handles polling, span ingest, service filters, and connection status in live mode.
- **App_Module**: The IIFE `app.js` that builds the DOM structure, initializes views, and manages background fetching.
- **Load_Window**: The time interval for which spans have been fetched and cached. Defined by `activeWindowStart` (draggable) and the execution end time.
- **View_Window**: The time interval currently displayed in the timeline via zoom and pan. View_Window can never extend before Load_Window's start time.
- **Active_Window_Start**: The start time of the Load_Window. Default value: `executionStartTime - 15 minutes`. Can be dragged backward by the user.
- **Load_Start_Marker**: A draggable visual marker on the timeline representing Active_Window_Start.
- **Grey_Overlay**: A semi-transparent grey overlay drawn over the timeline area before Active_Window_Start to indicate that data is not loaded.
- **Delta_Fetch**: An incremental fetch of spans for a new time interval that is added to the existing cache without reloading everything.
- **Layout_Mode**: The current layout mode of the timeline, either `baseline` (default) or `compact` (packed).
- **Service_State**: A per-service state object with the fields: `enabled`, `disabledSince`, `pendingEnableFetch`, `evictionTimer`, `cachedSpanCount`, `cachedRange`.
- **Eviction_Timer**: A 30-second timer that starts when a service is toggled off. When the timer expires, the service's spans are cleared from the cache.
- **Enable_Grace_Period**: A 3-second delay after a service is toggled on before fetching starts, to avoid unnecessary requests during rapid on/off toggling.
- **Anti_Thrash_Guard**: A safeguard that stops fetching if the same service is toggled on/off 5 times within 10 seconds, until the behavior stabilizes.
- **Fit_All**: A function that zooms View_Window to the min/max of visible spans, clamped by Active_Window_Start.
- **Compact_Button**: A UI button that switches Layout_Mode to `compact` to pack visible spans vertically.

## Requirements

### Requirement 1: Load Window with Default Start

**User Story:** As a user, I want the timeline to automatically load spans from 15 minutes before the execution start time, so that I have relevant context without needing to adjust manually.

#### Acceptance Criteria

1. THE Live_Module SHALL set Active_Window_Start to `executionStartTime - 15 minutes` upon initialization.
2. THE Timeline_Module SHALL render a Load_Start_Marker at the Active_Window_Start position on the timeline.
3. THE Timeline_Module SHALL display the text "Loading from: HH:MM (drag to load older)" next to the Load_Start_Marker.
4. THE Timeline_Module SHALL render a Grey_Overlay over the timeline area before Active_Window_Start.
5. THE Grey_Overlay SHALL have a semi-transparent grey color that clearly distinguishes the unloaded area from the loaded area.

### Requirement 2: Draggable Load Start Marker with Delta Fetching

**User Story:** As a user, I want to drag the Load Start marker backward in time to incrementally load older spans, so that I can explore history without reloading all data.

#### Acceptance Criteria

1. WHEN the user drags the Load_Start_Marker backward, THE Timeline_Module SHALL update Active_Window_Start to the new position.
2. WHEN Active_Window_Start changes through dragging, THE Live_Module SHALL perform a Delta_Fetch for the new time interval (from the new Active_Window_Start to the previous Active_Window_Start).
3. THE Live_Module SHALL retain all previously cached spans during a Delta_Fetch and merge new spans with the existing cache.
4. THE Timeline_Module SHALL debounce drag events and trigger a Delta_Fetch either every 200–400 ms or on mouse-up, not on every pixel movement.
5. WHILE a Delta_Fetch is in progress, THE Timeline_Module SHALL display an indicator with the text "Fetching older spans…".
6. IF the user drags the Load_Start_Marker forward (toward the present), THEN THE Timeline_Module SHALL move the marker without triggering any new fetch.
7. WHEN the user drags the Load_Start_Marker forward past already cached spans, THE Live_Module SHALL retain all cached spans unchanged.

### Requirement 3: Maximum Limit for Load Window

**User Story:** As a user, I want there to be a maximum limit on how far back I can load, so that the system is not overloaded with too much data.

#### Acceptance Criteria

1. THE Live_Module SHALL limit Active_Window_Start to a maximum of 6 hours before executionStartTime.
2. THE Live_Module SHALL limit the total number of cached spans to 50,000.
3. IF the user attempts to drag the Load_Start_Marker beyond the 6-hour limit, THEN THE Timeline_Module SHALL stop the marker at the limit and display the message "Maximum limit reached (6 hours)".
4. IF the number of cached spans reaches 50,000, THEN THE Live_Module SHALL stop further Delta_Fetch operations and display the message "Span limit reached (50,000 spans)".
5. WHERE incremental loading is enabled, THE Live_Module SHALL fetch data in steps of 15 minutes per Delta_Fetch instead of the entire remaining interval.

### Requirement 4: Separation of Load Window and View Window

**User Story:** As a user, I want zoom and pan (View Window) to be independent of the loaded time interval (Load Window), so that I can navigate freely within loaded data without affecting what is fetched.

#### Acceptance Criteria

1. THE Timeline_Module SHALL maintain View_Window and Load_Window as two separate states.
2. THE Timeline_Module SHALL prevent View_Window's start time from being set to a value before Active_Window_Start.
3. WHEN the user zooms or pans, THE Timeline_Module SHALL only update View_Window without affecting Load_Window.
4. WHEN Active_Window_Start changes, THE Timeline_Module SHALL update the Grey_Overlay position without automatically changing View_Window.
5. THE Timeline_Module SHALL clamp filterStart to a value that is always >= Active_Window_Start.

### Requirement 5: Compact Spans Button

**User Story:** As a user, I want to pack visible spans vertically to reduce whitespace, so that I can see more spans at once without scrolling.

#### Acceptance Criteria

1. THE Timeline_Module SHALL render a Compact_Button with the text "Compact visible spans".
2. WHEN the user clicks the Compact_Button, THE Timeline_Module SHALL set Layout_Mode to `compact`.
3. WHILE Layout_Mode is `compact`, THE Timeline_Module SHALL pack span rows vertically without breaking group or parent logic.
4. WHILE Layout_Mode is `compact`, THE Compact_Button SHALL display the text "Reset layout".
5. WHEN the user clicks the Compact_Button while Layout_Mode is `compact`, THE Timeline_Module SHALL set Layout_Mode to `baseline`.
6. THE Compact_Button SHALL be keyboard accessible and respond to Enter and Space key presses.

### Requirement 6: Automatic Layout Mode Reset on Filter Change

**User Story:** As a user, I want the compact layout to reset automatically when I change filters, so that I always see a correct layout after filter changes.

#### Acceptance Criteria

1. WHEN a filter changes (service filter, search filter, or time filter), THE Timeline_Module SHALL set Layout_Mode to `baseline`.
2. WHEN Layout_Mode is reset to `baseline`, THE Timeline_Module SHALL restore span row positions to the default layout.
3. WHERE the "Auto-compact after filtering" setting is enabled, THE Timeline_Module SHALL automatically set Layout_Mode to `compact` after the filter change has been applied.
4. THE Timeline_Module SHALL render a toggle with the text "Auto-compact after filtering" (default: OFF) in the settings panel.

### Requirement 7: Service Toggle Off (Hide and Eviction)

**User Story:** As a user, I want spans to be hidden immediately when I toggle off a service, and for the cache to be cleared after a delay, so that I can quickly filter out services without losing data if I change my mind.

#### Acceptance Criteria

1. WHEN the user toggles off a service, THE Live_Module SHALL immediately hide the service's spans in the timeline (UI filter).
2. WHEN the user toggles off a service, THE Live_Module SHALL start an Eviction_Timer of 30 seconds for that service.
3. WHEN the Eviction_Timer expires, THE Live_Module SHALL clear the service's spans from the cache but retain the service's name in the service list.
4. IF the user toggles the service back on within 30 seconds (before the Eviction_Timer expires), THEN THE Live_Module SHALL cancel the Eviction_Timer and display cached spans without a new fetch.
5. THE Live_Module SHALL maintain a Service_State object per service with the fields: `enabled`, `disabledSince`, `pendingEnableFetch`, `evictionTimer`, `cachedSpanCount`, `cachedRange`.

### Requirement 8: Service Toggle On with Grace Period and Debounce

**User Story:** As a user, I want the system to wait briefly before fetching data when I toggle on a service, so that rapid on/off toggling does not cause unnecessary network requests.

#### Acceptance Criteria

1. WHEN the user toggles on a service that has no cached spans, THE Live_Module SHALL start an Enable_Grace_Period of 3 seconds before fetching begins.
2. WHILE the Enable_Grace_Period is active, THE Live_Module SHALL display a subtle countdown "Loading starts in 3…2…1" next to the service name in the service list.
3. IF the user toggles off the service within the Enable_Grace_Period (3 seconds), THEN THE Live_Module SHALL cancel the pending fetch without making any network request.
4. WHEN the Enable_Grace_Period expires, THE Live_Module SHALL fetch spans for the service within the interval Active_Window_Start to the execution end time and merge the result with the cache.
5. WHERE only a single service is pending fetch and no cache exists, THE Live_Module SHALL use a shortened grace period of 1 second instead of 3 seconds.

### Requirement 9: Anti-Thrash Protection for Service Toggling

**User Story:** As a user, I want the system to protect itself against rapid repeated on/off toggling of the same service, so that the server is not overloaded with unnecessary requests.

#### Acceptance Criteria

1. THE Live_Module SHALL count the number of on/off toggles per service within a 10-second sliding window.
2. IF the same service is toggled on/off 5 times within 10 seconds, THEN THE Live_Module SHALL activate the Anti_Thrash_Guard for that service and stop all fetches until the behavior stabilizes.
3. WHILE the Anti_Thrash_Guard is active for a service, THE Live_Module SHALL display the message "Stabilizing…" next to the service name in the service list.
4. WHEN 10 seconds pass without further toggling for a service with an active Anti_Thrash_Guard, THE Live_Module SHALL deactivate the Anti_Thrash_Guard and allow normal fetching.

### Requirement 10: Fit All Button

**User Story:** As a user, I want to zoom the timeline so that all visible spans fit, so that I can quickly get an overview without manual zoom adjustment.

#### Acceptance Criteria

1. THE Timeline_Module SHALL render a Fit_All button with the text "Fit All".
2. WHEN the user clicks the Fit_All button, THE Timeline_Module SHALL zoom View_Window to the min and max timestamps of all visible (non-filtered) spans.
3. THE Timeline_Module SHALL clamp the Fit_All result so that View_Window's start time is never before Active_Window_Start.
4. IF no spans are visible after filtering, THEN THE Timeline_Module SHALL zoom to the last 5 minutes within the Load_Window and display a toast message "No spans in current filters".
5. THE Fit_All button SHALL be keyboard accessible and respond to Enter and Space key presses.

### Requirement 11: UX Details for the Service List

**User Story:** As a user, I want to see detailed status information per service in the service list, so that I understand each service's current state (active, cached, pending, eviction).

#### Acceptance Criteria

1. WHILE a service is enabled and has cached spans, THE Live_Module SHALL display "Enabled (N spans cached)" next to the service name in the service list.
2. WHILE a service has an active Enable_Grace_Period, THE Live_Module SHALL display "Pending (N s)" with a countdown next to the service name.
3. WHILE a service has an active Eviction_Timer, THE Live_Module SHALL display "Evicting in N s" next to the service name.
4. WHILE a service has an active Anti_Thrash_Guard, THE Live_Module SHALL display "Stabilizing…" next to the service name.
5. WHEN a service is disabled and the Eviction_Timer has expired, THE Live_Module SHALL display "Disabled" next to the service name.

### Requirement 12: Backward Compatibility

**User Story:** As a developer, I want the new features to not break existing functionality, so that current users are not negatively affected.

#### Acceptance Criteria

1. THE Timeline_Module SHALL continue to render spans with the existing lane assignment logic in `baseline` Layout_Mode.
2. THE Live_Module SHALL continue to support both `json` and `signoz` provider types for polling.
3. THE Live_Module SHALL continue to emit `timeline-data` events that the Timeline_Module consumes.
4. WHEN the viewer is loaded in static (non-live) mode, THE Timeline_Module SHALL render spans without Load_Start_Marker, Grey_Overlay, or service toggle functionality.
5. THE App_Module SHALL continue to emit the `app-ready` event after the DOM structure has been built.
6. THE Timeline_Module SHALL continue to support existing zoom, pan, and span selection features without changed behavior.
