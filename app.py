from flask import Flask, render_template, request, jsonify
import sqlite3
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from datetime import datetime, time, timedelta
import re

app = Flask(__name__)

DATABASE = "attendance.db"

# =========================================================
# ATTENDANCE CONFIG
# =========================================================

# Class is considered to start at this time each day.
CLASS_START_TIME = time(8, 0)      # 08:00 AM
LATE_GRACE_MINUTES = 15            # scans after start+grace are "Late"

ALLOWED_STATUSES = {"Present", "Late", "Absent"}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            course TEXT,
            year_level TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (student_id)
            REFERENCES students(student_id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# QR DATA PROCESSING
# =========================================================

def extract_student_id(qr_data):
    """
    Gets a student ID from common QR formats.

    Examples supported:

    2026-0001

    Student ID: 2026-0001

    ID: 2026-0001

    https://example.com/student/2026-0001
    """

    qr_data = qr_data.strip()

    if not qr_data:
        return None

    # If the QR contains a plain student ID
    plain_id = re.fullmatch(
        r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*",
        qr_data
    )

    if plain_id:
        return qr_data

    # Look for "Student ID: 2026-0001"
    match = re.search(
        r"(?:student\s*id|studentid|id)\s*[:#=\-]?\s*([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)",
        qr_data,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    # Try to get an ID from the end of a URL
    match = re.search(
        r"/([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)/?$",
        qr_data
    )

    if match:
        return match.group(1)

    return None


def determine_status(now):
    """
    Decides Present vs Late based on CLASS_START_TIME + grace period.
    """
    cutoff_dt = datetime.combine(now.date(), CLASS_START_TIME) + timedelta(
        minutes=LATE_GRACE_MINUTES
    )

    if now <= cutoff_dt:
        return "Present"

    return "Late"


def decode_image_from_request():
    """
    Shared helper: pulls 'image' from request.files, decodes it with
    OpenCV, and returns (image, error_response). Only one of the two
    will be set.
    """
    if "image" not in request.files:
        return None, jsonify({
            "success": False,
            "message": "No image received."
        })

    image_file = request.files["image"]
    file_bytes = image_file.read()

    if not file_bytes:
        return None, jsonify({
            "success": False,
            "message": "Empty image received."
        })

    image_array = np.frombuffer(file_bytes, np.uint8)

    try:
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except cv2.error:
        image = None

    if image is None:
        return None, jsonify({
            "success": False,
            "message": "Could not read camera image."
        })

    return image, None


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


# =========================================================
# SCANNER PAGE
# =========================================================

@app.route("/scanner")
def scanner():
    return render_template("scanner.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    conn = get_db()

    students = conn.execute("""
        SELECT *
        FROM students
        ORDER BY name COLLATE NOCASE
    """).fetchall()

    attendance = conn.execute("""
        SELECT
            attendance.id,
            attendance.student_id,
            students.name,
            students.course,
            students.year_level,
            attendance.date,
            attendance.time,
            attendance.status
        FROM attendance
        JOIN students
        ON attendance.student_id = students.student_id
        ORDER BY attendance.id DESC
    """).fetchall()

    total_students = conn.execute("""
        SELECT COUNT(*) AS total
        FROM students
    """).fetchone()["total"]

    today = datetime.now().strftime("%Y-%m-%d")

    present_today = conn.execute("""
        SELECT COUNT(*) AS total
        FROM attendance
        WHERE date = ?
        AND status IN ('Present', 'Late')
    """, (today,)).fetchone()["total"]

    conn.close()

    return render_template(
        "dashboard.html",
        students=students,
        attendance=attendance,
        total_students=total_students,
        present_today=present_today,
        today=today
    )


# =========================================================
# DECODE QR ONLY
# Used during student registration
# =========================================================

@app.route("/decode_qr", methods=["POST"])
def decode_qr():

    image, error = decode_image_from_request()
    if error:
        return error

    qr_codes = decode(image)

    if not qr_codes:
        return jsonify({
            "success": False,
            "message": "No QR code detected."
        })

    qr_data = qr_codes[0].data.decode(
        "utf-8",
        errors="ignore"
    ).strip()

    student_id = extract_student_id(qr_data)

    if not student_id:
        return jsonify({
            "success": False,
            "message": "QR code detected, but no Student ID could be identified.",
            "qr_data": qr_data
        })

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM students
        WHERE student_id = ?
    """, (student_id,)).fetchone()

    conn.close()

    if existing:
        return jsonify({
            "success": True,
            "already_registered": True,
            "student": {
                "student_id": existing["student_id"],
                "name": existing["name"],
                "course": existing["course"],
                "year_level": existing["year_level"]
            },
            "message": "This student is already registered."
        })

    return jsonify({
        "success": True,
        "already_registered": False,
        "student_id": student_id,
        "qr_data": qr_data,
        "message": "QR code scanned successfully."
    })


# =========================================================
# REGISTER STUDENT
# =========================================================

@app.route("/register", methods=["POST"])
def register():

    student_id = request.form.get("student_id", "").strip()
    name = request.form.get("name", "").strip()
    course = request.form.get("course", "").strip()
    year_level = request.form.get("year_level", "").strip()

    if not student_id:
        return jsonify({
            "success": False,
            "message": "Please scan the student's QR code first."
        })

    if not name:
        return jsonify({
            "success": False,
            "message": "Full name is required."
        })

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM students
        WHERE student_id = ?
    """, (student_id,)).fetchone()

    if existing:
        conn.close()

        return jsonify({
            "success": False,
            "message": "This student is already registered."
        })

    try:

        conn.execute("""
            INSERT INTO students
            (student_id, name, course, year_level)
            VALUES (?, ?, ?, ?)
        """, (student_id, name, course, year_level))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"{name} has been successfully registered!"
        })

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify({
            "success": False,
            "message": "This Student ID is already registered."
        })


