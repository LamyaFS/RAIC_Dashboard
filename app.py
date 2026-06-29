from __future__ import annotations

import base64
import html
import json
import os
import re
import textwrap
from pathlib import Path
from typing import Iterable, Sequence

import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials


# -----------------------------------------------------------------------------
# Application settings
# -----------------------------------------------------------------------------
SPREADSHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "TOOL Scouter Results")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "All Mapped Solutions")
CREDENTIALS_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
REPORT_YEAR = int(os.getenv("REPORT_YEAR", "2026"))
APP_DIR = Path(__file__).resolve().parent
ASSET_DIR = APP_DIR / "assets"
HEADER_MAP_FILE = ASSET_DIR / "header_world_map.png"

# The dashboard checks Google Sheets again while a viewer keeps the page open.
# A 30-second interval gives near-real-time updates without excessive API calls.
AUTO_REFRESH_SECONDS = max(15, int(os.getenv("AUTO_REFRESH_SECONDS", "30")))
_requested_cache_ttl = int(
    os.getenv("CACHE_TTL_SECONDS", str(max(1, AUTO_REFRESH_SECONDS - 2)))
)
CACHE_TTL_SECONDS = min(
    max(1, _requested_cache_ttl),
    max(1, AUTO_REFRESH_SECONDS - 2),
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

COLORS = {
    "page": "#00182a",
    "panel": "#032844",
    "panel_2": "#042e4f",
    "panel_border": "#0b4c73",
    "track": "#0b3658",
    "text": "#d9e8f2",
    "muted": "#a9bed0",
    "accent": "#2dd4bf",
    "accent_2": "#29bd75",
    "cyan": "#5cd9d1",
    "blue": "#67a7df",
}

ORG_TYPE_ORDER = [
    "Scaleup",
    "Corporate",
    "Startup",
    "University Spinout",
    "Research",
    "Project",
]

ORG_TYPE_SHORT = {
    "Scaleup": "Scaleup",
    "Corporate": "Corporate",
    "Startup": "Startup",
    "University Spinout": "Univ. Spinout",
    "Research": "Research",
    "Project": "Project",
}

ORG_COLORS = ["#2dc77c", "#9ae9a0", "#40b97f", "#b8edf2", "#73afe2", "#2f75b8"]

COUNTRY_CODES = {
    "Australia": ("AU", "AUS"),
    "Belgium": ("BE", "BEL"),
    "Brazil": ("BR", "BRA"),
    "Canada": ("CA", "CAN"),
    "Chile": ("CL", "CHL"),
    "China": ("CN", "CHN"),
    "Egypt": ("EG", "EGY"),
    "Estonia": ("EE", "EST"),
    "Fiji": ("FJ", "FJI"),
    "Finland": ("FI", "FIN"),
    "France": ("FR", "FRA"),
    "Germany": ("DE", "DEU"),
    "India": ("IN", "IND"),
    "Ireland": ("IE", "IRL"),
    "Italy": ("IT", "ITA"),
    "Japan": ("JP", "JPN"),
    "Kenya": ("KE", "KEN"),
    "Luxembourg": ("LU", "LUX"),
    "Morocco": ("MA", "MAR"),
    "Netherlands": ("NL", "NLD"),
    "New Zealand": ("NZ", "NZL"),
    "Nigeria": ("NG", "NGA"),
    "Norway": ("NO", "NOR"),
    "Philippines": ("PH", "PHL"),
    "Rwanda": ("RW", "RWA"),
    "Saudi Arabia": ("SA", "SAU"),
    "Singapore": ("SG", "SGP"),
    "South Africa": ("ZA", "ZAF"),
    "South Korea": ("KR", "KOR"),
    "Sweden": ("SE", "SWE"),
    "Switzerland": ("CH", "CHE"),
    "Taiwan": ("TW", "TWN"),
    "United Arab Emirates": ("AE", "ARE"),
    "United Kingdom": ("GB", "GBR"),
    "United States": ("US", "USA"),
}


COUNTRY_NAME_ALIASES = {
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "united kingdom": "United Kingdom",
    "usa": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "u.s.": "United States",
    "united states of america": "United States",
    "united states": "United States",
    "south korea": "South Korea",
    "republic of korea": "South Korea",
    "korea, republic of": "South Korea",
    "north korea": "North Korea",
    "democratic people's republic of korea": "North Korea",
    "russia": "Russia",
    "russian federation": "Russia",
    "czech republic": "Czechia",
    "czechia": "Czechia",
    "viet nam": "Vietnam",
    "vietnam": "Vietnam",
    "ivory coast": "CÃ´te d'Ivoire",
    "cote d'ivoire": "CÃ´te d'Ivoire",
    "cÃ´te d'ivoire": "CÃ´te d'Ivoire",
    "bolivia": "Bolivia",
    "tanzania": "Tanzania",
    "moldova": "Moldova",
    "laos": "Laos",
    "syria": "Syria",
    "iran": "Iran",
    "brunei": "Brunei",
    "cape verde": "Cabo Verde",
    "swaziland": "Eswatini",
}

REQUIRED_COLUMNS = [
    "Company",
    "Solution Categories",
    "Diversity",
    "Organisation Type",
    "HQ Country",
    "Region",
    "Lifecycle Stage",
    "TRL",
    "Year Established",
]


# -----------------------------------------------------------------------------
# Page and visual styling
# -----------------------------------------------------------------------------
def image_data_uri(path: Path) -> str:
    """Return a local image as a CSS-ready data URI."""
    if not path.exists():
        return ""

    suffix = path.suffix.lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def configure_page() -> None:
    header_map_uri = image_data_uri(HEADER_MAP_FILE)
    st.set_page_config(
        page_title="Guardians of the Arctic | Global Guide",
        page_icon="â„ï¸",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        f"""
        <style>
        :root {{
            --page: {COLORS['page']};
            --panel: {COLORS['panel']};
            --panel2: {COLORS['panel_2']};
            --border: {COLORS['panel_border']};
            --track: {COLORS['track']};
            --text: {COLORS['text']};
            --muted: {COLORS['muted']};
            --accent: {COLORS['accent']};
            --accent2: {COLORS['accent_2']};
        }}

        html, body, [data-testid="stAppViewContainer"], .stApp {{
            background:
                radial-gradient(circle at 18% -10%, rgba(19, 113, 151, 0.22), transparent 31%),
                linear-gradient(180deg, #001426 0%, var(--page) 44%, #001326 100%);
            color: var(--text);
        }}

        [data-testid="stHeader"] {{
            background: transparent;
        }}

        [data-testid="stToolbar"], #MainMenu, footer {{
            visibility: hidden;
        }}

        .block-container {{
            max-width: 1500px;
            padding: 0.45rem 0.65rem 1.5rem;
        }}

        .st-key-hero {{
            position: relative;
            isolation: isolate;
            overflow: hidden;
            padding: 0.75rem 1.35rem 0.55rem;
            margin-bottom: 0.55rem;
            border: 1px solid #77c6d2;
            border-radius: 11px 11px 0 0;
            background:
                radial-gradient(circle at 72% 20%, rgba(238, 255, 255, 0.48), transparent 14%),
                radial-gradient(circle at 79% 56%, rgba(59, 161, 188, 0.28), transparent 30%),
                linear-gradient(105deg, #c9f8fb 0%, #9be4ed 47%, #6fc4d7 100%);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.20);
        }}

        /* Faded Arctic/world map watermark shown in the top banner. */
        .st-key-hero::before {{
            content: "";
            position: absolute;
            z-index: 0;
            width: clamp(390px, 43vw, 700px);
            height: 132%;
            right: 11.5%;
            top: -16%;
            background-image: url("{header_map_uri}");
            background-repeat: no-repeat;
            background-position: center;
            background-size: contain;
            opacity: 0.47;
            filter: saturate(0.75) contrast(0.92) brightness(1.04);
            pointer-events: none;
        }}

        /* Fine curved latitude-style lines over the map watermark. */
        .st-key-hero::after {{
            content: "";
            position: absolute;
            z-index: 0;
            width: clamp(420px, 46vw, 740px);
            height: 225%;
            right: 8%;
            top: -77%;
            border-radius: 50%;
            background:
                repeating-radial-gradient(
                    ellipse at center,
                    transparent 0 38px,
                    rgba(234, 255, 255, 0.13) 39px 40px,
                    transparent 41px 77px
                );
            transform: rotate(-8deg);
            pointer-events: none;
        }}

        .st-key-hero > div {{
            position: relative;
            z-index: 2;
        }}

        .hero-title {{
            color: #001b36;
            font-family: "Arial Narrow", "Roboto Condensed", Impact, sans-serif;
            font-size: clamp(2rem, 3vw, 3.6rem);
            line-height: 0.98;
            font-weight: 900;
            letter-spacing: 0.035em;
            text-transform: uppercase;
            margin-top: 0.08rem;
        }}

        .hero-subtitle {{
            color: #051e35;
            font-size: clamp(1rem, 1.45vw, 1.45rem);
            font-weight: 600;
            margin-top: 0.48rem;
        }}

        .hero-guide {{
            color: #0c3450;
            font-size: 1rem;
            margin-top: 0.65rem;
            margin-bottom: 0.1rem;
        }}

        .st-key-hero [data-testid="stWidgetLabel"] p {{
            color: #0d6f78;
            font-weight: 700;
            font-size: 0.8rem;
            margin-bottom: 0.12rem;
        }}

        .st-key-hero [data-baseweb="select"] > div {{
            min-height: 2.55rem;
            color: #d9f6ff;
            background: #001c32;
            border: 1px solid #0a6681;
            border-radius: 8px;
            box-shadow: inset 0 0 0 1px rgba(76, 215, 212, 0.08);
        }}

        .st-key-hero [data-testid="stSelectbox"] {{
            margin-bottom: -0.15rem;
        }}

        .section-card {{
            background: linear-gradient(145deg, rgba(4, 48, 80, 0.96), rgba(2, 34, 61, 0.98));
            border: 1px solid var(--border);
            border-radius: 10px;
            box-shadow: inset 0 1px 0 rgba(89, 191, 211, 0.07), 0 8px 18px rgba(0, 0, 0, 0.12);
            padding: 0.85rem 1rem;
        }}

        .st-key-org-card,
        .st-key-regions-card,
        .st-key-diversity-card,
        .st-key-distribution-card,
        .st-key-countries-card,
        .st-key-map-card {{
            background: linear-gradient(145deg, rgba(4, 48, 80, 0.96), rgba(2, 34, 61, 0.98));
            border: 1px solid var(--border);
            border-radius: 10px;
            box-shadow: inset 0 1px 0 rgba(89, 191, 211, 0.07), 0 8px 18px rgba(0, 0, 0, 0.12);
            padding: 0.72rem 1rem 0.6rem;
        }}

        .st-key-org-card, .st-key-regions-card {{
            min-height: 312px;
        }}

        .st-key-diversity-card, .st-key-distribution-card {{
            min-height: 310px;
        }}

        .st-key-countries-card, .st-key-map-card {{
            min-height: 560px;
        }}

        .section-title {{
            color: var(--accent);
            font-family: "Arial Narrow", "Roboto Condensed", sans-serif;
            font-size: 1rem;
            font-weight: 800;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin: 0.05rem 0 0.55rem;
        }}

        .kpi-card {{
            min-height: 112px;
            display: flex;
            align-items: center;
            gap: 0.82rem;
            padding: 0.78rem 0.88rem;
            border: 1px solid #0b4b73;
            border-radius: 10px;
            background: linear-gradient(145deg, #07345a 0%, #032542 100%);
            box-shadow: inset 0 1px 0 rgba(122, 224, 230, 0.07), 0 7px 15px rgba(0, 0, 0, 0.12);
        }}

        .kpi-icon {{
            width: 58px;
            min-width: 58px;
            height: 58px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            color: #91ead4;
            background: linear-gradient(145deg, #176596, #0a476f);
            box-shadow: inset 0 0 0 1px rgba(110, 221, 219, 0.08);
        }}

        .kpi-icon svg {{
            width: 34px;
            height: 34px;
        }}

        .kpi-value {{
            color: var(--accent);
            font-family: "Arial Narrow", "Roboto Condensed", sans-serif;
            font-size: 2.25rem;
            font-weight: 900;
            line-height: 1;
        }}

        .kpi-label {{
            color: #f1f7fb;
            font-size: 0.88rem;
            line-height: 1.15;
            margin-top: 0.24rem;
        }}

        .kpi-detail {{
            color: #c2d5e3;
            min-height: 1.1rem;
            font-size: 0.73rem;
            line-height: 1.2;
            margin-top: 0.34rem;
        }}

        .legend-wrap {{
            padding-top: 0.2rem;
        }}

        .legend-row {{
            display: grid;
            grid-template-columns: 15px 1fr 34px;
            gap: 0.55rem;
            align-items: center;
            margin: 0.58rem 0;
            color: #d9e8f2;
            font-size: 0.84rem;
        }}

        .legend-swatch {{
            width: 13px;
            height: 18px;
            border-radius: 3px;
        }}

        .legend-value {{
            color: var(--accent);
            text-align: right;
            font-variant-numeric: tabular-nums;
        }}

        .progress-list {{
            width: 100%;
            padding-top: 0.1rem;
        }}

        .progress-row {{
            display: grid;
            grid-template-columns: minmax(115px, 0.72fr) minmax(130px, 1.45fr) 32px;
            gap: 0.55rem;
            align-items: center;
            margin: 0.58rem 0;
        }}

        .progress-label {{
            color: #e0ebf3;
            font-size: 0.84rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .progress-track {{
            width: 100%;
            height: 17px;
            background: #0b3658;
            border-radius: 2px;
            overflow: hidden;
            box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.25);
        }}

        .progress-fill {{
            height: 100%;
            min-width: 0;
            border-radius: 2px;
            background: linear-gradient(90deg, #21b876 0%, #36c98a 100%);
            box-shadow: 0 0 12px rgba(45, 212, 191, 0.12);
        }}

        .progress-value {{
            color: var(--accent);
            font-size: 0.82rem;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }}

        .diversity-mini {{
            min-height: 104px;
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            padding: 0.62rem;
            border-radius: 8px;
            border: 1px solid #0b4a71;
            background: linear-gradient(150deg, #073456, #02223e);
        }}

        .diversity-icon {{
            width: 43px;
            min-width: 43px;
            height: 43px;
            color: #83e1ca;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            background: linear-gradient(145deg, #17658d, #0a466b);
        }}

        .diversity-icon svg {{ width: 27px; height: 27px; }}
        .diversity-number {{ color: var(--accent); font-size: 1.85rem; line-height: 1; font-weight: 900; }}
        .diversity-percent {{ color: #e0ebf2; font-size: 0.72rem; margin-top: 0.2rem; }}
        .diversity-label {{ color: #d0dfe9; font-size: 0.72rem; line-height: 1.2; margin-top: 0.18rem; }}

        .footer-strip {{
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: center;
            margin: 0.52rem 0;
            padding: 0.56rem 0.85rem;
            border: 1px solid #0b4b73;
            border-radius: 8px;
            background: linear-gradient(90deg, #042d4b, #02223e);
            color: #a9bdcc;
            font-size: 0.77rem;
        }}

        .footer-message {{ display: flex; align-items: center; gap: 0.55rem; }}
        .footer-message svg {{ width: 22px; height: 22px; color: var(--accent); }}

        .country-row {{
            display: grid;
            grid-template-columns: 28px minmax(95px, 0.72fr) minmax(115px, 1.35fr) 28px;
            gap: 0.45rem;
            align-items: center;
            margin: 0.65rem 0;
        }}

        .country-code {{ color: #f1f6fa; font-size: 0.75rem; font-weight: 800; }}
        .country-name {{ color: #e3edf4; font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .country-note {{ color: #829cb0; font-size: 0.7rem; margin-top: 1.05rem; }}

        .country-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.36rem;
            padding: 0.35rem 0 0.25rem;
        }}

        .country-chip {{
            display: inline-flex;
            gap: 0.3rem;
            align-items: center;
            padding: 0.36rem 0.5rem;
            border-radius: 6px;
            border: 1px solid #0b4165;
            background: #073052;
            color: #bcd0df;
            font-size: 0.7rem;
            line-height: 1;
        }}

        .country-chip b {{ color: #eef6fb; font-size: 0.72rem; }}

        .empty-note {{
            color: #b7cbd9;
            padding: 1.2rem 0;
            text-align: center;
        }}

        [data-testid="stPlotlyChart"] {{
            margin-top: -0.25rem;
        }}

        @media (max-width: 900px) {{
            .block-container {{ padding-left: 0.45rem; padding-right: 0.45rem; }}
            .kpi-card {{ min-height: 100px; }}
            .progress-row {{ grid-template-columns: minmax(95px, 0.9fr) minmax(100px, 1.2fr) 28px; }}
            .footer-strip {{ align-items: flex-start; flex-direction: column; }}
            .st-key-hero::before {{
                width: 430px;
                height: 105%;
                right: 4%;
                top: -4%;
                opacity: 0.28;
            }}
            .st-key-hero::after {{
                right: -7%;
                opacity: 0.70;
            }}
        }}

        @media (max-width: 620px) {{
            .st-key-hero::before {{
                width: 330px;
                right: -13%;
                opacity: 0.20;
            }}
            .st-key-hero::after {{
                display: none;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Data access and cleaning
# -----------------------------------------------------------------------------
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean Google Sheets text while preserving the original field contents."""
    df.columns = df.columns.astype(str).str.strip()
    df = df.fillna("")
    df = df.astype(str)

    # DataFrame.map is available in modern pandas. applymap keeps compatibility
    # with older installations.
    if hasattr(df, "map"):
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    else:
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    return df


def normalize_column_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    canonical_by_key = {
        "company": "Company",
        "solution categories": "Solution Categories",
        "diversity": "Diversity",
        "organisation type": "Organisation Type",
        "organization type": "Organisation Type",
        "hq country": "HQ Country",
        "region": "Region",
        "lifecycle stage": "Lifecycle Stage",
        "trl": "TRL",
        "year established": "Year Established",
    }

    for column in df.columns:
        normalized = normalize_column_name(column)
        key = normalized.lower()
        rename_map[column] = canonical_by_key.get(key, normalized)

    df = df.rename(columns=rename_map)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    for column in REQUIRED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    return df


def service_account_info_from_secrets() -> dict | None:
    try:
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except (FileNotFoundError, KeyError, TypeError):
        return None
    return None


@st.cache_resource(show_spinner=False)
def get_google_client() -> gspread.Client:
    secret_info = service_account_info_from_secrets()

    if secret_info:
        credentials = Credentials.from_service_account_info(secret_info, scopes=SCOPES)
    else:
        credentials_path = Path(CREDENTIALS_FILE)
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Google service account file not found: {credentials_path.resolve()}"
            )
        credentials = Credentials.from_service_account_file(
            str(credentials_path), scopes=SCOPES
        )

    return gspread.authorize(credentials)


def load_google_sheet(
    spreadsheet_name: str,
    spreadsheet_id: str,
    worksheet_name: str,
) -> pd.DataFrame:
    client = get_google_client()
    spreadsheet = (
        client.open_by_key(spreadsheet_id)
        if spreadsheet_id
        else client.open(spreadsheet_name)
    )
    worksheet = spreadsheet.worksheet(worksheet_name)
    values = worksheet.get_all_values()

    if not values:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    headers = values[0]
    width = len(headers)
    body = [(row + [""] * width)[:width] for row in values[1:]]
    df = pd.DataFrame(body, columns=headers)
    df = clean_dataframe(df)
    df = standardize_columns(df)
    df = df[df["Company"].str.strip().ne("")].copy()
    return df.reset_index(drop=True)


# -----------------------------------------------------------------------------
# Metric calculations
# -----------------------------------------------------------------------------
def extract_stage_numbers(value: str) -> list[int]:
    numbers = [int(number) for number in re.findall(r"\d+", str(value))]
    return [number for number in numbers if 1 <= number <= 9]


def is_high_maturity(value: str) -> bool:
    numbers = extract_stage_numbers(value)
    return bool(numbers) and max(numbers) >= 6


def category_count(value: str) -> int:
    text = str(value)
    category_numbers = set(re.findall(r"(?<!\d)([1-6])\s*\)", text))
    if category_numbers:
        return len(category_numbers)

    # Fallback for newly added rows that omit category numbers.
    keywords = {
        "transition mineral-free": 1,
        "transition mineral free": 1,
        "transition mineral-reducing": 2,
        "transition mineral reducing": 2,
        "new materials replacing transition minerals": 3,
        "more responsible landbased mining": 4,
        "circular minerals": 5,
        "urban mining": 5,
        "mining-free transition minerals": 6,
        "mining free transition minerals": 6,
    }
    lower = text.lower()
    matched = {number for keyword, number in keywords.items() if keyword in lower}
    return len(matched)


def safe_percentage(numerator: int, denominator: int) -> int:
    return round((numerator / denominator) * 100) if denominator else 0


def ordered_counts(
    series: pd.Series,
    preferred_order: Sequence[str] | None = None,
) -> list[tuple[str, int]]:
    counts = series[series.str.strip().ne("")].value_counts().to_dict()
    result: list[tuple[str, int]] = []

    if preferred_order:
        for label in preferred_order:
            result.append((label, int(counts.pop(label, 0))))

    result.extend(
        sorted(((str(label), int(value)) for label, value in counts.items()), key=lambda x: (-x[1], x[0]))
    )
    return result


def normalize_country_name(value: str) -> str:
    """Normalize common country-name variants while allowing new countries."""
    country = re.sub(r"\s+", " ", str(value)).strip()
    if not country:
        return ""

    alias = COUNTRY_NAME_ALIASES.get(country.casefold())
    if alias:
        return alias

    # Preserve normal names, but clean accidental all-lowercase or all-uppercase entries.
    if country.islower() or country.isupper():
        return country.title()
    return country


def country_counts(df: pd.DataFrame) -> list[tuple[str, int]]:
    countries = df["HQ Country"].map(normalize_country_name)
    countries = countries[(countries != "") & (countries.str.casefold() != "european union")]
    counts = countries.value_counts().to_dict()
    return sorted(
        ((str(country), int(count)) for country, count in counts.items()),
        key=lambda item: (-item[1], item[0]),
    )


def apply_filters(df: pd.DataFrame, year: int, region: str) -> pd.DataFrame:
    filtered = df.copy()
    established = pd.to_numeric(filtered["Year Established"], errors="coerce")
    filtered = filtered[established.isna() | (established <= year)]

    if region != "All Regions":
        filtered = filtered[filtered["Region"].str.strip() == region]

    return filtered.reset_index(drop=True)


# -----------------------------------------------------------------------------
# HTML and chart helpers
# -----------------------------------------------------------------------------
def render_html(content: str) -> None:
    """Render compact HTML without Markdown treating indentation as code."""
    cleaned_html = textwrap.dedent(content).strip()
    cleaned_html = re.sub(r">\s+<", "><", cleaned_html)
    st.markdown(cleaned_html, unsafe_allow_html=True)


def svg_icon(name: str) -> str:
    icons = {
        "building": """
            <path d="M3 9.5 12 4l9 5.5"/><path d="M5 10h14"/>
            <path d="M6.5 10v8M10 10v8M14 10v8M17.5 10v8"/><path d="M4 19h16"/>
        """,
        "pin": """
            <path d="M12 21s6-6.1 6-11a6 6 0 1 0-12 0c0 4.9 6 11 6 11Z"/>
            <circle cx="12" cy="10" r="2.2"/>
        """,
        "rocket": """
            <path d="M14.5 4.2c2.3-1.1 4.6-.9 5.3-.7.2.7.4 3-0.7 5.3l-5.6 5.6-4-4 5-6.2Z"/>
            <path d="m9.5 10.5-3 .7-2.7 2.7 4.2.2M13.5 14.5l-.7 3-2.7 2.7-.2-4.2"/>
            <circle cx="16.2" cy="7.2" r="1.3"/><path d="M6.2 17.8c-1.5.3-2.6 1.4-3 3 1.6-.4 2.7-1.5 3-3Z"/>
        """,
        "layers": """
            <rect x="3" y="5" width="11" height="11" rx="2"/><rect x="10" y="10" width="11" height="11" rx="2"/>
        """,
        "growth": """
            <path d="M4 19v-5h3v5M10.5 19V9h3v10M17 19V5h3v14"/>
            <path d="m4 10 5-4 4 2 6-5"/><path d="M16 3h3v3"/>
        """,
        "globe": """
            <circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9S14.5 18.5 12 21M12 3C9.5 5.5 8.2 8.5 8.2 12s1.3 6.5 3.8 9"/>
        """,
        "female": """
            <circle cx="12" cy="8" r="5"/><path d="M12 13v8M8.5 17h7"/>
        """,
        "users": """
            <circle cx="9" cy="8" r="3"/><circle cx="16.5" cy="9" r="2.4"/>
            <path d="M3.8 19c.4-4 2.4-6 5.2-6s4.8 2 5.2 6M14.2 14.2c3.3-.5 5.5 1.2 6 4.8"/>
        """,
        "leaf": """
            <path d="M20 4C11 4 5.5 8.2 5.5 14.1c0 3.4 2.4 5.4 5.4 5.4C16.8 19.5 20 12.9 20 4Z"/>
            <path d="M4 21c2.4-5.7 6.7-9.1 12.6-11.3"/>
        """,
    }
    body = icons.get(name, icons["globe"])
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{body}</svg>'
    )


