import os
import calendar
from urllib.parse import quote
from datetime import datetime, date

import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, Response
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
        work_types=WORK_TYPES,
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
# ROUTES — 2 & 3. Placeholder பிரிவுகள் (பின்னர் விரிவாக்கம் செய்யலாம்)
# ---------------------------------------------------------------------------
@app.route("/actual")
def actual_placeholder():
    return render_template(
        "placeholder.html",
        title="உண்மைப் பயணத் திட்டம்",
        message="இந்தப் பகுதி விரைவில் சேர்க்கப்படும்.",
    )


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
    story.append(T(ref_line))
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
            T(f"{d.weekday}கிழமை", size=10, leading=13),
            T(d.place_display, size=10, leading=13),
        ])

    plan_table = Table(table_data, colWidths=[28 * mm, 30 * mm, doc.width - 58 * mm], repeatRows=1)
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
