import os
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
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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


# ---------------------------------------------------------------------------
# DATA FETCHING (Google Sheet -> CSV)
# ---------------------------------------------------------------------------
def sheet_csv_url(sheet_name: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={sheet_name}"
    )


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


def build_place_display(work_type, library_name, survey_year):
    if work_type == "நூலகங்கள் ஆய்வு":
        parts = [work_type]
        extra = []
        if library_name:
            extra.append(library_name)
        if survey_year:
            extra.append(f"({survey_year})")
        if extra:
            parts.append("- " + " ".join(extra))
        return " ".join(parts)
    return work_type or "-"


def build_actual_content(has_survey, survey_year, survey_libs, has_visit, visit_libs, has_office):
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
        month_name=TAMIL_MONTHS[month],
        year=year,
        month=month,
    )


@app.route("/planned/<int:year>/<int:month>/day", methods=["POST"])
def planned_save_day(year, month):
    plan = get_or_create_plan(year, month)
    day_str = request.form.get("day_date")
    work_type = (request.form.get("work_type") or "").strip()
    library_name = (request.form.get("library_name") or "").strip()
    survey_year = (request.form.get("survey_year") or "").strip()

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

    if work_type == "நூலகங்கள் ஆய்வு" and (not library_name or not survey_year):
        flash("நூலகங்கள் ஆய்வு-க்கு நூலகம் பெயர் மற்றும் ஆய்வு ஆண்டு கட்டாயம்.")
        return redirect(url_for("planned_view", year=year, month=month))

    place_display = build_place_display(work_type, library_name, survey_year)

    row = TourPlanDay(
        plan_id=plan.id,
        day_date=d,
        weekday=TAMIL_WEEKDAYS[d.weekday()],
        day_type="work",
        work_type=work_type,
        library_name=library_name if work_type == "நூலகங்கள் ஆய்வு" else None,
        survey_year=survey_year if work_type == "நூலகங்கள் ஆய்வு" else None,
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
    library_name = (request.form.get("library_name") or "").strip()
    survey_year = (request.form.get("survey_year") or "").strip()

    if not work_type:
        flash("பணியிடம் தேர்வு செய்யவும்.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    if work_type == "அலுவலகப் பணி" and day.day_date.weekday() in OFFICE_WORK_EXCLUDED_WEEKDAYS:
        flash("சனி / ஞாயிறு நாட்களில் 'அலுவலகப் பணி' தேர்வு செய்ய முடியாது.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    if work_type == "நூலகங்கள் ஆய்வு" and (not library_name or not survey_year):
        flash("நூலகங்கள் ஆய்வு-க்கு நூலகம் பெயர் மற்றும் ஆய்வு ஆண்டு கட்டாயம்.")
        return redirect(url_for("planned_edit_day_form", year=year, month=month, day_id=day_id))

    day.work_type = work_type
    day.library_name = library_name if work_type == "நூலகங்கள் ஆய்வு" else None
    day.survey_year = survey_year if work_type == "நூலகங்கள் ஆய்வு" else None
    day.place_display = build_place_display(work_type, library_name, survey_year)
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

    visit_libs_raw = form.getlist("visit_libraries")
    survey_libs_raw = form.getlist("survey_libraries")
    survey_year = (form.get("survey_year") or "").strip()
    time_from = (form.get("time_from") or "").strip()
    time_to = (form.get("time_to") or "").strip()

    visit_libs = visit_libs_raw[:MAX_LIBRARIES_PER_DAY]
    survey_libs = survey_libs_raw[:MAX_LIBRARIES_PER_DAY]

    if not (has_visit or has_survey or has_office):
        return None, "பார்வை / ஆய்வு / அலுவலகப் பணி — ஒன்றையாவது தேர்வு செய்யவும்."

    if has_visit and not visit_libs:
        return None, "பார்வைக்கு குறைந்தது ஒரு நூலகம் தேர்வு செய்யவும்."

    if len(visit_libs_raw) > MAX_LIBRARIES_PER_DAY:
        return None, f"பார்வைக்கு அதிகபட்சம் {MAX_LIBRARIES_PER_DAY} நூலகங்கள் மட்டுமே தேர்வு செய்யலாம்."

    if has_survey and (not survey_year or not survey_libs):
        return None, "ஆய்வுக்கு ஆய்வு ஆண்டு மற்றும் குறைந்தது ஒரு நூலகம் தேர்வு செய்யவும்."

    if len(survey_libs_raw) > MAX_LIBRARIES_PER_DAY:
        return None, f"ஆய்வுக்கு அதிகபட்சம் {MAX_LIBRARIES_PER_DAY} நூலகங்கள் மட்டுமே தேர்வு செய்யலாம்."

    if not time_from or not time_to:
        return None, "எடுத்துக் கொண்ட நேரம் (முற்பகல் & பிற்பகல்) தேர்வு செய்யவும்."

    data = {
        "has_visit": has_visit,
        "visit_libs": visit_libs,
        "has_survey": has_survey,
        "survey_year": survey_year if has_survey else "",
        "survey_libs": survey_libs,
        "has_office": has_office,
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

    place_display = build_actual_content(
        data["has_survey"], data["survey_year"], data["survey_libs"],
        data["has_visit"], data["visit_libs"], data["has_office"],
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

    day.has_visit = data["has_visit"]
    day.visit_libraries = "\n".join(data["visit_libs"])
    day.has_survey = data["has_survey"]
    day.survey_year = data["survey_year"]
    day.survey_libraries = "\n".join(data["survey_libs"])
    day.has_office = data["has_office"]
    day.time_from = data["time_from"]
    day.time_to = data["time_to"]
    day.place_display = build_actual_content(
        data["has_survey"], data["survey_year"], data["survey_libs"],
        data["has_visit"], data["visit_libs"], data["has_office"],
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

    if password != DELETE_PASSWORD:
        flash("கடவுச்சொல் தவறு — எதுவும் அழிக்கப்படவில்லை.")
        return redirect(url_for(next_page))

    planned = TourPlan.query.filter_by(year=year, month=month).first()
    if planned:
        db.session.delete(planned)
    actual = ActualTourPlan.query.filter_by(year=year, month=month).first()
    if actual:
        db.session.delete(actual)
    db.session.commit()

    flash(f"{TAMIL_MONTHS[month]} {year} — உத்தேசப் பயணத் திட்டம் மற்றும் உண்மைப் பயணத் திட்டம் அழிக்கப்பட்டது.")
    return redirect(url_for(next_page))


# ---------------------------------------------------------------------------
# ROUTES — 3. Placeholder பிரிவு (பின்னர் விரிவாக்கம் செய்யலாம்)
# ---------------------------------------------------------------------------
@app.route("/reports")
def reports_placeholder():
    return render_template(
        "placeholder.html",
        title="ஆய்வு / பார்வை அறிக்கைகள்",
        message="இந்தப் பகுதி விரைவில் சேர்க்கப்படும்.",
    )


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
    story.append(T(f"{LETTER_RECEIVER_DESIGNATION}(பொ),<br/>{LETTER_RECEIVER_OFFICE_LINE2}", align="right"))
    story.append(Spacer(1, 22))

    story.append(T(
        f"பெறுநர் – {LETTER_SENDER_DESIGNATION}, {LETTER_SENDER_OFFICE_LINE1} {LETTER_SENDER_OFFICE_LINE2}",
        size=9, leading=12,
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
    story.append(T(f"{LETTER_RECEIVER_DESIGNATION}(பொ),<br/>{DISTRICT_NAME}.", align="right"))

    doc.build(story)
    return buf.getvalue()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