def metric_card(value: int, label: str, detail: str, icon: str) -> str:
    safe_label = html.escape(label)
    safe_detail = html.escape(detail) if detail else "&nbsp;"

    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-icon">{svg_icon(icon)}</div>'
        f'<div class="kpi-content">'
        f'<div class="kpi-value">{value:,}</div>'
        f'<div class="kpi-label">{safe_label}</div>'
        f'<div class="kpi-detail">{safe_detail}</div>'
        f'</div>'
        f'</div>'
    )


def section_title(title: str) -> None:
    render_html(f'<div class="section-title">{html.escape(title)}</div>')


def progress_rows(
    items: Iterable[tuple[str, int]],
    maximum: int | None = None,
) -> str:
    item_list = list(items)
    max_value = (
        maximum
        if maximum is not None
        else max((value for _, value in item_list), default=0)
    )

    rows: list[str] = []
    for label, value in item_list:
        width_percentage = (value / max_value * 100) if max_value else 0
        safe_label = html.escape(label)
        rows.append(
            f'<div class="progress-row">'
            f'<div class="progress-label" title="{safe_label}">{safe_label}</div>'
            f'<div class="progress-track">'
            f'<div class="progress-fill" style="width:{width_percentage:.2f}%;"></div>'
            f'</div>'
            f'<div class="progress-value">{value:,}</div>'
            f'</div>'
        )

    return '<div class="progress-list">' + "".join(rows) + '</div>'