# =========================================================
# ATTENDANCE QR SCANNER
# =========================================================

@app.route("/scan", methods=["POST"])
def scan():

    image, error = decode_image_from_request()
    if error:
        return error

    qr_codes = decode(image)

    if not qr_codes:
        return jsonify({
            "success": False,
            "message": "No QR code detected."
        })

    qr_data = qr_codes[0].data.decode(
        "utf-8",
        errors="ignore"
    ).strip()

    student_id = extract_student_id(qr_data)

    if not student_id:
        return jsonify({
            "success": False,
            "message": "QR code detected, but no Student ID could be identified."
        })

    conn = get_db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE student_id = ?
    """, (student_id,)).fetchone()

    if not student:
        conn.close()

        return jsonify({
            "success": False,
            "registered": False,
            "qr_data": qr_data,
            "student_id": student_id,
            "message": f"Student ID '{student_id}' is not registered."
        })

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%I:%M:%S %p")

    existing_attendance = conn.execute("""
        SELECT *
        FROM attendance
        WHERE student_id = ?
        AND date = ?
    """, (student_id, today)).fetchone()

    if existing_attendance:
        conn.close()

        return jsonify({
            "success": True,
            "already_scanned": True,
            "student": {
                "student_id": student["student_id"],
                "name": student["name"],
                "course": student["course"],
                "year_level": student["year_level"]
            },
            "date": existing_attendance["date"],
            "time": existing_attendance["time"],
            "status": existing_attendance["status"],
            "message": f"{student['name']} is already marked {existing_attendance['status'].lower()} today."
        })

    status = determine_status(now)

    conn.execute("""
        INSERT INTO attendance
        (student_id, date, time, status)
        VALUES (?, ?, ?, ?)
    """, (student_id, today, current_time, status))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "already_scanned": False,
        "student": {
            "student_id": student["student_id"],
            "name": student["name"],
            "course": student["course"],
            "year_level": student["year_level"]
        },
        "date": today,
        "time": current_time,
        "status": status,
        "message": f"Attendance recorded for {student['name']} ({status})!"
    })


# =========================================================
# MANUAL OVERRIDE (professor edits a status)
# =========================================================

@app.route("/update_attendance", methods=["POST"])
def update_attendance():

    student_id = request.form.get("student_id", "").strip()
    date = request.form.get("date", "").strip()
    status = request.form.get("status", "").strip()

    if not student_id or not date:
        return jsonify({
            "success": False,
            "message": "Student ID and date are required."
        })

    if status not in ALLOWED_STATUSES:
        return jsonify({
            "success": False,
            "message": f"Status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}."
        })

    conn = get_db()

    student = conn.execute("""
        SELECT * FROM students WHERE student_id = ?
    """, (student_id,)).fetchone()

    if not student:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"Student ID '{student_id}' is not registered."
        })

    existing = conn.execute("""
        SELECT * FROM attendance
        WHERE student_id = ? AND date = ?
    """, (student_id, date)).fetchone()

    if existing:
        conn.execute("""
            UPDATE attendance
            SET status = ?
            WHERE student_id = ? AND date = ?
        """, (status, student_id, date))
        message = f"{student['name']}'s status for {date} updated to {status}."
    else:
        current_time = datetime.now().strftime("%I:%M:%S %p")
        conn.execute("""
            INSERT INTO attendance (student_id, date, time, status)
            VALUES (?, ?, ?, ?)
        """, (student_id, date, current_time, status))
        message = f"{student['name']} marked {status} for {date}."

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": message
    })


# =========================================================
# MARK ABSENTEES
# End-of-day sweep: any registered student with no attendance
# row for the given date gets marked Absent.
# =========================================================

@app.route("/mark_absentees", methods=["POST"])
def mark_absentees():

    date = request.form.get("date", "").strip()

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()

    missing_students = conn.execute("""
        SELECT s.student_id, s.name
        FROM students s
        WHERE s.student_id NOT IN (
            SELECT student_id FROM attendance WHERE date = ?
        )
    """, (date,)).fetchall()

    current_time = datetime.now().strftime("%I:%M:%S %p")

    for student in missing_students:
        conn.execute("""
            INSERT INTO attendance (student_id, date, time, status)
            VALUES (?, ?, ?, 'Absent')
        """, (student["student_id"], date, current_time))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "marked_count": len(missing_students),
        "message": f"{len(missing_students)} student(s) marked Absent for {date}."
    })


# =========================================================
# DELETE STUDENT
# =========================================================

@app.route("/delete_student/<student_id>", methods=["POST"])
def delete_student(student_id):

    conn = get_db()

    conn.execute("""
        DELETE FROM attendance
        WHERE student_id = ?
    """, (student_id,))

    conn.execute("""
        DELETE FROM students
        WHERE student_id = ?
    """, (student_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Student deleted successfully."
    })


# =========================================================
# RUN APPLICATION
# =========================================================

init_db()
