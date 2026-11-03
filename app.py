import os
import re
import calendar
from urllib.parse import quote
from datetime import datetime, date

import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, Response, abort
from flask_sqlalchemy import SQLAlchemy

from reportlab.lib.pagesizes import legal, portrait
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from tamil_text import TamilText

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dindigul-library-tour-planner-dev-key")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
# Google Sheet-ஐ "Anyone with the link - Viewer" எனப் பகிர்ந்திருக்க வேண்டும்.
SHEET_ID = os.environ.get("SHEET_ID", "1R0h8KZLz3fKsEYEb4PHDNwzQGD75Lc7qVrFk4I_aDy4")
LIBRARY_SHEET_NAME = os.environ.get("LIBRARY_SHEET_NAME", "Sheet1")
HOLIDAY_SHEET_NAME = os.environ.get("HOLIDAY_SHEET_NAME", "HOLIDAYS")

# கடிதத்தில் நிரந்தரமாகத் தோன்றும் விவரங்கள் — தேவைப்பட்டால் இங்கே மாற்றிக்கொள்ளவும்.
LETTER_SENDER_NAME = os.environ.get("LETTER_SENDER_NAME", "திரு.மு.லெ.முத்து")
LETTER_SENDER_DESIGNATION = os.environ.get("LETTER_SENDER_DESIGNATION", "நூலக ஆய்வாளர்")
LETTER_SENDER_OFFICE_LINE1 = os.environ.get("LETTER_SENDER_OFFICE_LINE1", "மாவட்ட நூலக அலுவலகம்,")
LETTER_SENDER_OFFICE_LINE2 = os.environ.get("LETTER_SENDER_OFFICE_LINE2", "திண்டுக்கல் – 624 003")
LETTER_RECEIVER_DESIGNATION = os.environ.get("LETTER_RECEIVER_DESIGNATION", "மாவட்ட நூலக அலுவலர்")
LETTER_RECEIVER_OFFICE_LINE1 = os.environ.get("LETTER_RECEIVER_OFFICE_LINE1", "மாவட்ட நூலக அலுவலகம்,")
LETTER_RECEIVER_OFFICE_LINE2 = os.environ.get("LETTER_RECEIVER_OFFICE_LINE2", "திண்டுக்கல்")
DISTRICT_NAME = os.environ.get("DISTRICT_NAME", "திண்டுக்கல்")

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
db_url = os.environ.get("DATABASE_URL", "sqlite:///tour_planner.db")
# Render வழங்கும் URL "postgres://" என தொடங்கும்; SQLAlchemy 1.4+ க்கு "postgresql://" தேவை.
# SQLAlchemy 2.1+ "postgresql://" என்றால் psycopg3 ஐ தேடும்; நாம் psycopg2 பயன்படுத்துவதால்
# driver-ஐ வெளிப்படையாகக் குறிப்பிடுகிறோம்.
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Neon idle ஆனபின் connection துண்டிக்கப்படலாம்; ஒவ்வொரு முறையும் முதலில் சோதிக்கும்.
app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"pool_pre_ping": True, "pool_recycle": 280})
db = SQLAlchemy(app)


class TourPlan(db.Model):
    __tablename__ = "tour_plans"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    file_number = db.Column(db.String(100))
    letter_date = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    days = db.relationship(
        "TourPlanDay", backref="plan", cascade="all, delete-orphan",
        order_by="TourPlanDay.day_date",
    )

    __table_args__ = (db.UniqueConstraint("year", "month", name="uq_year_month"),)


class TourPlanDay(db.Model):
    __tablename__ = "tour_plan_days"
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("tour_plans.id"), nullable=False)
    day_date = db.Column(db.Date, nullable=False)
    weekday = db.Column(db.String(20), nullable=False)
    day_type = db.Column(db.String(30), nullable=False)  # government_holiday / weekly_off / second_saturday / work
    work_type = db.Column(db.String(100))
    library_name = db.Column(db.String(255))
    survey_year = db.Column(db.String(20))
    leave_type = db.Column(db.String(50))
    place_display = db.Column(db.String(500), nullable=False)

    __table_args__ = (db.UniqueConstraint("plan_id", "day_date", name="uq_plan_date"),)


class ActualTourPlan(db.Model):
    __tablename__ = "actual_tour_plans"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    days = db.relationship(
        "ActualTourPlanDay", backref="plan", cascade="all, delete-orphan",
        order_by="ActualTourPlanDay.day_date",
    )

    __table_args__ = (db.UniqueConstraint("year", "month", name="uq_actual_year_month"),)


class ActualTourPlanDay(db.Model):
    __tablename__ = "actual_tour_plan_days"
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("actual_tour_plans.id"), nullable=False)
    day_date = db.Column(db.Date, nullable=False)
    weekday = db.Column(db.String(20), nullable=False)
    day_type = db.Column(db.String(30), nullable=False)  # government_holiday / weekly_off / second_saturday / work
    has_visit = db.Column(db.Boolean, default=False, nullable=False)
    visit_libraries = db.Column(db.Text)      # '\n' separated நூலகம் பெயர்கள் (பார்வை)
    has_survey = db.Column(db.Boolean, default=False, nullable=False)
    survey_year = db.Column(db.String(20))
    survey_libraries = db.Column(db.Text)     # '\n' separated நூலகம் பெயர்கள் (ஆய்வு)
    has_office = db.Column(db.Boolean, default=False, nullable=False)
    has_leave = db.Column(db.Boolean, default=False, nullable=False)
    leave_type = db.Column(db.String(50))
    time_from = db.Column(db.String(20))
    time_to = db.Column(db.String(20))
    place_display = db.Column(db.Text, nullable=False)   # காட்சிக்கான உரை ('\n' கோடுகள்)

    __table_args__ = (db.UniqueConstraint("plan_id", "day_date", name="uq_actual_plan_date"),)

    @property
    def content_lines(self):
        return (self.place_display or "-").split("\n")

    @property
    def visit_library_list(self):
        return [x for x in (self.visit_libraries or "").split("\n") if x]

    @property
    def survey_library_list(self):
        return [x for x in (self.survey_libraries or "").split("\n") if x]

    @property
    def time_display(self):
        parts = []
        if self.time_from:
            parts.append(f"{self.time_from} மு.ப.")
        if self.time_to:
            parts.append(f"{self.time_to} பி.ப")
        return " ".join(parts)


class InspectionIntimation(db.Model):
    """ஆய்வு தகவல் நூலகருக்கு அனுப்புதல் — ஒவ்வொரு அறிவிப்பு கடிதப் பதிவு."""
    __tablename__ = "inspection_intimations"
    id = db.Column(db.Integer, primary_key=True)
    file_number = db.Column(db.String(100), nullable=False)      # ந.க.எண்.
    letter_date = db.Column(db.Date, nullable=False)             # நாள்
    library_type = db.Column(db.String(100))                     # நூலக வகை
    library_name = db.Column(db.String(255), nullable=False)     # நூலகம் பெயர்
    survey_year = db.Column(db.String(20), nullable=False)       # ஆய்வு ஆண்டு
    inspection_date = db.Column(db.Date, nullable=False)         # ஆய்வு நடைபெறவுள்ள நாள்
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Library(db.Model):
    """நூலகங்கள் — வகை, பெயர், முகவரி, நூலகர், தொலைபேசி (Neon DB-ல் சேமிப்பு)."""
    __tablename__ = "libraries"
    id = db.Column(db.Integer, primary_key=True)
    library_type = db.Column(db.String(100))
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.Text)
    librarian_name = db.Column(db.String(255))
    phone = db.Column(db.String(100))


with app.app_context():
    db.create_all()


TAMIL_WEEKDAYS = ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"]

TAMIL_MONTHS = {
    1: "ஜனவரி", 2: "பிப்ரவரி", 3: "மார்ச்", 4: "ஏப்ரல்", 5: "மே", 6: "ஜூன்",
    7: "ஜூலை", 8: "ஆகஸ்ட்", 9: "செப்டம்பர்", 10: "அக்டோபர்", 11: "நவம்பர்", 12: "டிசம்பர்",
}

WORK_TYPES = [
    "நூலகங்கள் பார்வை",
    "அலுவலகப் பணி",
    "நூலகங்கள் ஆய்வு",
    "விடுப்பு",
]

LEAVE_TYPES = [
    "தற்செயல் விடுப்பு",
    "மதவிடுப்பு",
    "ஈட்டிய விடுப்பு",
    "மருத்துவ விடுப்பு",
]

