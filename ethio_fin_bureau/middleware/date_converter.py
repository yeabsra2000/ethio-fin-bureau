"""Ge'ez / Ethiopian calendar → ISO-8601 Gregorian date conversion."""
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import unquote

from ethiopian_date_converter.ethiopian_date_convertor import EthDate

# Amharic month names (Ge'ez calendar)
AMHARIC_MONTHS = {
    "መስከረም": 1, "ጥቅምት": 2, "ህዳር": 3, "ታህሳስ": 4,
    "ጥር": 5, "የካቲት": 6, "መጋቢት": 7, "ሚያዚያ": 8,
    "ግንቦት": 9, "ሰኔ": 10, "ሐምሌ": 11, "ነሀሴ": 12, "ጳጉሜ": 13,
}

# Gregorian URL path: /2026/07/19/
URL_DATE_RE = re.compile(r"/(20\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])(?:/|$)")

# Ethiopian numeric: 17/10/2017 or 17-10-2017 or 17.10.2017
ETH_NUMERIC_RE = re.compile(r"\b(0?[1-9]|[12]\d|3[01])\s*[/.\-]\s*(0?[1-9]|1[0-2])\s*[/.\-]\s*(20\d{2})\b")

# Year/Month only in URL: /2026/07/
URL_YEAR_MONTH_RE = re.compile(r"/(20\d{2})/(0[1-9]|1[0-2])(?:/|$)")

# Amharic: መስከረም 12, 2017 or 12 ቀን 2017
# Pattern 1: MonthName Day, Year
# Pattern 2: Day MonthName Year
AMHARIC_DATE_RE = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})|(?P<day2>\d{1,2})\s+(?P<month2>\w+)\s+(?P<year2>\d{4})"
)

# Common Ethiopian news date patterns in headlines
# e.g., "June 15, 2023" or "15 June 2023"
ENGLISH_DATE_RE = re.compile(
    r"\b(?P<month_name>\w+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})|(?P<day2>\d{1,2})\s+(?P<month_name2>\w+)\s+(?P<year2>\d{4})\b"
)

# English month names mapping
ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _to_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _to_iso_from_year_month(year: int, month: int) -> str:
    """Convert year/month to ISO date, defaulting to 1st of month."""
    try:
        return _to_iso(datetime(year, month, 1))
    except ValueError:
        return f"{year:04d}-{month:02d}-01"


def parse_url_date(url: str) -> Optional[str]:
    """Extract full date from URL path (YYYY/MM/DD)."""
    match = URL_DATE_RE.search(unquote(url))
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return _to_iso(datetime(year, month, day))
    except ValueError:
        return None


def parse_url_year_month(url: str) -> Optional[str]:
    """Extract year/month from URL path (YYYY/MM) - defaults to 1st of month."""
    match = URL_YEAR_MONTH_RE.search(unquote(url))
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return _to_iso_from_year_month(year, month)


def parse_ethiopian_numeric(text: str) -> Optional[str]:
    """Parse D/M/YYYY Ethiopian numeric dates."""
    match = ETH_NUMERIC_RE.search(text)
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        eth = EthDate(day, month, year)
        return _to_iso(eth.to_gregorian())
    except (ValueError, TypeError):
        return None


def parse_amharic_date(text: str) -> Optional[str]:
    """Parse Amharic month-name dates (Ge'ez calendar)."""
    match = AMHARIC_DATE_RE.search(text)
    if not match:
        return None
    
    # Pattern 1: MonthName Day, Year (named groups month, day, year)
    if match.group('month'):
        month_name = match.group('month')
        day = int(match.group('day'))
        year = int(match.group('year'))
        month = AMHARIC_MONTHS.get(month_name)
        if not month:
            return None
        try:
            eth = EthDate(day, month, year)
            return _to_iso(eth.to_gregorian())
        except (ValueError, TypeError):
            return None
    
    # Pattern 2: Day MonthName Year (named groups day2, month2, year2)
    if match.group('day2'):
        day = int(match.group('day2'))
        month_name = match.group('month2')
        year = int(match.group('year2'))
        month = AMHARIC_MONTHS.get(month_name)
        if not month:
            return None
        try:
            eth = EthDate(day, month, year)
            return _to_iso(eth.to_gregorian())
        except (ValueError, TypeError):
            return None
    
    return None


def parse_english_date(text: str) -> Optional[str]:
    """Parse English month-name dates (e.g., 'June 15, 2023')."""
    match = ENGLISH_DATE_RE.search(text)
    if not match:
        return None
    
    # Pattern 1: MonthName Day, Year
    if match.group('month_name'):
        month_name = match.group('month_name').lower()
        day = int(match.group('day'))
        year = int(match.group('year'))
        month = ENGLISH_MONTHS.get(month_name)
        if not month:
            return None
        try:
            return _to_iso(datetime(year, month, day))
        except ValueError:
            return None
    
    # Pattern 2: Day MonthName Year
    if match.group('month_name2'):
        month_name = match.group('month_name2').lower()
        day = int(match.group('day2'))
        year = int(match.group('year2'))
        month = ENGLISH_MONTHS.get(month_name)
        if not month:
            return None
        try:
            return _to_iso(datetime(year, month, day))
        except ValueError:
            return None
    
    return None


def extract_date_from_content(html_content: str) -> Optional[str]:
    """
    Extract date from article HTML content.
    Looks for date in meta tags, time elements, and common date patterns.
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Try meta tags with date
        for meta in soup.find_all("meta", attrs={"property": re.compile(r"date", re.I)}):
            content = meta.get("content", "")
            if content:
                result = parse_english_date(content) or parse_url_date(content)
                if result:
                    return result
        
        # Try time elements
        for time_elem in soup.find_all("time"):
            datetime_attr = time_elem.get("datetime")
            if datetime_attr:
                result = parse_url_date(datetime_attr)
                if result:
                    return result
            text = time_elem.get_text(strip=True)
            if text:
                result = parse_english_date(text) or parse_amharic_date(text)
                if result:
                    return result
        
        # Try article published date classes
        for cls in ["published", "post-date", "article-date", "date", "byline"]:
            elem = soup.find(class_=re.compile(cls, re.I))
            if elem:
                text = elem.get_text(strip=True)
                result = parse_english_date(text) or parse_amharic_date(text) or parse_url_date(text)
                if result:
                    return result
    except Exception:
        pass
    
    return None


def extract_and_convert_dates(headline: str, url: str) -> Optional[str]:
    """
    Resolve the best available publication date as ISO-8601 (YYYY-MM-DD).
    Priority: URL full date → URL year/month → Ethiopian numeric in text → Amharic month in text → English date in text.
    Falls back to current date if no date is found.
    """
    # Try full date in URL
    result = parse_url_date(url)
    if result:
        return result
    
    # Try year/month in URL
    result = parse_url_year_month(url)
    if result:
        return result
    
    # Try numeric in headline
    result = parse_ethiopian_numeric(headline)
    if result:
        return result
    
    # Try numeric in URL
    result = parse_ethiopian_numeric(url)
    if result:
        return result
    
    # Try Amharic month in headline
    result = parse_amharic_date(headline)
    if result:
        return result
    
    # Try English month in headline
    result = parse_english_date(headline)
    if result:
        return result
    
    # No date found - fallback to current date
    return datetime.now().strftime("%Y-%m-%d")