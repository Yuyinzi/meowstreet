# Aluminium COT publication gap

Investigated November 9, 2026. Configured instrument: ALUMINUM - COMMODITY EXCHANGE INC., code 191691, disaggregated futures-only, managed money.

## Verified

The official 2026 archive has only five rows for this contract: January 6 (27 reportable traders), January 13 (23), February 3 (20), June 2 (22), June 9 (21). June 9 open interest is 2,477 contracts. The June 9 weekly HTML report independently confirms the contract and 21 traders. The June 16 weekly report omits 191691. The annual archive contains no later row under that code, so the importer is not dropping newer records or missing a simple market-name change.

CFTC FAQ 1 says markets disappear when reportable large traders drop below 20, and return when the count reaches 20 again. The sparse 2026 publication pattern and last count of 21 strongly support this explanation. This is an inference: no contract-specific notice or unpublished post-June-9 trader count was found. Do not label the futures contract discontinued based on absent COT data.

Premium contracts 191693 and 191696 continue through November 3 but are different exposures; no substitution or history stitching was performed. Existing unavailable/stale behavior remains appropriate; retain archive checks so the same contract can resume if it reappears.

## Sources

- https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm (FAQ 1, Missing Contract Market)
- https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2026/futures/other_lf060926.htm
- https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2026/futures/other_lf061626.htm
- https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip

No application code, runtime method, or source identity changed.
