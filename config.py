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