def country_progress_rows(items: Sequence[tuple[str, int]]) -> str:
    maximum = max((value for _, value in items), default=0)
    rows: list[str] = []

    for country, value in items:
        alpha2 = COUNTRY_CODES.get(country, (country[:2].upper(), ""))[0]
        width_percentage = (value / maximum * 100) if maximum else 0
        safe_country = html.escape(country)

        rows.append(
            f'<div class="country-row">'
            f'<div class="country-code">{html.escape(alpha2)}</div>'
            f'<div class="country-name" title="{safe_country}">{safe_country}</div>'
            f'<div class="progress-track">'
            f'<div class="progress-fill" style="width:{width_percentage:.2f}%;"></div>'
            f'</div>'
            f'<div class="progress-value">{value:,}</div>'
            f'</div>'
        )

    return "".join(rows)


def diversity_card(value: int, percentage: int, label: str, icon: str) -> str:
    return (
        f'<div class="diversity-mini">'
        f'<div class="diversity-icon">{svg_icon(icon)}</div>'
        f'<div>'
        f'<div class="diversity-number">{value:,}</div>'
        f'<div class="diversity-percent">{percentage}% of all solutions</div>'
        f'<div class="diversity-label">{html.escape(label)}</div>'
        f'</div>'
        f'</div>'
    )


