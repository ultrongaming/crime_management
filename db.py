import os
import sqlite3
from datetime import datetime, date

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "crimes.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    badge_no TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'officer',
    department TEXT DEFAULT 'General Investigation',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS criminal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    age INTEGER,
    gender TEXT,
    address TEXT,
    identifying_marks TEXT,
    status TEXT DEFAULT 'Wanted',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS case_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    crime_type TEXT NOT NULL,
    description TEXT,
    location TEXT,
    date_reported TEXT,
    status TEXT DEFAULT 'Open',
    priority TEXT DEFAULT 'Medium',
    officer_id INTEGER REFERENCES user(id) ON DELETE SET NULL,
    criminal_id INTEGER REFERENCES criminal(id) ON DELETE SET NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS case_note (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES case_file(id) ON DELETE CASCADE,
    author TEXT,
    content TEXT NOT NULL,
    created_at TEXT
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS c FROM user").fetchone()["c"]
    if existing:
        conn.close()
        return

    def make_user(full_name, badge_no, username, password, role, department):
        conn.execute(
            "INSERT INTO user (full_name, badge_no, username, password_hash, role, department, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (full_name, badge_no, username, generate_password_hash(password), role, department, now()),
        )

    make_user("Alex Whitfield", "ADM-001", "admin", "admin123", "admin", "Bureau of Investigation")
    make_user("Priya Nair", "OFC-104", "pnair", "officer123", "officer", "Homicide")
    make_user("Marcus Reyes", "OFC-207", "mreyes", "officer123", "officer", "Narcotics")
    conn.commit()

    officer1 = conn.execute("SELECT id FROM user WHERE username='pnair'").fetchone()["id"]
    officer2 = conn.execute("SELECT id FROM user WHERE username='mreyes'").fetchone()["id"]

    conn.execute(
        "INSERT INTO criminal (full_name, age, gender, address, identifying_marks, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Daniel Kray", 34, "Male", "14 Foundry Row, Millbrook",
         "Scar above left eyebrow, anchor tattoo on right forearm", "Wanted", now()),
    )
    conn.execute(
        "INSERT INTO criminal (full_name, age, gender, address, identifying_marks, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Selena Voss", 29, "Female", "88 Harbor View Apts, Eastport",
         "No distinguishing marks on file", "In Custody", now()),
    )
    conn.commit()

    criminal1 = conn.execute("SELECT id FROM criminal WHERE full_name='Daniel Kray'").fetchone()["id"]
    criminal2 = conn.execute("SELECT id FROM criminal WHERE full_name='Selena Voss'").fetchone()["id"]

    def make_case(case_number, title, crime_type, description, location, status, priority, officer_id, criminal_id):
        conn.execute(
            "INSERT INTO case_file (case_number, title, crime_type, description, location, date_reported, "
            "status, priority, officer_id, criminal_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (case_number, title, crime_type, description, location, date.today().isoformat(),
             status, priority, officer_id, criminal_id, now()),
        )

    year = datetime.utcnow().year
    make_case(f"CR-{year}-0001", "Break-in at Millbrook Hardware", "Burglary",
              "Forced entry through rear service door reported overnight. Cash register and power tools taken.",
              "Millbrook Hardware, 22 Foundry Row", "Under Investigation", "High", officer1, criminal1)
    make_case(f"CR-{year}-0002", "Vehicle theft, Eastport Marina lot", "Grand Theft Auto",
              "Sedan reported stolen from marina parking lot between 9pm and 6am.",
              "Eastport Marina, Dock Street", "Open", "Medium", officer2, None)
    make_case(f"CR-{year}-0003", "Narcotics possession, Harbor View", "Drug Possession",
              "Routine stop led to discovery of controlled substances. Suspect detained pending lab results.",
              "Harbor View Apts, Eastport", "Closed", "Low", officer2, criminal2)
    conn.commit()

    case1_id = conn.execute("SELECT id FROM case_file WHERE case_number=?", (f"CR-{year}-0001",)).fetchone()["id"]
    conn.execute(
        "INSERT INTO case_note (case_id, author, content, created_at) VALUES (?, ?, ?, ?)",
        (case1_id, "Priya Nair",
         "Canvassed neighboring stores, no working CCTV found. Pulling traffic cam footage next.", now()),
    )
    conn.commit()
    conn.close()