SURVEY_YEARS = ["2024-2025", "2025-2026", "2027-2028"]

# சனி (5) / ஞாயிறு (6) நாட்களில் "அலுவலகப் பணி" விருப்பம் காட்டப்படாது.
OFFICE_WORK_EXCLUDED_WEEKDAYS = (5, 6)

# ஒரு மாதத்திற்கான, ஏற்கனவே சேமிக்கப்பட்ட உத்தேசப் பயணத் திட்டம் மற்றும்
# உண்மைப் பயணத் திட்டத்தை அழிக்க தேவைப்படும் கடவுச்சொல்.
DELETE_PASSWORD = os.environ.get("DELETE_PASSWORD", "Dlodgl@123")


def work_types_for_day(d):
    """கொடுக்கப்பட்ட தேதி சனி/ஞாயிறு எனில் 'அலுவலகப் பணி' விருப்பத்தை நீக்கிய
    பட்டியலைத் திருப்பும்."""
    if d and d.weekday() in OFFICE_WORK_EXCLUDED_WEEKDAYS:
        return [wt for wt in WORK_TYPES if wt != "அலுவலகப் பணி"]
    return WORK_TYPES

# உண்மைப் பயணத் திட்டம் — "எடுத்துக் கொண்ட நேரம்" தேர்வுகள்
TIME_FROM_OPTIONS = ["08.00", "09.00"]
TIME_TO_OPTIONS = ["05.00", "06.00", "07.00", "08.00"]
MAX_LIBRARIES_PER_DAY = 6
MAX_PLANNED_SURVEY_LIBRARIES = 2  # உத்தேசப் பயணத் திட்டத்தில் 'ஆய்வு'க்கு அதிகபட்ச நூலகங்கள்

# "அலுவலகப் பணி" தேர்வு செய்யும்போது நேரம் தேர்வு காட்டப்படாது — இந்த
# நிலையான இயல்புநேரம் தானாகப் பயன்படுத்தப்படும்.
OFFICE_DEFAULT_TIME_FROM = "09.45"
OFFICE_DEFAULT_TIME_TO = "05.45"


# ---------------------------------------------------------------------------
# DATA FETCHING (Google Sheet -> CSV)
# ---------------------------------------------------------------------------
def sheet_csv_url(sheet_name: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={sheet_name}"
    )


def get_libraries():
    """நூலகப் பட்டியல்: DB-ல் பதிவுகள் இருந்தால் அதுவே; இல்லையெனில் Google Sheet."""
    try:
        rows = Library.query.order_by(Library.id).all()
        if rows:
            return [{"type": (r.library_type or "").strip(), "name": r.name} for r in rows]
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        print("Library DB read error:", exc)
    return _get_libraries_from_sheet()


def _get_libraries_from_sheet():
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
# DAY-TYPE CLASSIFICATION (அரசு விடுமுறை / வார விடுமுறை / 2ம் சனி / வேலை நாள்)
# ---------------------------------------------------------------------------
def is_second_saturday(d: date) -> bool:
    if d.weekday() != 5:  # Saturday
        return False
    saturdays_so_far = sum(
        1 for day in range(1, d.day + 1)
        if date(d.year, d.month, day).weekday() == 5
    )
    return saturdays_so_far == 2


def classify_day(d: date, holidays: dict):
    """Returns (day_type, auto_place_display) — auto_place_display is None for work days."""
    key = d.isoformat()
    if key in holidays:
        name = holidays[key]
        display = f"அரசு விடுமுறை - {name}" if name else "அரசு விடுமுறை"
        return "government_holiday", display
    if d.weekday() == 4:  # Friday
        return "weekly_off", "வார விடுமுறை"
    if is_second_saturday(d):
        return "second_saturday", "இரண்டாம் சனிக்கிழமை அரசு விடுமுறை"
    return "work", None


def build_place_display(work_type, library_names, survey_year, leave_type=None):
    if work_type == "நூலகங்கள் ஆய்வு":
        if isinstance(library_names, str):
            library_names = [library_names] if library_names else []
        parts = [work_type]
        extra = []
        if library_names:
            extra.append(", ".join(library_names))
        if survey_year:
            extra.append(f"({survey_year})")
        if extra:
            parts.append("- " + " ".join(extra))
        return " ".join(parts)
    if work_type == "விடுப்பு":
        return f"விடுப்பு - {leave_type}" if leave_type else "விடுப்பு"
    return work_type or "-"


def build_actual_content(has_survey, survey_year, survey_libs, has_visit, visit_libs, has_office,
                          has_leave=False, leave_type=None):
    """உண்மைப் பயணத் திட்ட நாளின் 'ஆய்வு/படிவம்' நெடுவரிசைக்கான பல-வரி உரையை
    கட்டமைக்கிறது (மாடல் கடிதத்தில் உள்ளது போன்று ஆய்வு பிரிவு முதலிலும்,
    பார்வை பிரிவு பின்னாலும்)."""
    lines = []
    if has_survey and survey_libs:
        lines.append(f"ஆய்வு {survey_year}" if survey_year else "ஆய்வு")
        for i, lib in enumerate(survey_libs, start=1):
            lines.append(f"    {i}.{lib}")
    if has_visit and visit_libs:
        if lines:
            lines.append("")
        lines.append("பார்வை")
        for i, lib in enumerate(visit_libs, start=1):
            lines.append(f"    {i}.{lib}")
    if has_office:
        if lines:
            lines.append("")
        lines.append("அலுவலகப் பணி")
    if has_leave:
        if lines:
            lines.append("")
        lines.append(f"விடுப்பு - {leave_type}" if leave_type else "விடுப்பு")
    return "\n".join(lines) if lines else "-"


def get_or_create_plan(year, month):
    plan = TourPlan.query.filter_by(year=year, month=month).first()
    if not plan:
        plan = TourPlan(year=year, month=month)
        db.session.add(plan)
        db.session.commit()
    return plan


def cascade_autofill(plan, holidays):
    """plan-இல் இதுவரை பதிவாகாத நாட்களை, work day வரும் வரை தானாக நிரப்பும்."""
    days_in_month = calendar.monthrange(plan.year, plan.month)[1]
    filled_dates = {d.day_date for d in plan.days}
    changed = False
    next_pending = None

    for day_num in range(1, days_in_month + 1):
        d = date(plan.year, plan.month, day_num)
        if d in filled_dates:
            continue
        day_type, auto_display = classify_day(d, holidays)
        if day_type == "work":
            next_pending = d
            break
        row = TourPlanDay(
            plan_id=plan.id,
            day_date=d,
            weekday=TAMIL_WEEKDAYS[d.weekday()],
            day_type=day_type,
            place_display=auto_display,
        )
        db.session.add(row)
        changed = True

    if changed:
        db.session.commit()

    days_in_month_total = calendar.monthrange(plan.year, plan.month)[1]
    if next_pending is None and len(plan.days) == days_in_month_total:
        if not plan.is_complete:
            plan.is_complete = True
            db.session.commit()

    return next_pending


def find_duplicate_survey_library(plan, survey_libs, exclude_day_id=None):
    """plan-இல் உள்ள மற்ற நாட்களில் ஏற்கனவே 'ஆய்வு' பதிவாகியுள்ள நூலகங்களுடன்
    survey_libs-ல் ஏதேனும் மோதுகிறதா எனச் சரிபார்க்கும். மோதல் இருந்தால்
    (நூலகம் பெயர், அந்த நாள்) திருப்பும், இல்லையெனில் (None, None)."""
    wanted = set(survey_libs or [])
    if not wanted:
        return None, None
    for day in plan.days:
        if exclude_day_id and day.id == exclude_day_id:
            continue
        if not day.has_survey:
            continue
        overlap = wanted & set(day.survey_library_list)
        if overlap:
            return next(iter(overlap)), day.day_date
    return None, None


def get_or_create_actual_plan(year, month):
    plan = ActualTourPlan.query.filter_by(year=year, month=month).first()
    if not plan:
        plan = ActualTourPlan(year=year, month=month)
        db.session.add(plan)
        db.session.commit()
    return plan