def organisation_donut(items: Sequence[tuple[str, int]], total: int) -> go.Figure:
    labels = [ORG_TYPE_SHORT.get(label, label) for label, _ in items]
    values = [value for _, value in items]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            sort=False,
            direction="clockwise",
            marker={"colors": ORG_COLORS[: len(labels)], "line": {"color": "#0a3656", "width": 0.7}},
            textinfo="none",
            hovertemplate="%{label}: %{value}<extra></extra>",
        )
    )
    fig.update_layout(
        height=235,
        margin={"l": 0, "r": 0, "t": 2, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        annotations=[
            {
                "text": f"<b>{total:,}</b><br><span style='font-size:13px'>Total</span>",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 24, "color": COLORS["accent"]},
                "align": "center",
            }
        ],
    )
    return fig


def organisation_bar(items: Sequence[tuple[str, int]]) -> go.Figure:
    labels = [ORG_TYPE_SHORT.get(label, label).replace(" ", "<br>", 1) if label == "University Spinout" else ORG_TYPE_SHORT.get(label, label) for label, _ in items]
    values = [value for _, value in items]
    max_value = max(values, default=0)

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker={"color": ORG_COLORS[: len(labels)], "line": {"width": 0}},
            hovertemplate="%{x}: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        height=250,
        margin={"l": 35, "r": 8, "t": 5, "b": 42},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.43,
        font={"family": "Arial, sans-serif", "size": 11, "color": COLORS["text"]},
        xaxis={
            "showgrid": False,
            "zeroline": False,
            "tickfont": {"size": 10, "color": "#d6e4ee"},
            "fixedrange": True,
        },
        yaxis={
            "range": [0, max(40, max_value + 5)],
            "dtick": 10,
            "showgrid": False,
            "zeroline": True,
            "zerolinecolor": "#5d7890",
            "tickfont": {"size": 10, "color": "#c7d7e3"},
            "fixedrange": True,
        },
    )
    return fig


