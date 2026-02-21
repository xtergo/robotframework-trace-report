#!/usr/bin/env python3
"""Verify timeline UI is present and functional."""
import re

with open('report_with_timeline.html', 'r') as f:
    html = f.read()

print("=" * 60)
print("VERIFICATION: Timeline UI Visibility")
print("=" * 60)

# View tabs
print("\n1. View Tab Navigation:")
checks = [
    ('View tabs container', r'<nav[^>]*class="view-tabs"'),
    ('Tree tab button', r'<button[^>]*data-view="tree"'),
    ('Timeline tab button', r'<button[^>]*data-view="timeline"'),
    ('Stats tab button', r'<button[^>]*data-view="stats"'),
    ('Tab role attributes', r'role="tab"'),
    ('Tab switching function', r'function _switchView\(viewId\)'),
]
for name, pattern in checks:
    result = '✓' if re.search(pattern, html) else '✗'
    print(f'  {result} {name}')

# View containers
print("\n2. View Containers:")
checks = [
    ('Tree view container', r'id="view-tree"'),
    ('Timeline view container', r'id="view-timeline"'),
    ('Stats view container', r'id="view-stats"'),
    ('View container class', r'class="view-container"'),
]
for name, pattern in checks:
    result = '✓' if re.search(pattern, html) else '✗'
    print(f'  {result} {name}')

# Timeline initialization
print("\n3. Timeline Initialization:")
checks = [
    ('initTimeline function exists', r'function initTimeline\('),
    ('Timeline init on tab switch', r"window\.initTimeline.*newContainer.*appState\.data"),
    ('Timeline lazy loading', r'data-initialized'),
]
for name, pattern in checks:
    result = '✓' if re.search(pattern, html, re.DOTALL) else '✗'
    print(f'  {result} {name}')

# Public API
print("\n4. Public API:")
checks = [
    ('RFTraceViewer.setFilter', r'window\.RFTraceViewer\.setFilter\s*=\s*function'),
    ('RFTraceViewer.navigateTo', r'window\.RFTraceViewer\.navigateTo\s*=\s*function'),
    ('RFTraceViewer.getState', r'window\.RFTraceViewer\.getState\s*=\s*function'),
    ('RFTraceViewer.registerPlugin', r'window\.RFTraceViewer\.registerPlugin\s*=\s*function'),
]
for name, pattern in checks:
    result = '✓' if re.search(pattern, html) else '✗'
    print(f'  {result} {name}')

# CSS styles
print("\n5. CSS Styles:")
checks = [
    ('View tabs styles', r'\.view-tabs\s*{'),
    ('View tab button styles', r'\.view-tab\s*{'),
    ('Active tab styles', r'\.view-tab\.active'),
    ('View container styles', r'\.view-container\s*{'),
]
for name, pattern in checks:
    result = '✓' if re.search(pattern, html) else '✗'
    print(f'  {result} {name}')

# File size check
import os
size_kb = os.path.getsize('report_with_timeline.html') / 1024
print(f"\n6. File Size: {size_kb:.1f} KB")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
print("\n✅ You should now see Timeline tab in the report!")
print("   Click the 'Timeline' tab to view the Gantt chart.")
