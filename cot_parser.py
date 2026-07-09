"""
Parser module — extracts structured COT data from CFTC fixed-width text.

The CFTC report is a pre-formatted text file. Each instrument block has:
  - A header line: "INSTRUMENT_NAME - EXCHANGE (CONTRACT_SPEC)"
  - A CFTC Code line with Open Interest
  - A "Positions" section with 14 numbers (Dealer, AM, LF, Other, Nonreportable)
  - A "Percent of Open Interest" section with 14 numbers
  - Separated by dashed lines

Column order (14 values per row):
  0:  Dealer Long         1:  Dealer Short       2:  Dealer Spreading
  3:  AM Long             4:  AM Short           5:  AM Spreading
  6:  LF Long             7:  LF Short           8:  LF Spreading
  9:  Other Long          10: Other Short        11: Other Spreading
  12: Nonreportable Long  13: Nonreportable Short
"""

import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

from config import INSTRUMENTS


def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and decode entities, return plain text."""
    soup = BeautifulSoup(raw_html, "html.parser")
    # The data is inside <pre> tags
    pre_tags = soup.find_all("pre")
    if pre_tags:
        return "\n".join(tag.get_text() for tag in pre_tags)
    # Fallback: just get all text
    return soup.get_text()


def _parse_number(s: str) -> Optional[float]:
    """Parse a number string like '200,285' or '-1,554' or '.' into float."""
    s = s.strip()
    if s == "." or s == "":
        return 0.0
    # Remove commas
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_report_date(text: str) -> Optional[str]:
    """Extract the 'as of' date from the report header."""
    match = re.search(
        r"Positions\s+as\s+of\s+(\w+\s+\d+,\s*\d{4})", text
    )
    if match:
        return match.group(1).strip()
    return None


def _split_into_blocks(text: str) -> List[str]:
    """
    Split the report text into instrument blocks using the dashed separator.
    Each block starts after a separator line and ends at the next one.
    """
    # The separator is a line of mostly dashes
    separator_pattern = re.compile(r"^-{50,}", re.MULTILINE)
    parts = separator_pattern.split(text)
    return parts


def _match_instrument(block_text: str) -> Optional[str]:
    """
    Check if this block matches any of our instruments.
    Returns the display name (e.g., 'EUR') or None.
    """
    # Get the first significant line (instrument header)
    upper_text = block_text.upper()

    for display_name, info in INSTRUMENTS.items():
        pattern = info["pattern"].upper()
        exchange = info["exchange"].upper()

        # Must match both instrument name and exchange
        if pattern in upper_text and exchange in upper_text:
            # Avoid matching consolidated entries (e.g., "S&P 500 Consolidated")
            # We want the specific contract, not the consolidated
            if "CONSOLIDATED" in upper_text and display_name in [
                "SP500 (E-MINI)", "NAS100 (NQ MINI)"
            ]:
                continue
            # Avoid matching sub-indices (Energy, Financial, Health Care, etc.)
            # for S&P 500 — we want only E-MINI S&P 500
            if display_name == "SP500 (E-MINI)":
                if any(x in upper_text for x in [
                    "ENERGY", "FINANCIAL", "HEALTH CARE",
                    "INDUSTRIAL", "TECHNOLOGY", "UTILITIES",
                    "COMMUNICATION", "MICRO E-MINI", "ANNUAL DIVIDEND",
                    "QUARTERLY DIVIDEND", "TOTAL RETURN", "S&P 400",
                ]):
                    continue
            # For Nasdaq, avoid micro
            if display_name == "NAS100 (NQ MINI)":
                if "MICRO" in upper_text:
                    continue
            # For DJIA, avoid consolidated and DOW JONES REAL ESTATE
            if display_name == "US30 (YM)":
                if "REAL ESTATE" in upper_text:
                    continue
            # For Russell, avoid
            if "RUSSELL" in upper_text and display_name not in []:
                continue
            return display_name

    return None


def _extract_numbers_from_line(line: str) -> List[float]:
    """Extract all numbers from a line of text."""
    # Match numbers like 200,285 or -1,554 or just . (which means 0)
    tokens = re.findall(r"-?[\d,]+\.?\d*|\.", line)
    return [_parse_number(t) for t in tokens]


def _extract_open_interest(block_text: str) -> float:
    """Extract Open Interest value from the block."""
    match = re.search(r"Open\s+Interest\s+is\s+([\d,]+)", block_text)
    if match:
        return _parse_number(match.group(1))
    return 0.0


def _extract_positions(block_text: str) -> Optional[List[float]]:
    """
    Extract the 14 position values from the 'Positions' section.
    The positions line comes right after 'Positions' header.
    """
    lines = block_text.split("\n")
    found_positions = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "Positions":
            found_positions = True
            continue

        if found_positions and stripped:
            nums = _extract_numbers_from_line(stripped)
            if len(nums) >= 14:
                return nums[:14]
            elif len(nums) > 0:
                # Sometimes values might be on next line too
                # Try combining with next line
                if i + 1 < len(lines):
                    combined = stripped + " " + lines[i + 1].strip()
                    nums = _extract_numbers_from_line(combined)
                    if len(nums) >= 14:
                        return nums[:14]
                return None
            # Skip empty lines after "Positions"
            continue

    return None


def _extract_percentages(block_text: str) -> Optional[List[float]]:
    """
    Extract the 14 percentage values from the
    'Percent of Open Interest' section.
    """
    lines = block_text.split("\n")
    found_pct = False

    for i, line in enumerate(lines):
        if "Percent of Open Interest" in line:
            found_pct = True
            continue

        if found_pct and line.strip():
            nums = _extract_numbers_from_line(line.strip())
            if len(nums) >= 14:
                return nums[:14]
            elif len(nums) > 0 and i + 1 < len(lines):
                combined = line.strip() + " " + lines[i + 1].strip()
                nums = _extract_numbers_from_line(combined)
                if len(nums) >= 14:
                    return nums[:14]
            return None

    return None


def parse_report(raw_html: str) -> Dict:
    """
    Parse a full CFTC report page into structured data.

    Returns:
        {
            "report_date": "June 30, 2026",
            "instruments": {
                "EUR": {
                    "open_interest": 790076.0,
                    "dealer": {"long": ..., "short": ...},
                    "asset_manager": {"long": ..., "short": ...},
                    "leveraged_funds": {"long": ..., "short": ...},
                },
                ...
            }
        }
    """
    text = _clean_html(raw_html)
    report_date = _extract_report_date(text)

    result = {
        "report_date": report_date,
        "instruments": {},
    }

    blocks = _split_into_blocks(text)

    for block in blocks:
        if not block.strip():
            continue

        name = _match_instrument(block)
        if name is None:
            continue

        # Skip if we already have this instrument (avoid duplicates from
        # consolidated entries)
        if name in result["instruments"]:
            continue

        oi = _extract_open_interest(block)
        positions = _extract_positions(block)
        # percentages = _extract_percentages(block)  # Not used directly

        if positions is None or oi == 0:
            continue

        # Column indices: Dealer(0,1,2), AM(3,4,5), LF(6,7,8), Other(9,10,11), NR(12,13)
        result["instruments"][name] = {
            "open_interest": oi,
            "dealer": {
                "long": positions[0],
                "short": positions[1],
            },
            "asset_manager": {
                "long": positions[3],
                "short": positions[4],
            },
            "leveraged_funds": {
                "long": positions[6],
                "short": positions[7],
            },
        }

    return result
