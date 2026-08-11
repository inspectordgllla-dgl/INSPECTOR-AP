import os
import calendar
from datetime import datetime, date

import pandas as pd
from flask import Flask, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
# Google Sheet-ஐ "Anyone with the link - Viewer" எனப் பகிர்ந்திருக்க வேண்டும்.
SHEET_ID = os.environ.get("SHEET_ID", "1R0h8KZLz3fKsEYEb4PHDNwzQGD75Lc7qVrFk4I_aDy4")
LIBRARY_SHEET_NAME = os.environ.get("LIBRARY_SHEET_NAME", "Sheet1")
HOLIDAY_SHEET_NAME = os.environ.get("HOLIDAY_SHEET_NAME", "HOLIDAYS")


def sheet_csv_url(sheet_name: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={sheet_name}"
    )


TAMIL_WEEKDAYS = ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"]

TAMIL_MONTHS = {
    1: "ஜனவரி", 2: "பிப்ரவரி", 3: "மார்ச்", 4: "ஏப்ரல்", 5: "மே", 6: "ஜூன்",
    7: "ஜூலை", 8: "ஆகஸ்ட்", 9: "செப்டம்பர்", 10: "அக்டோபர்", 11: "நவம்பர்", 12: "டிசம்பர்",
}

WORK_TYPES = [
    "நூலகங்கள் பார்வை",
    "அலுவலகப் பணி",
    "நூலகங்கள் ஆய்வு",
]

SURVEY_YEARS = ["2024-2025", "2025-2026", "2027-2028"]


# ---------------------------------------------------------------------------
# DATA FETCHING (Google Sheet -> CSV)
# ---------------------------------------------------------------------------
def get_libraries():
    """Sheet1: A column = நூலக வகை, B column = நூலகம் பெயர் (A2:B175)."""
    try:
        df = pd.read_csv(sheet_csv_url(LIBRARY_SHEET_NAME))
        df.columns = [str(c).strip() for c in df.columns]
        type_col = df.columns[0]
        name_col = df.columns[1]
        libs = []
        for _, row in df.iterrows():
            ltype = str(row.get(type_col, "")).strip()
            lname = str(row.get(name_col, "")).strip()
            if lname and lname.lower() != "nan":
                libs.append({"type": ltype if ltype.lower() != "nan" else "", "name": lname})
        return libs
    except Exception as exc:  # noqa: BLE001
        print("Library fetch error:", exc)
        return []


def _parse_date(raw: str):
    raw = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def get_holidays():
    """HOLIDAYS sheet: DATE (dd/mm/yyyy), Holiday Name, Holiday day."""
    holidays = {}
    try:
        df = pd.read_csv(sheet_csv_url(HOLIDAY_SHEET_NAME))
        df.columns = [str(c).strip() for c in df.columns]
        if df.shape[1] < 1:
            return holidays
        date_col = df.columns[0]
        name_col = df.columns[1] if df.shape[1] > 1 else None
        for _, row in df.iterrows():
            raw_date = str(row.get(date_col, "")).strip()
            if not raw_date or raw_date.lower() == "nan":
                continue
            d = _parse_date(raw_date)
            if not d:
                continue
            hname = str(row.get(name_col, "")).strip() if name_col else ""
            if hname.lower() == "nan":
                hname = ""
            holidays[d.isoformat()] = hname
    except Exception as exc:  # noqa: BLE001
        print("Holiday fetch error:", exc)
    return holidays


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    libraries = get_libraries()
    holidays = get_holidays()

    days_in_month = calendar.monthrange(year, month)[1]
    rows = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        holiday_name = holidays.get(d.isoformat())
        rows.append({
            "key": d.isoformat(),
            "date_disp": d.strftime("%d-%m-%Y"),
            "weekday": TAMIL_WEEKDAYS[d.weekday()],
            "is_sunday": d.weekday() == 6,
            "holiday_name": holiday_name,
        })

    return render_template(
        "index.html",
        rows=rows,
        libraries=libraries,
        work_types=WORK_TYPES,
        survey_years=SURVEY_YEARS,
        year=year,
        month=month,
        month_name=TAMIL_MONTHS[month],
        tamil_months=TAMIL_MONTHS,
        years_range=list(range(today.year - 1, today.year + 2)),
    )


@app.route("/generate", methods=["POST"])
def generate():
    year = int(request.form.get("year"))
    month = int(request.form.get("month"))
    days_in_month = calendar.monthrange(year, month)[1]

    plan = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        key = d.isoformat()
        work_type = (request.form.get(f"work_{key}") or "").strip()
        library_name = (request.form.get(f"library_{key}") or "").strip()
        survey_year = (request.form.get(f"survey_year_{key}") or "").strip()

        place_display = work_type
        if work_type == "நூலகங்கள் ஆய்வு":
            extra = []
            if library_name:
                extra.append(library_name)
            if survey_year:
                extra.append(f"({survey_year})")
            if extra:
                place_display = f"{work_type} - {' '.join(extra)}"
        elif work_type == "நூலகங்கள் பார்வை" and library_name:
            place_display = f"{work_type} - {library_name}"

        plan.append({
            "date_disp": d.strftime("%d-%m-%Y"),
            "weekday": TAMIL_WEEKDAYS[d.weekday()],
            "place": place_display or "-",
        })

    return render_template(
        "result.html",
        plan=plan,
        month_name=TAMIL_MONTHS[month],
        year=year,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
