"""
Configuration for Commodity COT Data.
Contains CFTC Disaggregated instrument patterns matched against Socrata
market_and_exchange_names strings from dataset 72hh-3qpy.
"""

# ── Socrata dataset info ───────────────────────────────────────────────
COMMODITY_DATASET_ID = "72hh-3qpy"
SOCRATA_HOST = "publicreporting.cftc.gov"

# ── Instrument definitions ─────────────────────────────────────────────
# "pattern"  : substring to search for in market_and_exchange_names (upper-cased)
# "exchange" : exchange substring to confirm the correct contract
#
# These strings match the Socrata market_and_exchange_names column exactly.
COMMODITY_INSTRUMENTS = {
    "Gold": {
        "pattern": "GOLD",
        "exchange": "COMMODITY EXCHANGE INC.",
    },
    "Silver": {
        "pattern": "SILVER",
        "exchange": "COMMODITY EXCHANGE INC.",
    },
    "WTI Crude": {
        "pattern": "WTI-PHYSICAL",
        "exchange": "NEW YORK MERCANTILE EXCHANGE",
    },
    "Brent": {
        "pattern": "BRENT LAST DAY",
        "exchange": "NEW YORK MERCANTILE EXCHANGE",
    },
    "Natural Gas": {
        "pattern": "NAT GAS NYME",
        "exchange": "NEW YORK MERCANTILE EXCHANGE",
    },
    "Copper": {
        "pattern": "COPPER- #1",
        "exchange": "COMMODITY EXCHANGE INC.",
    },
}

COMMODITY_ORDER = ["Gold", "Silver", "WTI Crude", "Brent", "Natural Gas", "Copper"]