def global_map(items: Sequence[tuple[str, int]]) -> go.Figure:
    """Build the map from country names instead of a fixed country dictionary.

    This allows newly added countries in Google Sheets to appear automatically.
    Plotly resolves standard country names through locationmode='country names'.
    """
    mapped = [
        (normalize_country_name(country), count)
        for country, count in items
        if normalize_country_name(country)
    ]

    if not mapped:
        return go.Figure()

    fig = go.Figure(
        go.Choropleth(
            locations=[country for country, _ in mapped],
            locationmode="country names",
            z=[count for _, count in mapped],
            text=[country for country, _ in mapped],
            customdata=[count for _, count in mapped],
            colorscale=[
                [0.0, "#72d5b3"],
                [0.35, "#56cfaa"],
                [0.70, "#32bd91"],
                [1.0, "#1fa879"],
            ],
            showscale=False,
            marker_line_color="#153f5f",
            marker_line_width=0.45,
            hovertemplate="%{text}: %{customdata} solutions<extra></extra>",
        )
    )
    fig.update_geos(
        projection_type="natural earth",
        showframe=False,
        showcoastlines=False,
        showcountries=True,
        countrycolor="#173d5b",
        showland=True,
        landcolor="#082c48",
        showocean=True,
        oceancolor="#032641",
        showlakes=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=320,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        uirevision=None,
    )
    return fig


