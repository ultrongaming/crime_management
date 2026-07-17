import os
from datetime import datetime, date
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, flash, session, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

import db as dbm

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-this-in-production"


# ---------------------------------------------------------------------------
# Current-user handling (lightweight, session based)
# ---------------------------------------------------------------------------

class AnonymousUser:
    is_authenticated = False
    is_admin = False


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = AnonymousUser()
    else:
        conn = dbm.get_db()
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if row is None:
            g.user = AnonymousUser()
        else:
            g.user = dict(row)
            g.user["is_authenticated"] = True
            g.user["is_admin"] = row["role"] == "admin"


@app.context_processor
def inject_user():
    return {"current_user": g.get("user", AnonymousUser()), "current_year": datetime.utcnow().year}


def _is_logged_in():
    return isinstance(g.user, dict) and g.user.get("is_authenticated")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _is_logged_in():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        is_admin = g.user.get("is_admin") if isinstance(g.user, dict) else False
        if not is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def current_user_name():
    return g.user["full_name"] if isinstance(g.user, dict) else "System"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_case_number(conn):
    year = datetime.utcnow().year
    count = conn.execute("SELECT COUNT(*) AS c FROM case_file").fetchone()["c"] + 1
    candidate = f"CR-{year}-{count:04d}"
    while conn.execute("SELECT id FROM case_file WHERE case_number = ?", (candidate,)).fetchone():
        count += 1
        candidate = f"CR-{year}-{count:04d}"
    return candidate


def dashboard_stats(conn):
    def count(where="", params=()):
        return conn.execute(f"SELECT COUNT(*) AS c FROM case_file {where}", params).fetchone()["c"]

    return {
        "total_cases": count(),
        "open_cases": count("WHERE status = ?", ("Open",)),
        "investigating": count("WHERE status = ?", ("Under Investigation",)),
        "closed_cases": count("WHERE status = ?", ("Closed",)),
        "total_criminals": conn.execute("SELECT COUNT(*) AS c FROM criminal").fetchone()["c"],
        "wanted": conn.execute("SELECT COUNT(*) AS c FROM criminal WHERE status = ?", ("Wanted",)).fetchone()["c"],
    }


def slugify_status(value):
    return value.lower().replace(" ", "-")