def cascade_autofill_actual(plan, holidays):
    """actual plan-இல் இதுவரை பதிவாகாத நாட்களை, வேலை நாள் வரும் வரை தானாக நிரப்பும்."""
    days_in_month = calendar.monthrange(plan.year, plan.month)[1]
    filled_dates = {d.day_date for d in plan.days}
    changed = False
    next_pending = None

    for day_num in range(1, days_in_month + 1):
        d = date(plan.year, plan.month, day_num)
        if d in filled_dates:
            continue
        day_type, auto_display = classify_day(d, holidays)
        if day_type == "work":
            next_pending = d
            break
        row = ActualTourPlanDay(
            plan_id=plan.id,
            day_date=d,
            weekday=TAMIL_WEEKDAYS[d.weekday()],
            day_type=day_type,
            place_display=auto_display,
        )
        db.session.add(row)
        changed = True

    if changed:
        db.session.commit()

    days_in_month_total = calendar.monthrange(plan.year, plan.month)[1]
    if next_pending is None and len(plan.days) == days_in_month_total:
        if not plan.is_complete:
            plan.is_complete = True
            db.session.commit()

    return next_pending


# ---------------------------------------------------------------------------
# ROUTES — DASHBOARD
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ---------------------------------------------------------------------------
# ROUTES — 1. உத்தேசப் பயணத் திட்டம்
# ---------------------------------------------------------------------------
@app.route("/planned", methods=["GET"])
def planned_select():
    today = date.today()
    saved_plans = (
        TourPlan.query.order_by(TourPlan.year.desc(), TourPlan.month.desc()).all()
    )
    return render_template(
        "planned_select.html",
        tamil_months=TAMIL_MONTHS,
        years_range=list(range(today.year - 1, today.year + 2)),
        default_year=today.year,
        default_month=today.month,
        saved_plans=saved_plans,
    )


@app.route("/planned/<int:year>/<int:month>", methods=["GET"])
def planned_view(year, month):
    holidays = get_holidays()
    plan = get_or_create_plan(year, month)
    next_pending = cascade_autofill(plan, holidays)

    libraries = get_libraries()
    filled_days = TourPlan.query.get(plan.id).days  # refreshed relationship

    return render_template(
        "planned_index.html",
        plan=plan,
        filled_days=filled_days,
        next_pending=next_pending,
        libraries=libraries,
        work_types=work_types_for_day(next_pending),
        survey_years=SURVEY_YEARS,
        leave_types=LEAVE_TYPES,
        max_survey_libraries=MAX_PLANNED_SURVEY_LIBRARIES,
        month_name=TAMIL_MONTHS[month],
        year=year,
        month=month,
    )


