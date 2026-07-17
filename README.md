# Precinct Records — Crime Management System

A Flask website for filing and tracking crime cases, suspect/individual records,
and officer accounts. Comes pre-loaded with demo data so you can explore it
immediately.

## Features

- **Sign in** with role-based access (admin vs. officer)
- **Dashboard** with live counts of open / under-investigation / closed cases and wanted individuals
- **Case files** — file new cases, assign an officer, link a suspect, search & filter by status, add timestamped investigation notes, edit or delete
- **Individual records** — track suspects with status (Wanted / In Custody / Released / Convicted), search by name or address
- **Officer accounts** — admins can create new officer/admin logins and see each officer's open case load
- No JavaScript framework required — plain Flask + server-rendered HTML, styled as a dark "case file" records room

## Requirements

- Python 3.9+
- pip

## Setup

```bash
cd crime_management
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in your browser.

The first run automatically creates `instance/crimes.db` (SQLite) and seeds it
with demo accounts and sample cases.

## Demo accounts

| Username | Password    | Role    |
|----------|-------------|---------|
| admin    | admin123    | Admin   |
| pnair    | officer123  | Officer |
| mreyes   | officer123  | Officer |

Admins can additionally reach **Officers** to create new accounts. Officers see
everything except that page.

## Project structure

```
crime_management/
├── app.py              # Flask routes
├── db.py                # SQLite schema, connection helper, demo-data seeding
├── requirements.txt
├── instance/
│   └── crimes.db         # created automatically on first run
├── static/css/style.css
└── templates/            # Jinja2 templates
```

## Resetting the data

Delete `instance/crimes.db` and restart the app — it will be recreated and
reseeded automatically.

## Notes on production use

This is built for local use / learning / demoing. Before deploying it anywhere
real:
- Set a strong, secret `SECRET_KEY` via an environment variable instead of the hardcoded dev value in `app.py`.
- Turn off `debug=True`.
- Put it behind a real WSGI server (gunicorn/uwsgi) rather than the Flask dev server.
- Consider stronger password policies and rate-limiting the login route.
