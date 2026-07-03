# GDP Relationship Detail Chart Plan

## Goal

Improve the GDP relationship detail charts so they behave like the market phase detail chart: clearer axis ticks, full-width time-series charts, and hover tooltips showing values by date.

## Current Problems

- GDP relationship charts use simplified chart logic with coarse min/max value labels.
- Period ticks are too sparse.
- Charts do not support hover inspection.
- `Rolling 10Y correlations by lag` has multiple lag series and needs full-width rendering with all lag lines visible.

## Implementation Plan

1. Reuse market phase chart patterns
   - Use the existing market phase chart helpers as reference:
     - `niceTicks()`
     - `yAxisTicks()`
     - `xAxisTicks()`
     - SVG grid/tick rendering
     - hover tooltip behavior
   - Keep the GDP chart renderer separate if the data shape differs, but reuse the same interaction and axis ideas.

2. Replace simplified GDP chart rendering
   - Replace or refactor `renderMiniLineChart()` into a full chart renderer for GDP relationship charts.
   - Suggested function name: `renderRelationshipLineChart()`.
   - Inputs:
     - `title`
     - `series`
     - `keys`
     - `labels`
     - chart options such as `wide`, `percentMode`, or `valueFormatter`
   - Output:
     - full-width chart container
     - SVG chart
     - legend
     - x-axis ticks
     - y-axis ticks
     - grid lines
     - tooltip container

3. Improve y-axis ticks
   - Compute min/max across all visible series keys.
   - Use a `niceTicks()` style scale instead of only min/max labels.
   - Render several y-axis tick labels and horizontal grid lines.
   - Keep correlation values as raw correlation numbers, not percentages.

4. Improve x-axis ticks
   - Use the same date sampling approach as the market phase chart.
   - Format dates with `fmtMonthYear()`.
   - Show enough period context without overcrowding.

5. Add hover tooltip support
   - Adapt the market phase tooltip behavior.
   - On mouse move:
     - find the nearest date by x-position
     - show the date
     - show all series values for that date
     - include series labels matching the legend
   - For `Rolling 10Y correlations by lag`, tooltip should include:
     - No lag
     - 3M lag
     - 6M lag
     - 9M lag
     - 12M lag

6. Handle missing values
   - Some lag correlation series start later because rolling correlations require enough history.
   - Line rendering should skip missing values without breaking other series.
   - Tooltip should show `n/a` for missing values at the hovered date.

7. Keep layout full-width for time-series charts
   - Keep these charts full-width:
     - `Index YoY vs GDP YoY`
     - `Rolling correlation`
     - `Rolling 10Y correlations by lag`
   - Non-time-series blocks like `Quadnomial distribution` can remain smaller.

8. Update tests
   - Static JS tests should assert GDP relationship charts use:
     - tick helpers
     - grid/tick classes
     - tooltip hook
     - full-width chart class
   - Static tests should assert the old coarse axis caption text is absent:
     - no `Y-axis: value`
     - no `X-axis: period`
   - Add or extend helper tests through `window.__macroDashboardTestHooks` if needed:
     - GDP y-axis ticks are generated
     - date ticks are sampled
     - missing lag values do not break paths
   - Keep the GDP import/tool/API tests green.

## Verification

Run:

```bash
node --check static/macro-dashboard.js
.venv/bin/pytest tests/test_macro_dashboard_static.py -q
.venv/bin/pytest tests/test_gdp_market_relationships_db.py tests/test_import_gdp_market_relationships.py tests/test_gdp_market_relationship_tool.py tests/test_macro_dashboard_api.py tests/test_macro_dashboard_static.py -q
```

Manual check:

1. Open `/macro-dashboard.html`.
2. Click the USGDP card.
3. Confirm GDP charts are full-width.
4. Confirm x/y ticks are denser and similar to the market phase detail chart.
5. Confirm hover tooltip shows values for the hovered date.
6. Confirm `Rolling 10Y correlations by lag` shows all five lag lines.