def country_chips(items: Sequence[tuple[str, int]]) -> str:
    chips = []
    for country, _ in items:
        alpha2 = COUNTRY_CODES.get(country, (country[:2].upper(), ""))[0]
        chips.append(
            f'<span class="country-chip"><b>{html.escape(alpha2)}</b>{html.escape(country)}</span>'
        )
    return f'<div class="country-chips">{"".join(chips)}</div>'


def chart_config() -> dict:
    return {
        "displayModeBar": False,
        "responsive": True,
        "scrollZoom": False,
    }


# -----------------------------------------------------------------------------
# Dashboard rendering
# -----------------------------------------------------------------------------
def render_dashboard(df: pd.DataFrame) -> None:
    regions = sorted(
        region for region in df["Region"].str.strip().unique().tolist() if region
    )
    established_years = pd.to_numeric(df["Year Established"], errors="coerce").dropna()
    years = sorted({REPORT_YEAR, *established_years.astype(int).tolist()}, reverse=True)

    with st.container(key="hero"):
        title_column, filter_column = st.columns([4.7, 1.35], gap="large")
        with title_column:
            render_html(
                f"""
                <div class="hero-title">Guardians of the Arctic</div>
                <div class="hero-subtitle">United for the Rights of Future Generations</div>
                <div class="hero-guide">Global Guide {REPORT_YEAR}</div>
                """
            )
        with filter_column:
            selected_year = st.selectbox(
                "Year",
                options=years,
                index=years.index(REPORT_YEAR),
                key="year_filter",
            )
            selected_region = st.selectbox(
                "Region",
                options=["All Regions", *regions],
                index=0,
                key="region_filter",
            )

    filtered = apply_filters(df, selected_year, selected_region)
    total = len(filtered)

    high_maturity = int(filtered["TRL"].map(is_high_maturity).sum())
    multi_category = int(filtered["Solution Categories"].map(category_count).ge(2).sum())
    growth_stage = int(
        filtered["Organisation Type"].isin(["Startup", "Scaleup"]).sum()
    )
    region_total = int(filtered["Region"].str.strip().replace("", pd.NA).nunique())

    kpi_data = [
        (total, "Total Organizations", "", "building"),
        (region_total, "Global Regions", "", "pin"),
        (
            high_maturity,
            "High-Maturity Solutions",
            f"{safe_percentage(high_maturity, total)}% at TRL 6 to 9",
            "rocket",
        ),
        (
            multi_category,
            "Multi-Category Solutions",
            f"{safe_percentage(multi_category, total)}% address multiple solution areas",
            "layers",
        ),
        (growth_stage, "Growth-Stage Innovators", "", "growth"),
    ]

    kpi_columns = st.columns(5, gap="small")
    for column, (value, label, detail, icon) in zip(kpi_columns, kpi_data):
        with column:
            render_html(metric_card(value, label, detail, icon))

    render_html('<div style="height:0.5rem"></div>')

    org_items = ordered_counts(filtered["Organisation Type"], ORG_TYPE_ORDER)
    region_items = ordered_counts(filtered["Region"])

    top_left, top_right = st.columns([0.95, 1.08], gap="small")
    with top_left:
        with st.container(key="org-card"):
            section_title("Organisation Type")
            donut_column, legend_column = st.columns([0.92, 1.12], gap="small")
            with donut_column:
                st.plotly_chart(
                    organisation_donut(org_items, total),
                    width="stretch",
                    config=chart_config(),
                    key="org_donut",
                )
            with legend_column:
                legend_html: list[str] = []
                for index, (label, value) in enumerate(org_items):
                    color = ORG_COLORS[index % len(ORG_COLORS)]
                    display_label = html.escape(ORG_TYPE_SHORT.get(label, label))
                    legend_html.append(
                        f'<div class="legend-row">'
                        f'<span class="legend-swatch" style="background-color:{color};"></span>'
                        f'<span>{display_label}</span>'
                        f'<span class="legend-value">{value:,}</span>'
                        f'</div>'
                    )
                render_html(
                    '<div class="legend-wrap">' + "".join(legend_html) + '</div>'
                )

    with top_right:
        with st.container(key="regions-card"):
            section_title("Global Regions")
            if region_items:
                render_html(progress_rows(region_items))
            else:
                render_html('<div class="empty-note">No region data for this filter.</div>')

    render_html('<div style="height:0.45rem"></div>')

    diversity_text = filtered["Diversity"].str.lower()
    global_south = int(diversity_text.str.contains("global south", regex=False).sum())
    female_led = int(diversity_text.str.contains("female founded / lead", regex=False).sum())
    indigenous = int(
        diversity_text.str.contains("indigenous / small island state", regex=False).sum()
    )

    middle_left, middle_right = st.columns([1.08, 0.92], gap="small")
    with middle_left:
        with st.container(key="diversity-card"):
            section_title("Diversity & Inclusion")
            diversity_columns = st.columns(3, gap="small")
            diversity_data = [
                (
                    global_south,
                    safe_percentage(global_south, total),
                    "Global South founded or led",
                    "globe",
                ),
                (
                    female_led,
                    safe_percentage(female_led, total),
                    "Female founded or led",
                    "female",
                ),
                (
                    indigenous,
                    safe_percentage(indigenous, total),
                    "Indigenous & Small Island States",
                    "users",
                ),
            ]
            for column, item in zip(diversity_columns, diversity_data):
                with column:
                    render_html(diversity_card(*item))

            render_html(
                progress_rows(
                    [
                        ("Global South", global_south),
                        ("Female founded / led", female_led),
                        ("Indigenous & Small Island States", indigenous),
                    ],
                    maximum=max(global_south, female_led, indigenous, 1),
                )
            )

    with middle_right:
        with st.container(key="distribution-card"):
            section_title("Distribution by Organisation Type")
            st.plotly_chart(
                organisation_bar(org_items),
                width="stretch",
                config=chart_config(),
                key="org_bar",
            )

    render_html(
        f"""
        <div class="footer-strip">
            <div class="footer-message">{svg_icon('leaf')}<span>Empowering organizations worldwide to protect the Arctic and uphold the rights of future generations.</span></div>
            <div>* Companies may appear in multiple categories</div>
        </div>
        """
    )

    countries = country_counts(filtered)
    top_countries = countries[:10]
    country_total = len(countries)

    bottom_left, bottom_right = st.columns([0.84, 1.16], gap="small")
    with bottom_left:
        with st.container(key="countries-card"):
            section_title("Top 10 Countries by Number of Solutions")
            if top_countries:
                render_html(country_progress_rows(top_countries))
                remaining = max(country_total - len(top_countries), 0)
                if remaining:
                    remaining_counts = [count for _, count in countries[10:]]
                    low = min(remaining_counts, default=0)
                    high = max(remaining_counts, default=0)
                    range_text = f"{low}-{high}" if low != high else str(low)
                    render_html(
                        f'<div class="country-note">{remaining} additional countries with {range_text} solutions each</div>'
                    )
            else:
                render_html('<div class="empty-note">No country data for this filter.</div>')

    with bottom_right:
        with st.container(key="map-card"):
            section_title(f"Global Presence - {country_total} Countries Represented")
            if countries:
                st.plotly_chart(
                    global_map(countries),
                    width="stretch",
                    config=chart_config(),
                    key="country_map",
                )
                render_html(country_chips(countries))
            else:
                render_html('<div class="empty-note">No mapped countries for this filter.</div>')


