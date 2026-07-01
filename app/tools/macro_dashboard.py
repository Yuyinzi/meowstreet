MACRO_DASHBOARD_GROUPS = [
    {
        "id": "growth_cycle",
        "title": "Growth Cycle",
        "fields": [
            {
                "id": "gdp_indicator",
                "title": "Gross Domestic Product",
                "field": "macro.growth_cycle.gdp",
                "kind": "query",
            },
            {
                "id": "gdp_direction",
                "title": "GDP Direction",
                "field": "macro.growth_cycle.gdp_direction",
                "kind": "compute",
            },
            {
                "id": "industrial_production",
                "title": "Industrial Production",
                "field": "macro.growth_cycle.industrial_production",
                "kind": "query",
            },
            {
                "id": "corporate_earnings",
                "title": "Corporate Earnings",
                "field": "macro.growth_cycle.corporate_earnings",
                "kind": "query",
            },
            {
                "id": "weekly_jobless_claims",
                "title": "Weekly Jobless Claims",
                "field": "macro.growth_cycle.weekly_jobless_claims",
                "kind": "query",
            },
            {
                "id": "employment_situation_report",
                "title": "Employment Situation Report",
                "field": "macro.growth_cycle.employment_situation_report",
                "kind": "query",
            },
            {
                "id": "ism_pmi",
                "title": "ISM Manufacturing PMI",
                "field": "macro.growth_cycle.ism_pmi",
                "kind": "query",
            },
            {
                "id": "ism_new_orders",
                "title": "ISM New Orders",
                "field": "macro.growth_cycle.ism_new_orders",
                "kind": "query",
            },
            {
                "id": "ism_production",
                "title": "ISM Production",
                "field": "macro.growth_cycle.ism_production",
                "kind": "query",
            },
            {
                "id": "ism_employment",
                "title": "ISM Employment",
                "field": "macro.growth_cycle.ism_employment",
                "kind": "query",
            },
            {
                "id": "ism_inventories",
                "title": "ISM Inventories",
                "field": "macro.growth_cycle.ism_inventories",
                "kind": "query",
            },
            {
                "id": "ism_sector_growth_ranking",
                "title": "ISM Sector Growth Ranking",
                "field": "macro.growth_cycle.ism_sector_growth_ranking",
                "kind": "query",
            },
            {
                "id": "services_pmi",
                "title": "ISM Services PMI",
                "field": "macro.growth_cycle.services_pmi",
                "kind": "query",
            },
            {
                "id": "services_business_activity",
                "title": "Services Business Activity",
                "field": "macro.growth_cycle.services_business_activity",
                "kind": "query",
            },
            {
                "id": "services_new_orders",
                "title": "Services New Orders",
                "field": "macro.growth_cycle.services_new_orders",
                "kind": "query",
            },
            {
                "id": "services_employment",
                "title": "Services Employment",
                "field": "macro.growth_cycle.services_employment",
                "kind": "query",
            },
            {
                "id": "m2_mom_pct_change",
                "title": "M2 Month-on-Month Change",
                "field": "macro.growth_cycle.m2_mom_pct_change",
                "kind": "compute",
            },
            {
                "id": "m2_yoy_pct_change",
                "title": "M2 Year-on-Year Change",
                "field": "macro.growth_cycle.m2_yoy_pct_change",
                "kind": "compute",
            },
            {
                "id": "m2_percent_rank",
                "title": "M2 Percent Rank",
                "field": "macro.growth_cycle.m2_percent_rank",
                "kind": "compute",
            },
        ],
    },
    {
        "id": "rates_liquidity",
        "title": "Rates / Liquidity",
        "fields": [
            {
                "id": "real_interest_rate",
                "title": "Real Interest Rate",
                "field": "macro.rates_liquidity.real_interest_rate",
                "kind": "compute",
            },
            {
                "id": "nominal_10_year_yield",
                "title": "Nominal 10-Year Treasury Yield",
                "field": "macro.rates_liquidity.nominal_10_year_yield",
                "kind": "query",
            },
            {
                "id": "two_year_treasury_yield",
                "title": "2-Year Treasury Yield",
                "field": "macro.rates_liquidity.two_year_treasury_yield",
                "kind": "query",
            },
            {
                "id": "tens_twos_spread",
                "title": "10-Year Minus 2-Year Treasury Spread",
                "field": "macro.rates_liquidity.tens_twos_spread",
                "kind": "compute",
            },
            {
                "id": "one_month_treasury_yield",
                "title": "1-Month Treasury Yield",
                "field": "macro.rates_liquidity.one_month_treasury_yield",
                "kind": "query",
            },
            {
                "id": "three_month_treasury_yield",
                "title": "3-Month Treasury Yield",
                "field": "macro.rates_liquidity.three_month_treasury_yield",
                "kind": "query",
            },
            {
                "id": "six_month_treasury_yield",
                "title": "6-Month Treasury Yield",
                "field": "macro.rates_liquidity.six_month_treasury_yield",
                "kind": "query",
            },
            {
                "id": "one_year_treasury_yield",
                "title": "1-Year Treasury Yield",
                "field": "macro.rates_liquidity.one_year_treasury_yield",
                "kind": "query",
            },
            {
                "id": "three_year_treasury_yield",
                "title": "3-Year Treasury Yield",
                "field": "macro.rates_liquidity.three_year_treasury_yield",
                "kind": "query",
            },
            {
                "id": "five_year_treasury_yield",
                "title": "5-Year Treasury Yield",
                "field": "macro.rates_liquidity.five_year_treasury_yield",
                "kind": "query",
            },
            {
                "id": "seven_year_treasury_yield",
                "title": "7-Year Treasury Yield",
                "field": "macro.rates_liquidity.seven_year_treasury_yield",
                "kind": "query",
            },
            {
                "id": "twenty_year_treasury_yield",
                "title": "20-Year Treasury Yield",
                "field": "macro.rates_liquidity.twenty_year_treasury_yield",
                "kind": "query",
            },
            {
                "id": "fed_funds_rate",
                "title": "Fed Funds Rate",
                "field": "macro.rates_liquidity.fed_funds_rate",
                "kind": "query",
            },
            {
                "id": "three_month_libor",
                "title": "3-Month LIBOR",
                "field": "macro.rates_liquidity.three_month_libor",
                "kind": "query",
            },
        ],
    },
    {
        "id": "risk_sentiment",
        "title": "Risk / Sentiment",
        "fields": [
            {
                "id": "cpi_inflation",
                "title": "CPI Inflation",
                "field": "macro.risk_sentiment.cpi_inflation",
                "kind": "query",
            },
            {
                "id": "ppi_inflation",
                "title": "PPI Inflation",
                "field": "macro.risk_sentiment.ppi_inflation",
                "kind": "query",
            },
            {
                "id": "vix_index",
                "title": "VIX",
                "field": "macro.risk_sentiment.vix_index",
                "kind": "query",
            },
            {
                "id": "ted_spread",
                "title": "TED Spread",
                "field": "macro.risk_sentiment.ted_spread",
                "kind": "compute",
            },
            {
                "id": "credit_spread",
                "title": "Credit Spread",
                "field": "macro.risk_sentiment.credit_spread",
                "kind": "compute",
            },
            {
                "id": "aa_corporate_spread",
                "title": "AA Corporate Spread",
                "field": "macro.risk_sentiment.aa_corporate_spread",
                "kind": "query",
            },
            {
                "id": "bbb_corporate_spread",
                "title": "BBB Corporate Spread",
                "field": "macro.risk_sentiment.bbb_corporate_spread",
                "kind": "query",
            },
            {
                "id": "ccc_corporate_spread",
                "title": "CCC Corporate Spread",
                "field": "macro.risk_sentiment.ccc_corporate_spread",
                "kind": "query",
            },
            {
                "id": "umcsi_aggregate",
                "title": "UMCSI Aggregate",
                "field": "macro.risk_sentiment.umcsi_aggregate",
                "kind": "query",
            },
            {
                "id": "umcsi_expectations",
                "title": "UMCSI Expectations",
                "field": "macro.risk_sentiment.umcsi_expectations",
                "kind": "query",
            },
            {
                "id": "umcsi_current_conditions",
                "title": "UMCSI Current Conditions",
                "field": "macro.risk_sentiment.umcsi_current_conditions",
                "kind": "query",
            },
            {
                "id": "household_debt_to_gdp",
                "title": "Household Debt to GDP",
                "field": "macro.risk_sentiment.household_debt_to_gdp",
                "kind": "query",
            },
            {
                "id": "debt_service_payments_pct_income",
                "title": "Debt Service Payments as Percent of Income",
                "field": "macro.risk_sentiment.debt_service_payments_pct_income",
                "kind": "query",
            },
            {
                "id": "household_savings_rate",
                "title": "Household Savings Rate",
                "field": "macro.risk_sentiment.household_savings_rate",
                "kind": "query",
            },
        ],
    },
    {
        "id": "international_macro",
        "title": "International Macro",
        "fields": [
            {
                "id": "revenue_exposure_ratio",
                "title": "Geographic Revenue Exposure",
                "field": "macro.international_macro.revenue_exposure_ratio",
                "kind": "query",
            },
            {
                "id": "china_official_pmi",
                "title": "China Official Manufacturing PMI",
                "field": "macro.international_macro.china_official_pmi",
                "kind": "query",
            },
            {
                "id": "china_caixin_pmi",
                "title": "China Caixin Manufacturing PMI",
                "field": "macro.international_macro.china_caixin_pmi",
                "kind": "query",
            },
            {
                "id": "china_pmi_spread",
                "title": "China Official-Caixin PMI Spread",
                "field": "macro.international_macro.china_pmi_spread",
                "kind": "compute",
            },
            {
                "id": "chinese_real_rate",
                "title": "Chinese Real Interest Rate",
                "field": "macro.international_macro.chinese_real_rate",
                "kind": "compute",
            },
            {
                "id": "us_real_rate",
                "title": "US Real Interest Rate",
                "field": "macro.international_macro.us_real_rate",
                "kind": "compute",
            },
            {
                "id": "us_eu_manufacturing_pmis",
                "title": "US and EU Manufacturing PMIs",
                "field": "macro.international_macro.us_eu_manufacturing_pmis",
                "kind": "query",
            },
            {
                "id": "eurozone_esi",
                "title": "Eurozone Economic Sentiment Indicator",
                "field": "macro.international_macro.eurozone_esi",
                "kind": "query",
            },
            {
                "id": "european_real_yields",
                "title": "European Real Yields",
                "field": "macro.international_macro.european_real_yields",
                "kind": "compute",
            },
            {
                "id": "european_yield_curve_slope",
                "title": "European Yield Curve Slope",
                "field": "macro.international_macro.european_yield_curve_slope",
                "kind": "compute",
            },
        ],
    },
    {
        "id": "market_phase",
        "title": "Market Phase",
        "fields": [
            {
                "id": "sp500_monthly_price",
                "title": "S&P 500 Monthly Price",
                "field": "macro.market_phase.sp500_monthly_price",
                "kind": "query",
            },
            {
                "id": "index_high",
                "title": "Index Highest Closing High",
                "field": "macro.market_phase.index_high",
                "kind": "query",
            },
            {
                "id": "index_current_close",
                "title": "Index Current Close",
                "field": "macro.market_phase.index_current_close",
                "kind": "query",
            },
            {
                "id": "index_drawdown_pct",
                "title": "Index Drawdown Percent",
                "field": "macro.market_phase.index_drawdown_pct",
                "kind": "compute",
            },
            {
                "id": "market_phase_status",
                "title": "Market Phase Status",
                "field": "macro.market_phase.market_phase_status",
                "kind": "compute",
            },
            {
                "id": "bear_market_level",
                "title": "Bear Market Level",
                "field": "macro.market_phase.bear_market_level",
                "kind": "compute",
            },
            {
                "id": "bull_market_level",
                "title": "Bull Market Level",
                "field": "macro.market_phase.bull_market_level",
                "kind": "compute",
            },
        ],
    },
    {
        "id": "macro_bias",
        "title": "Macro Bias",
        "fields": [
            {
                "id": "pmi_expansion_check",
                "title": "PMI Expansion / Contraction Status",
                "field": "macro.bias.pmi_expansion_check",
                "kind": "compute",
            },
            {
                "id": "pmi_trend",
                "title": "PMI Trend",
                "field": "macro.bias.pmi_trend",
                "kind": "compute",
            },
            {
                "id": "pmi_phase_classification",
                "title": "PMI Phase Classification",
                "field": "macro.bias.pmi_phase_classification",
                "kind": "compute",
            },
            {
                "id": "macro_bias_score",
                "title": "Macro Bias Score",
                "field": "macro.bias.macro_bias_score",
                "kind": "compute",
            },
            {
                "id": "portfolio_bias",
                "title": "Portfolio Bias",
                "field": "macro.bias.portfolio_bias",
                "kind": "compute",
            },
            {
                "id": "regime",
                "title": "Macro Regime",
                "field": "macro.regime",
                "kind": "compute",
            },
        ],
    },
]


from app.tools.macro_growth_cycle import build_growth_cycle_dashboard


def fetch_macro_dashboard(growth_cycle_inputs=None):
    if not growth_cycle_inputs:
        return None
    return build_growth_cycle_dashboard(**growth_cycle_inputs)
