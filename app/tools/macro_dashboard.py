from app.tools.macro_growth_cycle import (
    GROWTH_CYCLE_DASHBOARD_FIELDS,
    build_growth_cycle_dashboard,
)


MACRO_DASHBOARD_GROUPS = [
    {
        "id": "growth_cycle",
        "title": "Growth Cycle",
        "fields": GROWTH_CYCLE_DASHBOARD_FIELDS,
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
                "id": "household_debt_service_ratio",
                "title": "Household Debt Service Payments as Percent of Disposable Income",
                "field": "macro.risk_sentiment.household_debt_service_ratio",
                "kind": "query",
            },
            {
                "id": "personal_saving_rate",
                "title": "Personal Saving Rate",
                "field": "macro.risk_sentiment.personal_saving_rate",
                "kind": "query",
            },
            {
                "id": "one_to_four_family_mortgage_liabilities",
                "title": "One-to-Four-Family Residential Mortgage Liabilities",
                "field": "macro.risk_sentiment.one_to_four_family_mortgage_liabilities",
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


def fetch_macro_dashboard(growth_cycle_inputs=None):
    if not growth_cycle_inputs:
        return None
    return build_growth_cycle_dashboard(**growth_cycle_inputs)
