"""
Configuration for COT Analyzer Dashboard.
Contains instrument definitions, release schedule, and URL templates.
"""

from datetime import date, timedelta

# ──────────────────────────────────────────────────────────────────────
# Instruments we care about — maps display name to CFTC instrument name
# patterns (used to match blocks in the report text).
# ──────────────────────────────────────────────────────────────────────
INSTRUMENTS = {
    "USD (DXY)":        {"pattern": "USD INDEX",             "exchange": "ICE FUTURES"},
    "EUR":              {"pattern": "EURO FX",               "exchange": "CHICAGO MERCANTILE"},
    "GBP":              {"pattern": "BRITISH POUND",         "exchange": "CHICAGO MERCANTILE"},
    "CAD":              {"pattern": "CANADIAN DOLLAR",       "exchange": "CHICAGO MERCANTILE"},
    "AUD":              {"pattern": "AUSTRALIAN DOLLAR",     "exchange": "CHICAGO MERCANTILE"},
    "NZD":              {"pattern": "NZ DOLLAR",             "exchange": "CHICAGO MERCANTILE"},
    "CHF":              {"pattern": "SWISS FRANC",           "exchange": "CHICAGO MERCANTILE"},
    "JPY":              {"pattern": "JAPANESE YEN",          "exchange": "CHICAGO MERCANTILE"},
}

# ──────────────────────────────────────────────────────────────────────
# 2026 CFTC COT Release Schedule
# These are the dates the reports are *released* (usually Fridays).
# ──────────────────────────────────────────────────────────────────────
RELEASE_DATES_2026 = sorted([
    # January
    date(2026, 1, 5), date(2026, 1, 9), date(2026, 1, 16),
    date(2026, 1, 23), date(2026, 1, 30),
    # February
    date(2026, 2, 6), date(2026, 2, 13), date(2026, 2, 20), date(2026, 2, 27),
    # March
    date(2026, 3, 6), date(2026, 3, 13), date(2026, 3, 20), date(2026, 3, 27),
    # April
    date(2026, 4, 3), date(2026, 4, 10), date(2026, 4, 17), date(2026, 4, 24),
    # May
    date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 15),
    date(2026, 5, 22), date(2026, 5, 29),
    # June
    date(2026, 6, 5), date(2026, 6, 12), date(2026, 6, 22), date(2026, 6, 26),
    # July
    date(2026, 7, 6), date(2026, 7, 10), date(2026, 7, 17),
    date(2026, 7, 24), date(2026, 7, 31),
    # August
    date(2026, 8, 7), date(2026, 8, 14), date(2026, 8, 21), date(2026, 8, 28),
    # September
    date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25),
    # October
    date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16),
    date(2026, 10, 23), date(2026, 10, 30),
    # November
    date(2026, 11, 6), date(2026, 11, 16), date(2026, 11, 20), date(2026, 11, 30),
    # December
    date(2026, 12, 4), date(2026, 12, 11), date(2026, 12, 18), date(2026, 12, 28),
])



# ──────────────────────────────────────────────────────────────────────
# URL Templates
# ──────────────────────────────────────────────────────────────────────
CURRENT_URL = "https://www.cftc.gov/dea/futures/financial_lf.htm"

# Archive URL template — {MMDDYY} placeholder
ARCHIVE_URL_TEMPLATE = (
    "https://www.cftc.gov/sites/default/files/files/dea/cotarchives"
    "/{year}/futures/financial_lf{mmddyy}.htm"
)


def get_archive_url(release_date: date) -> str:
    """Build archive URL from a release date by finding the prior Tuesday."""
    # CFTC report dates are always Tuesdays. Find the most recent Tuesday.
    offset = (release_date.weekday() - 1) % 7
    report_date = release_date - timedelta(days=offset)
    
    mmddyy = report_date.strftime("%m%d%y")
    return ARCHIVE_URL_TEMPLATE.format(
        year=report_date.year,
        mmddyy=mmddyy,
    )


# ──────────────────────────────────────────────────────────────────────
# Contract Specifications & Approximate FX Rates
# Used to convert contract counts → USD notional values (billions).
#
# contract_size: units of the underlying currency per 1 futures contract
# fx_rate_to_usd: approximate exchange rate to convert 1 unit → USD
#   - For XXX/USD pairs (EUR, GBP, AUD, NZD): rate is direct (e.g., 1 EUR = 1.158 USD)
#   - For USD/XXX pairs (CAD, CHF, JPY): rate is 1/spot (e.g., 1 CAD = 1/1.391 USD)
#   - For DXY: contract_size = 1000, value = 1000 × index level
#
# Update these rates periodically for more accurate dollar estimates.
# ──────────────────────────────────────────────────────────────────────
CONTRACT_SPECS = {
    "EUR": {
        "contract_size": 125_000,       # 125,000 EUR per contract
        "fx_rate_to_usd": 1.158,        # 1 EUR ≈ 1.158 USD
    },
    "GBP": {
        "contract_size": 62_500,        # 62,500 GBP per contract
        "fx_rate_to_usd": 1.348,        # 1 GBP ≈ 1.348 USD
    },
    "CAD": {
        "contract_size": 100_000,       # 100,000 CAD per contract
        "fx_rate_to_usd": 1 / 1.391,   # 1 CAD ≈ 0.719 USD
    },
    "AUD": {
        "contract_size": 100_000,       # 100,000 AUD per contract
        "fx_rate_to_usd": 0.714,        # 1 AUD ≈ 0.714 USD
    },
    "NZD": {
        "contract_size": 100_000,       # 100,000 NZD per contract
        "fx_rate_to_usd": 0.584,        # 1 NZD ≈ 0.584 USD
    },
    "CHF": {
        "contract_size": 125_000,       # 125,000 CHF per contract
        "fx_rate_to_usd": 1 / 0.813,   # 1 CHF ≈ 1.230 USD
    },
    "JPY": {
        "contract_size": 12_500_000,    # 12,500,000 JPY per contract
        "fx_rate_to_usd": 1 / 159.0,   # 1 JPY ≈ 0.00629 USD
    },
    "USD (DXY)": {
        "contract_size": 1_000,         # $1,000 × Index value
        "fx_rate_to_usd": 99.5,         # DXY index level (~99.5)
    },
}


def contracts_to_usd(currency_name: str, num_contracts: float) -> float:
    """Convert a number of futures contracts to USD notional value.

    Returns the value in raw USD (not billions).
    """
    spec = CONTRACT_SPECS.get(currency_name)
    if spec is None:
        return 0.0
    return num_contracts * spec["contract_size"] * spec["fx_rate_to_usd"]


def contracts_to_billions(currency_name: str, num_contracts: float) -> float:
    """Convert a number of futures contracts to USD notional value in billions."""
    return contracts_to_usd(currency_name, num_contracts) / 1_000_000_000