@app.route("/planned/<int:year>/<int:month>/day", methods=["POST"])
def planned_save_day(year, month):
    plan = get_or_create_plan(year, month)
    day_str = request.form.get("day_date")
    work_type = (request.form.get("work_type") or "").strip()
    library_names = [x.strip() for x in request.form.getlist("library_name") if x.strip()]
    survey_year = (request.form.get("survey_year") or "").strip()
    leave_type = (request.form.get("leave_type") or "").strip()

    try:
        d = datetime.strptime(day_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        flash("தேதி தவறாக உள்ளது.")
        return redirect(url_for("planned_view", year=year, month=month))

    if not work_type:
        flash("பணியிடம் தேர்வு செய்யவும்.")
        return redirect(url_for("planned_view", year=year, month=month))

    if work_type == "அலுவலகப் பணி" and d.weekday() in OFFICE_WORK_EXCLUDED_WEEKDAYS:
        flash("சனி / ஞாயிறு நாட்களில் 'அலுவலகப் பணி' தேர்வு செய்ய முடியாது.")
        return redirect(url_for("planned_view", year=year, month=month))

    if work_type == "நூலகங்கள் ஆய்வு" and (not library_names or not survey_year):
        flash("நூலகங்கள் ஆய்வு-க்கு நூலகம் பெயர் மற்றும் ஆய்வு ஆண்டு கட்டாயம்.")
        return redirect(url_for("planned_view", year=year, month=month))

    if work_type == "நூலகங்கள் ஆய்வு" and len(library_names) > MAX_PLANNED_SURVEY_LIBRARIES:
        flash(f"ஆய்வுக்கு அதிகபட்சம் {MAX_PLANNED_SURVEY_LIBRARIES} நூலகங்கள் மட்டுமே தேர்வு செய்யலாம்.")
        return redirect(url_for("planned_view", year=year, month=month))

    if work_type == "விடுப்பு" and not leave_type:
        flash("விடுப்பு வகையைத் தேர்வு செய்யவும்.")
        return redirect(url_for("planned_view", year=year, month=month))

    place_display = build_place_display(work_type, library_names, survey_year, leave_type)

    row = TourPlanDay(
        plan_id=plan.id,
        day_date=d,
        weekday=TAMIL_WEEKDAYS[d.weekday()],
        day_type="work",
        work_type=work_type,
        library_name="\n".join(library_names) if work_type == "நூலகங்கள் ஆய்வு" else None,
        survey_year=survey_year if work_type == "நூலகங்கள் ஆய்வு" else None,
        leave_type=leave_type if work_type == "விடுப்பு" else None,
        place_display=place_display,
    )
    db.session.add(row)
    db.session.commit()

    return redirect(url_for("planned_view", year=year, month=month))


@app.route("/planned/<int:year>/<int:month>/day/<int:day_id>/edit", methods=["GET"])
def planned_edit_day_form(year, month, day_id):
    plan = TourPlan.query.filter_by(year=year, month=month).first()
    if not plan:
        abort(404)
    day = TourPlanDay.query.filter_by(id=day_id, plan_id=plan.id).first()
    if not day:
        abort(404)
    if day.day_type != "work":
        flash("அரசு விடுமுறை / வார விடுமுறை நாட்களை திருத்த முடியாது.")
        return redirect(url_for("planned_view", year=year, month=month))

    libraries = get_libraries()
    return render_template(
        "planned_edit_day.html",
        plan=plan, day=day, libraries=libraries,
        work_types=work_types_for_day(day.day_date), survey_years=SURVEY_YEARS,
        leave_types=LEAVE_TYPES,
        max_survey_libraries=MAX_PLANNED_SURVEY_LIBRARIES,
        month_name=TAMIL_MONTHS[month], year=year, month=month,
    )


@app.route("/planned/<int:year>/<int:month>/day/<int:day_id>/edit", methods=["POST"])
def planned_edit_day_save(year, month, day_id):
    plan = TourPlan.query.filter_by(year=year, month=month).first()
    if not plan:
        abort(404)
    day = TourPlanDay.query.filter_by(id=day_id, plan_id=plan.id).first()
    if not day:
        abort(404)
    if day.day_type != "work":
        flash("அரசு விடுமுறை / வார விடுமுறை நாட்களை திருத்த முடியாது.")
        return redirect(url_for("planned_view", year=year, month=month))

    work_type = (request.form.get("work_type") or "").strip()
    library_names = [x.strip() for x in request.form.getlist("library_name") if x.strip()]
    survey_year = (request.form.get("survey_year") or "").strip()
    leave_type = (request.form.get("leave_type") or "").strip()

    if not work_type:
        flash("பணியிடம் தேர்வு செய்யவும்.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    if work_type == "அலுவலகப் பணி" and day.day_date.weekday() in OFFICE_WORK_EXCLUDED_WEEKDAYS:
        flash("சனி / ஞாயிறு நாட்களில் 'அலுவலகப் பணி' தேர்வு செய்ய முடியாது.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    if work_type == "நூலகங்கள் ஆய்வு" and (not library_names or not survey_year):
        flash("நூலகங்கள் ஆய்வு-க்கு நூலகம் பெயர் மற்றும் ஆய்வு ஆண்டு கட்டாயம்.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    if work_type == "நூலகங்கள் ஆய்வு" and len(library_names) > MAX_PLANNED_SURVEY_LIBRARIES:
        flash(f"ஆய்வுக்கு அதிகபட்சம் {MAX_PLANNED_SURVEY_LIBRARIES} நூலகங்கள் மட்டுமே தேர்வு செய்யலாம்.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    if work_type == "விடுப்பு" and not leave_type:
        flash("விடுப்பு வகையைத் தேர்வு செய்யவும்.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    day.work_type = work_type
    day.library_name = "\n".join(library_names) if work_type == "நூலகங்கள் ஆய்வு" else None
    day.survey_year = survey_year if work_type == "நூலகங்கள் ஆய்வு" else None
    day.leave_type = leave_type if work_type == "விடுப்பு" else None
    day.place_display = build_place_display(work_type, library_names, survey_year, leave_type)
    db.session.commit()

    flash("இந்த நாளின் பதிவு திருத்தப்பட்டது.")
    return redirect(url_for("planned_view", year=year, month=month))


@app.route("/planned/<int:year>/<int:month>/letter", methods=["GET"])
def planned_letter_form(year, month):
    plan = TourPlan.query.filter_by(year=year, month=month).first()
    if not plan or not plan.is_complete:
        flash("இந்த மாதத்திற்கான பயணத் திட்டம் இன்னும் முழுமையாகவில்லை.")
        return redirect(url_for("planned_view", year=year, month=month))
    return render_template(
        "letter_form.html", plan=plan, month_name=TAMIL_MONTHS[month], year=year, month=month,
    )


@app.route("/planned/<int:year>/<int:month>/letter", methods=["POST"])
def planned_letter_generate(year, month):
    plan = TourPlan.query.filter_by(year=year, month=month).first()
    if not plan or not plan.is_complete:
        flash("இந்த மாதத்திற்கான பயணத் திட்டம் இன்னும் முழுமையாகவில்லை.")
        return redirect(url_for("planned_view", year=year, month=month))

    file_number = (request.form.get("file_number") or "").strip()
    letter_date = (request.form.get("letter_date") or "").strip()
    plan.file_number = file_number
    plan.letter_date = letter_date
    db.session.commit()

    pdf_bytes = generate_permission_letter_pdf(plan)
    # HTTP header-களில் ASCII அல்லாத (தமிழ்) எழுத்துக்களை நேரடியாகப் பயன்படுத்த
    # முடியாது (Invalid HTTP Header எரர் தரும்). ஆகவே பதிவிறக்கும் கோப்புப் பெயருக்கு
    # ஆங்கில/எண் அடிப்படையிலான ASCII பெயரையும், UI-ல் காட்ட விரும்பினால் தமிழ்ப்
    # பெயரையும் RFC 5987 filename* முறையில் தனியாகக் கொடுக்கிறோம்.
    ascii_filename = f"utthesa-payanam-{year}-{month:02d}.pdf"
    tamil_filename = f"utthesa-payanam-{TAMIL_MONTHS[month]}-{year}.pdf".replace(" ", "-")
    encoded_tamil_filename = quote(tamil_filename)
    content_disposition = (
        f"attachment; filename={ascii_filename}; "
        f"filename*=UTF-8''{encoded_tamil_filename}"
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )


# ---------------------------------------------------------------------------
# ROUTES — 2. உண்மைப் பயணத் திட்டம்
# ---------------------------------------------------------------------------
@app.route("/actual", methods=["GET"])
def actual_select():
    today = date.today()
    saved_plans = (
        ActualTourPlan.query.order_by(ActualTourPlan.year.desc(), ActualTourPlan.month.desc()).all()
    )
    return render_template(
        "actual_select.html",
        tamil_months=TAMIL_MONTHS,
        years_range=list(range(today.year - 1, today.year + 2)),
        default_year=today.year,
        default_month=today.month,
        saved_plans=saved_plans,
    )


@app.route("/actual/<int:year>/<int:month>", methods=["GET"])
def actual_view(year, month):
    holidays = get_holidays()
    plan = get_or_create_actual_plan(year, month)
    next_pending = cascade_autofill_actual(plan, holidays)

    libraries = get_libraries()
    filled_days = ActualTourPlan.query.get(plan.id).days  # refreshed relationship

    return render_template(
        "actual_index.html",
        plan=plan,
        filled_days=filled_days,
        next_pending=next_pending,
        libraries=libraries,
        survey_years=SURVEY_YEARS,
        leave_types=LEAVE_TYPES,
        time_from_options=TIME_FROM_OPTIONS,
        time_to_options=TIME_TO_OPTIONS,
        max_libraries=MAX_LIBRARIES_PER_DAY,
        month_name=TAMIL_MONTHS[month],
        year=year,
        month=month,
    )


def _read_actual_day_form(form):
    """request.form-இலிருந்து ஒரு நாளின் ஆய்வு/பார்வை பதிவுக்கான தரவை படித்து,
    சரிபார்த்து (has_survey, survey_year, survey_libs, has_visit, visit_libs,
    has_office, time_from, time_to, error_message) என திருப்பும். தவறு
    இல்லையெனில் error_message None ஆக இருக்கும்."""
    has_visit = bool(form.get("has_visit"))
    has_survey = bool(form.get("has_survey"))
    has_office = bool(form.get("has_office"))
    has_leave = bool(form.get("has_leave"))

    visit_libs_raw = form.getlist("visit_libraries")
    survey_libs_raw = form.getlist("survey_libraries")
    survey_year = (form.get("survey_year") or "").strip()
    leave_type = (form.get("leave_type") or "").strip()
    time_from = (form.get("time_from") or "").strip()
    time_to = (form.get("time_to") or "").strip()

    visit_libs = visit_libs_raw[:MAX_LIBRARIES_PER_DAY]
    survey_libs = survey_libs_raw[:MAX_LIBRARIES_PER_DAY]

    if not (has_visit or has_survey or has_office or has_leave):
        return None, "பார்வை / ஆய்வு / அலுவலகப் பணி / விடுப்பு — ஒன்றையாவது தேர்வு செய்யவும்."

    # விடுப்பு, மற்ற மூன்று வகைகளுடன் (ஆய்வு / பார்வை / அலுவலகப் பணி) ஒரே நாளில்
    # சேர்ந்து தேர்வு செய்ய முடியாது — ஒன்று மட்டும் தேர்வு செய்ய வேண்டும்.
    if has_leave and (has_visit or has_survey or has_office):
        return None, "விடுப்பு தேர்வு செய்தால் ஆய்வு / பார்வை / அலுவலகப் பணி ஆகியவற்றைச் சேர்த்துத் தேர்வு செய்ய முடியாது."

    if has_visit and not visit_libs:
        return None, "பார்வைக்கு குறைந்தது ஒரு நூலகம் தேர்வு செய்யவும்."

    if len(visit_libs_raw) > MAX_LIBRARIES_PER_DAY:
        return None, f"பார்வைக்கு அதிகபட்சம் {MAX_LIBRARIES_PER_DAY} நூலகங்கள் மட்டுமே தேர்வு செய்யலாம்."

    if has_survey and (not survey_year or not survey_libs):
        return None, "ஆய்வுக்கு ஆய்வு ஆண்டு மற்றும் குறைந்தது ஒரு நூலகம் தேர்வு செய்யவும்."

    if len(survey_libs_raw) > MAX_LIBRARIES_PER_DAY:
        return None, f"ஆய்வுக்கு அதிகபட்சம் {MAX_LIBRARIES_PER_DAY} நூலகங்கள் மட்டுமே தேர்வு செய்யலாம்."

    if has_leave and not leave_type:
        return None, "விடுப்பு வகையைத் தேர்வு செய்யவும்."

    # அலுவலகப் பணி தேர்வு செய்தால் நேரம் தேர்வு தேவையில்லை — நிலையான
    # இயல்புநேரம் (09.45 மு.ப - 05.45 பிப) தானாகப் பயன்படுத்தப்படும்.
    if has_office:
        time_from, time_to = OFFICE_DEFAULT_TIME_FROM, OFFICE_DEFAULT_TIME_TO

    # அந்த நாள் முழுக்க விடுப்பு மட்டும் எனில் ("பார்வை/ஆய்வு/அலுவலகப் பணி" இல்லாமல்)
    # "எடுத்துக் கொண்ட நேரம்" கட்டாயமில்லை.
    only_leave = has_leave and not (has_visit or has_survey or has_office)
    if not only_leave and (not time_from or not time_to):
        return None, "எடுத்துக் கொண்ட நேரம் (முற்பகல் & பிற்பகல்) தேர்வு செய்யவும்."

    data = {
        "has_visit": has_visit,
        "visit_libs": visit_libs,
        "has_survey": has_survey,
        "survey_year": survey_year if has_survey else "",
        "survey_libs": survey_libs,
        "has_office": has_office,
        "has_leave": has_leave,
        "leave_type": leave_type if has_leave else "",
        "time_from": time_from,
        "time_to": time_to,
    }
    return data, None


@app.route("/actual/<int:year>/<int:month>/day", methods=["POST"])
def actual_save_day(year, month):
    plan = get_or_create_actual_plan(year, month)
    day_str = request.form.get("day_date")

    try:
        d = datetime.strptime(day_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        flash("தேதி தவறாக உள்ளது.")
        return redirect(url_for("actual_view", year=year, month=month))

    data, error = _read_actual_day_form(request.form)
    if error:
        flash(error)
        return redirect(url_for("actual_view", year=year, month=month))

    if data["has_office"] and d.weekday() in OFFICE_WORK_EXCLUDED_WEEKDAYS:
        flash("சனி / ஞாயிறு நாட்களில் 'அலுவலகப் பணி' தேர்வு செய்ய முடியாது.")
        return redirect(url_for("actual_view", year=year, month=month))

    if data["has_survey"]:
        dup_lib, dup_date = find_duplicate_survey_library(plan, data["survey_libs"])
        if dup_lib:
            flash(
                f"இந்த நூலகம் ({dup_lib}) இதே மாதத்தில் {dup_date.strftime('%d.%m.%Y')} "
                f"தேதியில் ஆய்வு மேற்கொள்ளப்பட்டுள்ளது. தயவு செய்து வேறு நூலகம் தேர்வு செய்யவும்."
            )
            return redirect(url_for("actual_view", year=year, month=month))

    place_display = build_actual_content(
        data["has_survey"], data["survey_year"], data["survey_libs"],
        data["has_visit"], data["visit_libs"], data["has_office"],
        data["has_leave"], data["leave_type"],
    )

    row = ActualTourPlanDay(
        plan_id=plan.id,
        day_date=d,
        weekday=TAMIL_WEEKDAYS[d.weekday()],
        day_type="work",
        has_visit=data["has_visit"],
        visit_libraries="\n".join(data["visit_libs"]),
        has_survey=data["has_survey"],
        survey_year=data["survey_year"],
        survey_libraries="\n".join(data["survey_libs"]),
        has_office=data["has_office"],
        has_leave=data["has_leave"],
        leave_type=data["leave_type"] or None,
        time_from=data["time_from"],
        time_to=data["time_to"],
        place_display=place_display,
    )
    db.session.add(row)
    db.session.commit()

    return redirect(url_for("actual_view", year=year, month=month))


@app.route("/actual/<int:year>/<int:month>/day/<int:day_id>/edit", methods=["GET"])
def actual_edit_day_form(year, month, day_id):
    plan = ActualTourPlan.query.filter_by(year=year, month=month).first()
    if not plan:
        abort(404)
    day = ActualTourPlanDay.query.filter_by(id=day_id, plan_id=plan.id).first()
    if not day:
        abort(404)
    if day.day_type != "work":
        flash("அரசு விடுமுறை / வார விடுமுறை நாட்களை திருத்த முடியாது.")
        return redirect(url_for("actual_view", year=year, month=month))

    libraries = get_libraries()
    return render_template(
        "actual_edit_day.html",
        plan=plan, day=day, libraries=libraries,
        survey_years=SURVEY_YEARS,
        leave_types=LEAVE_TYPES,
        time_from_options=TIME_FROM_OPTIONS,
        time_to_options=TIME_TO_OPTIONS,
        max_libraries=MAX_LIBRARIES_PER_DAY,
        month_name=TAMIL_MONTHS[month], year=year, month=month,
    )


@app.route("/actual/<int:year>/<int:month>/day/<int:day_id>/edit", methods=["POST"])
def actual_edit_day_save(year, month, day_id):
    plan = ActualTourPlan.query.filter_by(year=year, month=month).first()
    if not plan:
        abort(404)
    day = ActualTourPlanDay.query.filter_by(id=day_id, plan_id=plan.id).first()
    if not day:
        abort(404)
    if day.day_type != "work":
        flash("அரசு விடுமுறை / வார விடுமுறை நாட்களை திருத்த முடியாது.")
        return redirect(url_for("actual_view", year=year, month=month))

    data, error = _read_actual_day_form(request.form)
    if error:
        flash(error)
        return redirect(url_for("actual_edit_day_form", year=year, month=month, day_id=day_id))

    if data["has_office"] and day.day_date.weekday() in OFFICE_WORK_EXCLUDED_WEEKDAYS:
        flash("சனி / ஞாயிறு நாட்களில் 'அலுவலகப் பணி' தேர்வு செய்ய முடியாது.")
        return redirect(url_for("actual_edit_day_form", year=year, month=month, day_id=day_id))

    if data["has_survey"]:
        dup_lib, dup_date = find_duplicate_survey_library(plan, data["survey_libs"], exclude_day_id=day.id)
        if dup_lib:
            flash(
                f"இந்த நூலகம் ({dup_lib}) இதே மாதத்தில் {dup_date.strftime('%d.%m.%Y')} "
                f"தேதியில் ஆய்வு மேற்கொள்ளப்பட்டுள்ளது. தயவு செய்து வேறு நூலகம் தேர்வு செய்யவும்."
            )
            return redirect(url_for("actual_edit_day_form", year=year, month=month, day_id=day_id))

    day.has_visit = data["has_visit"]
    day.visit_libraries = "\n".join(data["visit_libs"])
    day.has_survey = data["has_survey"]
    day.survey_year = data["survey_year"]
    day.survey_libraries = "\n".join(data["survey_libs"])
    day.has_office = data["has_office"]
    day.has_leave = data["has_leave"]
    day.leave_type = data["leave_type"] or None
    day.time_from = data["time_from"]
    day.time_to = data["time_to"]
    day.place_display = build_actual_content(
        data["has_survey"], data["survey_year"], data["survey_libs"],
        data["has_visit"], data["visit_libs"], data["has_office"],
        data["has_leave"], data["leave_type"],
    )
    db.session.commit()

    flash("இந்த நாளின் பதிவு திருத்தப்பட்டது.")
    return redirect(url_for("actual_view", year=year, month=month))


@app.route("/actual/<int:year>/<int:month>/report", methods=["GET"])
def actual_report_pdf(year, month):
    plan = ActualTourPlan.query.filter_by(year=year, month=month).first()
    if not plan or not plan.is_complete:
        flash("இந்த மாதத்திற்கான உண்மைப் பயணத் திட்டம் இன்னும் முழுமையாகவில்லை.")
        return redirect(url_for("actual_view", year=year, month=month))

    pdf_bytes = generate_actual_report_pdf(plan)
    ascii_filename = f"unmai-payanam-{year}-{month:02d}.pdf"
    tamil_filename = f"unmai-payanam-{TAMIL_MONTHS[month]}-{year}.pdf".replace(" ", "-")
    encoded_tamil_filename = quote(tamil_filename)
    content_disposition = (
        f"attachment; filename={ascii_filename}; "
        f"filename*=UTF-8''{encoded_tamil_filename}"
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )


# ---------------------------------------------------------------------------
# ROUTES — ஒரு மாதத்திற்கான உத்தேச + உண்மை பயணத் திட்டங்களை அழித்தல்
# ---------------------------------------------------------------------------
@app.route("/delete_month/<int:year>/<int:month>", methods=["POST"])
def delete_month(year, month):
    password = request.form.get("password") or ""
    next_page = request.form.get("next") or "planned_select"
    if next_page not in ("planned_select", "actual_select"):
        next_page = "planned_select"

    # target: "planned" -> உத்தேசப் பயணத் திட்டம் மட்டும்
    #         "actual"  -> உண்மைப் பயணத் திட்டம் மட்டும்
    #         "both"    -> இரண்டும் (பழைய behaviour, form-ல் target அனுப்பாவிட்டால்)
    target = request.form.get("target") or "both"
    if target not in ("planned", "actual", "both"):
        target = "both"

    if password != DELETE_PASSWORD:
        flash("கடவுச்சொல் தவறு — எதுவும் அழிக்கப்படவில்லை.")
        return redirect(url_for(next_page))

    deleted_labels = []
    if target in ("planned", "both"):
        planned = TourPlan.query.filter_by(year=year, month=month).first()
        if planned:
            db.session.delete(planned)
            deleted_labels.append("உத்தேசப் பயணத் திட்டம்")
    if target in ("actual", "both"):
        actual = ActualTourPlan.query.filter_by(year=year, month=month).first()
        if actual:
            db.session.delete(actual)
            deleted_labels.append("உண்மைப் பயணத் திட்டம்")
    db.session.commit()

    if deleted_labels:
        flash(f"{TAMIL_MONTHS[month]} {year} — {' மற்றும் '.join(deleted_labels)} அழிக்கப்பட்டது.")
    else:
        flash(f"{TAMIL_MONTHS[month]} {year} — அழிக்க எதுவும் இல்லை.")
    return redirect(url_for(next_page))


# ---------------------------------------------------------------------------
# ROUTES — 3. ஆய்வு / பார்வை அறிக்கைகள்
# ---------------------------------------------------------------------------
DEFAULT_LIBRARY_TYPES = [
    "மைய நூலகம்", "முழு நேர கிளை நூலகம்", "கிளை நூலகம்", "ஊர்ப்புற நூலகம்",
]


@app.route("/reports")
def reports_placeholder():
    return render_template("reports_home.html")


def _library_types(libraries):
    """Google Sheet-ல் உள்ள நூலக வகைகள் (வரிசை மாறாமல்). Sheet கிடைக்கவில்லை
    எனில் இயல்பு நான்கு வகைகள்."""
    seen = []
    for lib in libraries:
        t = lib["type"]
        if t and t not in seen:
            seen.append(t)
    return seen or DEFAULT_LIBRARY_TYPES


@app.route("/reports/intimation", methods=["GET"])
def intimation_form():
    libraries = get_libraries()
    if not libraries:
        flash("Google Sheet-லிருந்து நூலகங்கள் பட்டியலைப் பெற இயலவில்லை. Sheet பகிர்வு அமைப்பைச் சரிபார்க்கவும்.")
    records = (
        InspectionIntimation.query.order_by(InspectionIntimation.id.desc()).limit(20).all()
    )
    return render_template(
        "intimation_form.html",
        libraries=libraries,
        library_types=_library_types(libraries),
        survey_years=SURVEY_YEARS,
        records=records,
    )


@app.route("/reports/intimation", methods=["POST"])
def intimation_generate():
    f = request.form
    file_number = (f.get("file_number") or "").strip()
    library_type = (f.get("library_type") or "").strip()
    library_name = (f.get("library_name") or "").strip()
    survey_year = (f.get("survey_year") or "").strip()
    letter_date = _parse_date(f.get("letter_date"))
    inspection_date = _parse_date(f.get("inspection_date"))

    if not (file_number and library_type and library_name and survey_year
            and letter_date and inspection_date):
        flash("அனைத்து விவரங்களையும் பூர்த்தி செய்யவும்.")
        return redirect(url_for("intimation_form"))

    rec = InspectionIntimation(
        file_number=file_number, letter_date=letter_date, library_type=library_type,
        library_name=library_name, survey_year=survey_year, inspection_date=inspection_date,
    )
    db.session.add(rec)
    db.session.commit()
    return _intimation_pdf_response(rec)


@app.route("/reports/intimation/<int:rec_id>/pdf", methods=["GET"])
def intimation_pdf(rec_id):
    rec = db.session.get(InspectionIntimation, rec_id)
    if rec is None:
        abort(404)
    return _intimation_pdf_response(rec)


@app.route("/reports/intimation/<int:rec_id>/delete", methods=["POST"])
def intimation_delete(rec_id):
    if (request.form.get("password") or "") != DELETE_PASSWORD:
        flash("கடவுச்சொல் தவறு — எதுவும் அழிக்கப்படவில்லை.")
        return redirect(url_for("intimation_form"))
    rec = db.session.get(InspectionIntimation, rec_id)
    if rec is not None:
        db.session.delete(rec)
        db.session.commit()
        flash("பதிவு அழிக்கப்பட்டது.")
    return redirect(url_for("intimation_form"))


def _intimation_pdf_response(rec):
    # கோப்புப் பெயர்: "<நூலகம் பெயர்>- ஆய்வு தகவல்.pdf". HTTP header-ல் தமிழ் எழுத்து
    # நேரடியாகப் போகாது என்பதால் ASCII பெயர் + RFC 5987 filename* இரண்டையும் தருகிறோம்.
    safe_name = re.sub(r'[\\/:*?"<>|\r\n]+', " ", rec.library_name or "").strip()
    tamil_filename = f"{safe_name}- ஆய்வு தகவல்.pdf"
    ascii_filename = f"inspection-intimation-{rec.id}.pdf"
    return Response(
        generate_inspection_intimation_pdf(rec),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename={ascii_filename}; "
                f"filename*=UTF-8''{quote(tamil_filename)}"
            )
        },
    )


# ---------------------------------------------------------------------------
# ROUTES — 4. நூலக முகவரி (Neon DB) — பார்வை, திருத்தம், ஏற்றுமதி
# ---------------------------------------------------------------------------
LIB_HEADER_ALIASES = {
    "library_type": ["நூலக வகை", "வகை", "type", "library type"],
    "name": ["நூலகம் பெயர்", "நூலகம்", "பெயர்", "name", "library", "library name"],
    "address": ["முகவரி", "address"],
    "librarian_name": ["நூலகர் பெயர்", "நூலகர்", "librarian", "librarian name"],
    "phone": ["தொலைபேசி எண்", "தொலைபேசி எண்.", "தொலைபேசி", "கைபேசி", "phone", "mobile", "phone number"],
}
LIB_FIELDS = ["library_type", "name", "address", "librarian_name", "phone"]


def _clean(v):
    v = "" if v is None else str(v).strip()
    return "" if v.lower() == "nan" else v


def _clean_phone(v):
    v = _clean(v)
    return v[:-2] if v.endswith(".0") and v[:-2].isdigit() else v


def _parse_library_rows(file_storage):
    """Excel (.xlsx) / CSV கோப்பை [{library_type,name,address,librarian_name,phone}] ஆக மாற்றும்.
    தலைப்பு வரிசையில் பெயர்கள் அடையாளம் காணப்பட்டால் அவற்றைப் பயன்படுத்தும்;
    இல்லையெனில் நெடுவரிசை வரிசை: வகை, பெயர், முகவரி, நூலகர், தொலைபேசி."""
    fname = (file_storage.filename or "").lower()
    if fname.endswith(".csv"):
        df = pd.read_csv(file_storage, dtype=str, keep_default_na=False)
    elif fname.endswith(".xlsx") or fname.endswith(".xlsm"):
        df = pd.read_excel(file_storage, dtype=str)
    else:
        raise ValueError(".xlsx அல்லது .csv கோப்பை மட்டும் தேர்ந்தெடுக்கவும் (பழைய .xls எனில் .xlsx ஆகச் சேமிக்கவும்).")
    df = df.fillna("")
    cols = [str(c).strip() for c in df.columns]
    lowered = {c.lower(): i for i, c in enumerate(cols)}
    mapping = {}
    for field, aliases in LIB_HEADER_ALIASES.items():
        for a in aliases:
            if a.lower() in lowered:
                mapping[field] = lowered[a.lower()]
                break
    if "name" not in mapping:  # தலைப்பு இல்லை — முதல் வரியையும் தரவாக எடுத்து, இடம் வாரியாக
        raw = pd.DataFrame([cols] + df.values.tolist())
        mapping = {f: i for i, f in enumerate(LIB_FIELDS) if i < raw.shape[1]}
        rows_src = raw.values.tolist()
    else:
        rows_src = df.values.tolist()
    out = []
    for r in rows_src:
        rec = {f: (_clean_phone(r[i]) if f == "phone" else _clean(r[i])) for f, i in mapping.items()}
        if rec.get("name"):
            out.append(rec)
    return out


def _find_library(name, ltype):
    q = Library.query.filter(Library.name == name)
    if ltype:
        hit = q.filter(Library.library_type == ltype).first()
        if hit:
            return hit
    matches = q.all()
    return matches[0] if len(matches) == 1 and not ltype else None


@app.route("/libraries")
def libraries_home():
    rows = Library.query.order_by(Library.id).all()
    libs = [
        {"id": r.id, "type": (r.library_type or "").strip(), "name": r.name,
         "address": r.address or "", "librarian": r.librarian_name or "", "phone": r.phone or ""}
        for r in rows
    ]
    types = []
    for l in libs:
        if l["type"] and l["type"] not in types:
            types.append(l["type"])
    return render_template("libraries_home.html", libs=libs, types=types)


@app.route("/libraries/manage")
def libraries_manage():
    rows = Library.query.order_by(Library.id).all()
    types = []
    for r in rows:
        t = (r.library_type or "").strip()
        if t and t not in types:
            types.append(t)
    return render_template("libraries_manage.html", rows=rows, types=types)


def _library_form(rec):
    """புதிய பதிவு (rec=None) அல்லது திருத்தம்."""
    if request.method == "POST":
        f = request.form
        name = _clean(f.get("name"))
        if not name:
            flash("நூலகம் பெயர் அவசியம்.")
            return redirect(request.url)
        is_new = rec is None
        if is_new:
            rec = Library()
            db.session.add(rec)
        rec.library_type = _clean(f.get("library_type"))
        rec.name = name
        rec.address = (f.get("address") or "").strip()
        rec.librarian_name = _clean(f.get("librarian_name"))
        rec.phone = _clean(f.get("phone"))
        db.session.commit()
        flash("புதிய நூலகம் சேர்க்கப்பட்டது." if is_new else "மாற்றங்கள் சேமிக்கப்பட்டன.")
        return redirect(url_for("libraries_manage"))
    types = [t for (t,) in db.session.query(Library.library_type).distinct().all() if t]
    return render_template("library_edit.html", rec=rec, types=types)


@app.route("/libraries/new", methods=["GET", "POST"])
def library_new():
    return _library_form(None)


@app.route("/libraries/<int:lib_id>/edit", methods=["GET", "POST"])
def library_edit(lib_id):
    rec = db.session.get(Library, lib_id)
    if rec is None:
        abort(404)
    return _library_form(rec)


@app.route("/libraries/<int:lib_id>/delete", methods=["POST"])
def library_delete(lib_id):
    if (request.form.get("password") or "") != DELETE_PASSWORD:
        flash("கடவுச்சொல் தவறு — எதுவும் அழிக்கப்படவில்லை.")
        return redirect(url_for("libraries_manage"))
    rec = db.session.get(Library, lib_id)
    if rec is not None:
        db.session.delete(rec)
        db.session.commit()
        flash("நூலகப் பதிவு அழிக்கப்பட்டது.")
    return redirect(url_for("libraries_manage"))


@app.route("/libraries/import-sheet", methods=["POST"])
def libraries_import_sheet():
    """Google Sheet-ல் உள்ள வகை + பெயரை DB-ல் சேர்க்கும் (ஏற்கனவே உள்ளவை தவிர்க்கப்படும்)."""
    libs = _get_libraries_from_sheet()
    if not libs:
        flash("Google Sheet-லிருந்து நூலகங்களைப் பெற இயலவில்லை.")
        return redirect(url_for("libraries_manage"))
    existing = {((r.library_type or "").strip(), r.name.strip()) for r in Library.query.all()}
    added = 0
    for l in libs:
        key = (l["type"], l["name"])
        if key in existing:
            continue
        db.session.add(Library(library_type=l["type"], name=l["name"]))
        existing.add(key)
        added += 1
    db.session.commit()
    flash(f"Google Sheet-லிருந்து {added} புதிய நூலகங்கள் சேர்க்கப்பட்டன; {len(libs) - added} ஏற்கனவே இருந்தன.")
    return redirect(url_for("libraries_manage"))


@app.route("/libraries/import-file", methods=["POST"])
def libraries_import_file():
    """Excel/CSV: பெயர் பொருந்தினால் முகவரி, நூலகர், தொலைபேசியை புதுப்பிக்கும்; இல்லையெனில் புதிதாகச் சேர்க்கும்.
    கோப்பில் காலியாக உள்ள கலங்கள் ஏற்கனவே உள்ள தகவலை அழிக்காது."""
    file = request.files.get("file")
    if not file or not file.filename:
        flash("கோப்பைத் தேர்ந்தெடுக்கவும்.")
        return redirect(url_for("libraries_manage"))
    try:
        rows = _parse_library_rows(file)
    except Exception as exc:  # noqa: BLE001
        flash(f"கோப்பைப் படிக்க இயலவில்லை: {exc}")
        return redirect(url_for("libraries_manage"))
    added = updated = 0
    for r in rows:
        rec = _find_library(r["name"], r.get("library_type", ""))
        if rec is None:
            db.session.add(Library(
                library_type=r.get("library_type", ""), name=r["name"],
                address=r.get("address", ""), librarian_name=r.get("librarian_name", ""),
                phone=r.get("phone", ""),
            ))
            added += 1
            db.session.flush()
        else:
            changed = False
            for f in ("address", "librarian_name", "phone"):
                v = r.get(f, "")
                if v and v != (getattr(rec, f) or ""):
                    setattr(rec, f, v)
                    changed = True
            if r.get("library_type") and not rec.library_type:
                rec.library_type = r["library_type"]
                changed = True
            updated += int(changed)
    db.session.commit()
    flash(f"கோப்பிலிருந்து {len(rows)} வரிசைகள் படிக்கப்பட்டன — புதிதாக {added}, புதுப்பிக்கப்பட்டவை {updated}.")
    return redirect(url_for("libraries_manage"))


# ---------------------------------------------------------------------------
# PDF LETTER GENERATION
# ---------------------------------------------------------------------------
# NOTE: ReportLab has no Indic text-shaping engine (no GSUB/GPOS), so it draws
# Tamil glyphs in raw Unicode order — vowel signs land in the wrong spot and
# consonant+vowel-sign ligatures fall back to the wrong shape. tamil_text.py
# shapes Tamil correctly with HarfBuzz + FreeType and draws it as a crisp
# raster image via the TamilText Flowable (drop-in replacement for Paragraph
# wherever Tamil script is involved). It reuses these same font files.
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_REGULAR = os.path.join(FONT_DIR, "NotoSansTamil-Regular.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "NotoSansTamil-Bold.ttf")


def generate_permission_letter_pdf(plan: TourPlan) -> bytes:
    import io

    buf = io.BytesIO()
    page_size = portrait(legal)
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    def T(text, font=FONT_REGULAR, size=11, leading=16, align="left", space_after=0):
        return TamilText(text, font, size, leading_pt=leading, align=align, space_after=space_after)

    story = []
    story.append(T("பொது நூலகத் துறை", font=FONT_BOLD, size=14, leading=18, align="center", space_after=14))

    header_table = Table(
        [[
            T(
                f"அனுப்புநர்<br/>{LETTER_SENDER_NAME},<br/>{LETTER_SENDER_DESIGNATION},<br/>"
                f"{LETTER_SENDER_OFFICE_LINE1}<br/>{LETTER_SENDER_OFFICE_LINE2}"
            ),
            T(
                f"பெறுநர்<br/>{LETTER_RECEIVER_DESIGNATION},<br/>"
                f"{LETTER_RECEIVER_OFFICE_LINE1}<br/>{LETTER_RECEIVER_OFFICE_LINE2}"
            ),
        ]],
        colWidths=[doc.width / 2.0, doc.width / 2.0],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))

    ref_line = f"ப.வெ.எண்.{plan.file_number or '____'}, நாள். {plan.letter_date or '__________'}"
    story.append(T(ref_line, align="center"))
    story.append(Spacer(1, 14))

    story.append(T("ஐயா,"))
    story.append(Spacer(1, 10))

    subject = (
        f"பொருள் : உத்தேசப் பயணத் திட்டம் – திண்டுக்கல் மாவட்ட நூலக ஆணைக்குழு – "
        f"{LETTER_SENDER_NAME} – {LETTER_SENDER_DESIGNATION} – {TAMIL_MONTHS[plan.month]} – {plan.year} "
        f"மாதத்திற்கான உத்தேச பயணத் திட்டம் சமர்ப்பித்தல் – சார்பு"
    )
    story.append(T(subject))
    story.append(Spacer(1, 14))

    table_data = [[
        T("நாள்", font=FONT_BOLD, size=10, leading=13, align="center"),
        T("கிழமை", font=FONT_BOLD, size=10, leading=13, align="center"),
        T("பணியிடம்", font=FONT_BOLD, size=10, leading=13, align="center"),
    ]]
    for d in plan.days:
        table_data.append([
            T(d.day_date.strftime("%d.%m.%Y"), size=10, leading=13),
            T(d.weekday, size=10, leading=13),
            T(d.place_display, size=10, leading=13),
        ])

    plan_table = Table(table_data, colWidths=[28 * mm, 26 * mm, doc.width - 54 * mm], repeatRows=1)
    plan_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(plan_table)
    story.append(Spacer(1, 16))

    story.append(T("மேற்கண்ட உத்தேச பயணத் திட்டத்திற்கு ஒப்புதல் வழங்குமாறு பணிவுடன் கேட்டுக் கொள்கிறேன்."))
    story.append(Spacer(1, 22))
    story.append(T(f"{LETTER_SENDER_DESIGNATION},<br/>{LETTER_RECEIVER_OFFICE_LINE2}", align="right"))
    story.append(Spacer(1, 22))

    story.append(T("மேற்கண்ட உத்தேச பயணத் திட்டத்திற்கு ஒப்புதல் வழங்கப்படுகிறது."))
    story.append(Spacer(1, 22))
    story.append(T(f"{LETTER_RECEIVER_DESIGNATION},<br/>{LETTER_RECEIVER_OFFICE_LINE2}", align="right"))
    story.append(Spacer(1, 22))

    story.append(T(
        f"பெறுநர் – {LETTER_SENDER_DESIGNATION}, {LETTER_SENDER_OFFICE_LINE1} {LETTER_SENDER_OFFICE_LINE2}",
        size=9, leading=12,
    ))

    doc.build(story)
    return buf.getvalue()


def _library_display(name, ltype):
    """நூலகம் பெயர் + நூலக வகை (எ.கா. 'கி23. ராமராஜபுரம் கிளை நூலகம்')."""
    return " ".join(x for x in ((name or "").strip(), (ltype or "").strip()) if x)


def generate_inspection_intimation_pdf(rec: InspectionIntimation) -> bytes:
    """ஆய்வு தகவல் நூலகருக்கு அனுப்புதல் — A4 portrait கடிதம்."""
    import io
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=portrait(A4),
        topMargin=22 * mm, bottomMargin=18 * mm,
        leftMargin=22 * mm, rightMargin=22 * mm,
    )

    def T(text, font=FONT_REGULAR, size=12, leading=19, align="left",
          space_after=0, justify=False, indent=0):
        return TamilText(text, font, size, leading_pt=leading, align=align,
                         space_after=space_after, justify=justify, first_indent=indent)

    lib = _library_display(rec.library_name, rec.library_type)
    insp_date = rec.inspection_date.strftime("%d.%m.%Y")
    letter_date = rec.letter_date.strftime("%d.%m.%Y")
    year = rec.survey_year

    story = [T(f"{DISTRICT_NAME} மாவட்ட நூலக அலுவலரின் செயல்முறைகள்",
               font=FONT_BOLD, size=13, leading=18, align="center", space_after=18)]

    ref = Table(
        [[T(f"ந.க.எண்.{rec.file_number}"), T(f"நாள்.:- {letter_date}", align="right")]],
        colWidths=[doc.width * 0.6, doc.width * 0.4],
    )
    ref.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(ref)
    story.append(Spacer(1, 24))

    subject_w = doc.width * 0.72
    label_w = 24 * mm
    subj = Table(
        [[
            T("பொருள்:", size=11, leading=17),
            T(f"ஆய்வு- நூலகங்கள் ஆண்டாய்வு- {lib}- {year} ஆண்டுக்கான - "
              f"ஆய்வு- {insp_date} நாளன்று நடைபெறுதல்- அறிவிப்பு- தொடர்பாக",
              size=11, leading=17),
        ]],
        colWidths=[label_w, subject_w - label_w], hAlign="RIGHT",
    )
    subj.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(subj)
    story.append(Spacer(1, 24))

    indent = 38
    story.append(T(
        f"எதிர்வரும் {insp_date} அன்று {lib} நூலக ஆய்வாளரால் {year} ஆம் "
        f"ஆண்டுக்கான ஆய்வு மேற்கொள்ளப்படவிருக்கிறது.",
        justify=True, indent=indent, space_after=8))
    story.append(T(
        "ஆய்வு நாளன்று சம்பந்தப்பட்ட நூலகர், அனைத்து பதிவேடுகள், புள்ளி விவரங்கள் வரவு "
        "செலவு கணக்குகளை தயார் நிலையில் வைத்திருக்க வேண்டும். பழைய பத்திரிகை விற்பனை "
        "அறிக்கை மற்றும் வழங்கப்பட்ட பத்திரிக்கைகளின் பட்டியல் ஆகியவற்றின் படிகள் தயார் "
        "செய்து வைத்திருக்க வேண்டும். ஆய்வு நடைபெறும் நாளில் எக்காரணம் கொண்டும் விடுப்பில் "
        "செல்லக்கூடாது எனவும் சம்பந்தப்பட்ட நூலகருக்கு அறிவுறுத்தப்படுகிறது.",
        justify=True, indent=indent, space_after=8))
    story.append(T(
        "ஆய்வு நடைபெறவிருக்கும் நூலகத்தில் தினக்கூலி நூலகப் பணியாளர் அனுமதிக்கப் "
        "பட்டிருப்பின் அவரும் தினக்கூலிக் கூட்டுநரும் நூலகத்தில் இருக்க வேண்டும்.",
        justify=True, indent=indent))
    story.append(Spacer(1, 44))

    sign = Table(
        [["", T(f"மாவட்ட நூலக அலுவலர்,<br/>{DISTRICT_NAME}", align="center")]],
        colWidths=[doc.width * 0.55, doc.width * 0.45],
    )
    sign.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(sign)
    story.append(Spacer(1, 14))
    story.append(T(
        f"பெறுநர்:<br/>நூலகர்<br/>{(rec.library_type or '').strip()}<br/>{(rec.library_name or '').strip()}"
    ))

    doc.build(story)
    return buf.getvalue()


def generate_actual_report_pdf(plan: ActualTourPlan) -> bytes:
    """உண்மைப் பயணத் திட்டம் — பயண நாட்குறிப்பு அறிக்கை (இணைத்துள்ள மாடல்
    கடிதத்தின் அமைப்பைப் பின்பற்றி)."""
    import io

    buf = io.BytesIO()
    page_size = portrait(legal)
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    def T(text, font=FONT_REGULAR, size=11, leading=16, align="left", space_after=0):
        return TamilText(text, font, size, leading_pt=leading, align=align, space_after=space_after)

    month_name = TAMIL_MONTHS[plan.month]

    story = []
    story.append(T(
        f"மாவட்ட நூலக ஆணைக்குழு {DISTRICT_NAME} மாவட்டம்",
        font=FONT_BOLD, size=13, leading=18, align="center", space_after=10,
    ))
    story.append(T(
        f"{LETTER_SENDER_NAME}, {LETTER_SENDER_DESIGNATION}, {DISTRICT_NAME} அவர்களின் "
        f"{month_name} {plan.year}-ஆம் மாதம் பயணம் செய்த பயண நாட்குறிப்பு",
        size=11, leading=15, align="center", space_after=16,
    ))

    table_data = [[
        T("நாள்", font=FONT_BOLD, size=10, leading=13, align="center"),
        T("கிழமை", font=FONT_BOLD, size=10, leading=13, align="center"),
        T("ஆய்வு/பார்வை", font=FONT_BOLD, size=10, leading=13, align="center"),
        T("எடுத்துக் கொண்ட நேரம்", font=FONT_BOLD, size=10, leading=13, align="center"),
    ]]
    for d in plan.days:
        table_data.append([
            T(d.day_date.strftime("%d.%m.%Y"), size=10, leading=13),
            T(d.weekday, size=10, leading=13),
            T((d.place_display or "-").replace("\n", "<br/>"), size=10, leading=13),
            T(d.time_display, size=10, leading=13),
        ])

    plan_table = Table(
        table_data,
        colWidths=[24 * mm, 28 * mm, doc.width - 90 * mm, 38 * mm],
        repeatRows=1,
    )
    plan_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(plan_table)
    story.append(Spacer(1, 18))

    story.append(T("மாவட்ட நூலக அலுவலர்க்கு பணிந்து சமர்ப்பிக்கப்படுகிறது."))
    story.append(Spacer(1, 22))
    story.append(T("தங்கள் உண்மையுள்ள", align="right"))
    story.append(Spacer(1, 22))
    story.append(T(f"{LETTER_SENDER_DESIGNATION},<br/>{DISTRICT_NAME}", align="right"))
    story.append(Spacer(1, 22))

    story.append(T(
        f"{LETTER_SENDER_NAME}, {LETTER_SENDER_DESIGNATION} {DISTRICT_NAME} அவர்களின் "
        f"{month_name}-{plan.year} மாதம் உண்மை பயண நாட்குறிப்பு அனுமதி அளிக்கப்படுகிறது."
    ))
    story.append(Spacer(1, 22))
    story.append(T(f"{LETTER_RECEIVER_DESIGNATION},<br/>{DISTRICT_NAME}.", align="right"))

    doc.build(story)
    return buf.getvalue()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