@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS}s")
def render_live_dashboard() -> None:
    """Read Google Sheets fresh and redraw the dashboard on a fixed interval."""
    try:
        data = load_google_sheet(
            SPREADSHEET_NAME,
            SPREADSHEET_ID,
            WORKSHEET_NAME,
        )
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.info(
            "Place your service-account JSON file beside app.py as credentials.json, "
            "or set GOOGLE_SERVICE_ACCOUNT_FILE to its path."
        )
        st.stop()
    except gspread.WorksheetNotFound:
        st.error(
            f'Worksheet tab "{WORKSHEET_NAME}" was not found in "{SPREADSHEET_NAME}".'
        )
        st.info(
            "The uploaded workbook uses the tab name All Mapped Solutions. "
            "Change GOOGLE_WORKSHEET_NAME if your Google Sheet uses a different tab name."
        )
        st.stop()
    except gspread.SpreadsheetNotFound:
        st.error(
            "The spreadsheet could not be opened. Confirm the spreadsheet name or ID, "
            "and share it with the service account client_email."
        )
        st.stop()
    except Exception as exc:
        st.error("The Google Sheet could not be loaded.")
        st.code(f"{type(exc).__name__}: {exc}")
        st.stop()

    render_dashboard(data)


def main() -> None:
    configure_page()
    render_live_dashboard()


if __name__ == "__main__":
    main()