app.jinja_env.filters["slug"] = slugify_status


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if _is_logged_in():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = dbm.get_db()
        row = conn.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["user_id"] = row["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid badge username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    conn = dbm.get_db()
    stats = dashboard_stats(conn)
    recent_cases = conn.execute(
        "SELECT * FROM case_file ORDER BY created_at DESC LIMIT 6"
    ).fetchall()
    recent_wanted = conn.execute(
        "SELECT * FROM criminal WHERE status = 'Wanted' ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats, recent_cases=recent_cases, recent_wanted=recent_wanted)


# ---------------------------------------------------------------------------
# Case routes
# ---------------------------------------------------------------------------

@app.route("/cases")
@login_required
def cases():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    conn = dbm.get_db()
    sql = ("SELECT c.*, u.full_name AS officer_name FROM case_file c "
           "LEFT JOIN user u ON c.officer_id = u.id WHERE 1=1")
    params = []
    if q:
        sql += " AND (c.title LIKE ? OR c.case_number LIKE ? OR c.crime_type LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    sql += " ORDER BY c.created_at DESC"
    all_cases = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("cases.html", cases=all_cases, q=q, status=status)


@app.route("/cases/new", methods=["GET", "POST"])
@login_required
def new_case():
    conn = dbm.get_db()
    officers = conn.execute("SELECT * FROM user ORDER BY full_name").fetchall()
    criminals = conn.execute("SELECT * FROM criminal ORDER BY full_name").fetchall()
    if request.method == "POST":
        case_number = generate_case_number(conn)
        date_str = request.form.get("date_reported") or date.today().isoformat()
        conn.execute(
            "INSERT INTO case_file (case_number, title, crime_type, description, location, date_reported, "
            "status, priority, officer_id, criminal_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                case_number,
                request.form["title"].strip(),
                request.form["crime_type"].strip(),
                request.form.get("description", "").strip(),
                request.form.get("location", "").strip(),
                date_str,
                request.form.get("status", "Open"),
                request.form.get("priority", "Medium"),
                request.form.get("officer_id") or None,
                request.form.get("criminal_id") or None,
                dbm.now(),
            ),
        )
        conn.commit()
        new_id = conn.execute("SELECT id FROM case_file WHERE case_number = ?", (case_number,)).fetchone()["id"]
        conn.close()
        flash(f"Case {case_number} filed successfully.", "success")
        return redirect(url_for("case_detail", case_id=new_id))
    conn.close()
    return render_template("add_case.html", officers=officers, criminals=criminals, today=date.today().isoformat())


@app.route("/cases/<int:case_id>")
@login_required
def case_detail(case_id):
    conn = dbm.get_db()
    case = conn.execute("SELECT * FROM case_file WHERE id = ?", (case_id,)).fetchone()
    if case is None:
        conn.close()
        abort(404)
    officer = None
    if case["officer_id"]:
        officer = conn.execute("SELECT * FROM user WHERE id = ?", (case["officer_id"],)).fetchone()
    criminal = None
    if case["criminal_id"]:
        criminal = conn.execute("SELECT * FROM criminal WHERE id = ?", (case["criminal_id"],)).fetchone()
    notes = conn.execute(
        "SELECT * FROM case_note WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
    ).fetchall()
    conn.close()
    return render_template("case_detail.html", case=case, officer=officer, criminal=criminal, notes=notes)


@app.route("/cases/<int:case_id>/edit", methods=["GET", "POST"])
@login_required
def edit_case(case_id):
    conn = dbm.get_db()
    case = conn.execute("SELECT * FROM case_file WHERE id = ?", (case_id,)).fetchone()
    if case is None:
        conn.close()
        abort(404)
    officers = conn.execute("SELECT * FROM user ORDER BY full_name").fetchall()
    criminals = conn.execute("SELECT * FROM criminal ORDER BY full_name").fetchall()
    if request.method == "POST":
        conn.execute(
            "UPDATE case_file SET title=?, crime_type=?, description=?, location=?, status=?, priority=?, "
            "officer_id=?, criminal_id=? WHERE id=?",
            (
                request.form["title"].strip(),
                request.form["crime_type"].strip(),
                request.form.get("description", "").strip(),
                request.form.get("location", "").strip(),
                request.form.get("status", "Open"),
                request.form.get("priority", "Medium"),
                request.form.get("officer_id") or None,
                request.form.get("criminal_id") or None,
                case_id,
            ),
        )
        conn.commit()
        conn.close()
        flash(f"Case {case['case_number']} updated.", "success")
        return redirect(url_for("case_detail", case_id=case_id))
    conn.close()
    return render_template("edit_case.html", case=case, officers=officers, criminals=criminals)


@app.route("/cases/<int:case_id>/delete", methods=["POST"])
@login_required
def delete_case(case_id):
    conn = dbm.get_db()
    case = conn.execute("SELECT * FROM case_file WHERE id = ?", (case_id,)).fetchone()
    conn.execute("DELETE FROM case_file WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()
    if case:
        flash(f"Case {case['case_number']} deleted.", "success")
    return redirect(url_for("cases"))


@app.route("/cases/<int:case_id>/notes", methods=["POST"])
@login_required
def add_note(case_id):
    content = request.form.get("content", "").strip()
    if content:
        conn = dbm.get_db()
        conn.execute(
            "INSERT INTO case_note (case_id, author, content, created_at) VALUES (?, ?, ?, ?)",
            (case_id, current_user_name(), content, dbm.now()),
        )
        conn.commit()
        conn.close()
        flash("Note added to case file.", "success")
    return redirect(url_for("case_detail", case_id=case_id))


# ---------------------------------------------------------------------------
# Criminal record routes
# ---------------------------------------------------------------------------

@app.route("/criminals")
@login_required
def criminals():
    q = request.args.get("q", "").strip()
    conn = dbm.get_db()
    sql = "SELECT * FROM criminal WHERE 1=1"
    params = []
    if q:
        sql += " AND (full_name LIKE ? OR address LIKE ?)"
        like = f"%{q}%"
        params += [like, like]
    sql += " ORDER BY created_at DESC"
    all_criminals = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("criminals.html", criminals=all_criminals, q=q)


@app.route("/criminals/new", methods=["GET", "POST"])
@login_required
def new_criminal():
    if request.method == "POST":
        conn = dbm.get_db()
        conn.execute(
            "INSERT INTO criminal (full_name, age, gender, address, identifying_marks, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                request.form["full_name"].strip(),
                request.form.get("age") or None,
                request.form.get("gender", ""),
                request.form.get("address", "").strip(),
                request.form.get("identifying_marks", "").strip(),
                request.form.get("status", "Wanted"),
                dbm.now(),
            ),
        )
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.close()
        flash("Record created.", "success")
        return redirect(url_for("criminal_detail", criminal_id=new_id))
    return render_template("add_criminal.html")


@app.route("/criminals/<int:criminal_id>")
@login_required
def criminal_detail(criminal_id):
    conn = dbm.get_db()
    criminal = conn.execute("SELECT * FROM criminal WHERE id = ?", (criminal_id,)).fetchone()
    if criminal is None:
        conn.close()
        abort(404)
    linked_cases = conn.execute("SELECT * FROM case_file WHERE criminal_id = ?", (criminal_id,)).fetchall()
    conn.close()
    return render_template("criminal_detail.html", criminal=criminal, cases=linked_cases)


@app.route("/criminals/<int:criminal_id>/edit", methods=["GET", "POST"])
@login_required
def edit_criminal(criminal_id):
    conn = dbm.get_db()
    criminal = conn.execute("SELECT * FROM criminal WHERE id = ?", (criminal_id,)).fetchone()
    if criminal is None:
        conn.close()
        abort(404)
    if request.method == "POST":
        conn.execute(
            "UPDATE criminal SET full_name=?, age=?, gender=?, address=?, identifying_marks=?, status=? WHERE id=?",
            (
                request.form["full_name"].strip(),
                request.form.get("age") or None,
                request.form.get("gender", ""),
                request.form.get("address", "").strip(),
                request.form.get("identifying_marks", "").strip(),
                request.form.get("status", "Wanted"),
                criminal_id,
            ),
        )
        conn.commit()
        conn.close()
        flash("Record updated.", "success")
        return redirect(url_for("criminal_detail", criminal_id=criminal_id))
    conn.close()
    return render_template("edit_criminal.html", criminal=criminal)


@app.route("/criminals/<int:criminal_id>/delete", methods=["POST"])
@login_required
def delete_criminal(criminal_id):
    conn = dbm.get_db()
    conn.execute("DELETE FROM criminal WHERE id = ?", (criminal_id,))
    conn.commit()
    conn.close()
    flash("Record deleted.", "success")
    return redirect(url_for("criminals"))


# ---------------------------------------------------------------------------
# Officers (admin only)
# ---------------------------------------------------------------------------

@app.route("/officers")
@login_required
@admin_required
def officers():
    conn = dbm.get_db()
    all_officers = conn.execute(
        "SELECT u.*, "
        "(SELECT COUNT(*) FROM case_file c WHERE c.officer_id = u.id AND c.status != 'Closed') AS open_case_count "
        "FROM user u ORDER BY full_name"
    ).fetchall()
    conn.close()
    return render_template("officers.html", officers=all_officers)


@app.route("/officers/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_officer():
    if request.method == "POST":
        conn = dbm.get_db()
        try:
            conn.execute(
                "INSERT INTO user (full_name, badge_no, username, password_hash, role, department, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    request.form["full_name"].strip(),
                    request.form["badge_no"].strip(),
                    request.form["username"].strip(),
                    generate_password_hash(request.form["password"]),
                    request.form.get("role", "officer"),
                    request.form.get("department", "General Investigation").strip(),
                    dbm.now(),
                ),
            )
            conn.commit()
            flash("Account created.", "success")
        except Exception:
            flash("Could not create account — badge number or username may already be in use.", "error")
        finally:
            conn.close()
        return redirect(url_for("officers"))
    return render_template("add_officer.html")


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You don't have access to this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="That record couldn't be found."), 404


if __name__ == "__main__":
    dbm.init_db()
    dbm.seed_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
