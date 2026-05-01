#python -m pip install streamlit pandas plotly

#python -m streamlit run adits_app.py

import streamlit as st
import sqlite3
import hashlib
import os
import json
import csv
import io
from datetime import datetime, date
from contextlib import contextmanager

DB_PATH = "adits.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_css():
    st.markdown("""
    <style>
    .main {
        background-color: #0f172a;
    }

    .stApp {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        color: white;
    }

    .card {
        background: linear-gradient(145deg, #1e293b, #334155);
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0px 4px 20px rgba(0,0,0,0.4);
        margin-bottom: 15px;
        transition: 0.3s;
    }

    .card:hover {
        transform: scale(1.02);
    }

    .title {
        font-size: 28px;
        font-weight: bold;
        color: #38bdf8;
    }

    .subtitle {
        font-size: 16px;
        color: #94a3b8;
    }

    .metric-card {
        background: linear-gradient(145deg, #1e40af, #3b82f6);
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        color: white;
    }

    .small-card {
        background: #1e293b;
        padding: 10px;
        border-radius: 10px;
        margin-bottom: 10px;
    }

    button {
        border-radius: 10px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def register_page():
    st.title("Register New User")

    with st.form("register_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["Project Owner", "Analyst", "Viewer"])
        submit = st.form_submit_button("Register")

    if submit:
        if not username or not password:
            st.error("All fields required.")
            return

        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE username=?",
                (username,)
            ).fetchone()

            if existing:
                st.error("Username already exists.")
                return

            conn.execute(
                "INSERT INTO users(username,password_hash,role,is_active,created_at) VALUES(?,?,?,1,?)",
                (username, hash_password(password), role, datetime.now().isoformat())
            )

            log_audit(conn, None, "REGISTER_USER", "User", None, username)

        st.success("User registered successfully. Please go to login.")

def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Administrator','Project Owner','Analyst','Viewer')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                start_date TEXT,
                owner_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS project_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Analyst','Viewer')),
                UNIQUE(project_id, user_id),
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS assumptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence_level REAL NOT NULL,
                impact_weight REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Valid' CHECK(status IN ('Valid','At Risk','Invalid')),
                owner_id INTEGER,
                expiration_date TEXT,
                justification TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS assumption_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assumption_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence_level REAL NOT NULL,
                impact_weight REAL NOT NULL,
                status TEXT NOT NULL,
                owner_id INTEGER,
                expiration_date TEXT,
                justification TEXT,
                version_number INTEGER NOT NULL,
                modified_by INTEGER,
                modified_at TEXT NOT NULL,
                comment TEXT,
                FOREIGN KEY(assumption_id) REFERENCES assumptions(id)
            );
            CREATE TABLE IF NOT EXISTS dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL,
                child_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(parent_id, child_id),
                FOREIGN KEY(parent_id) REFERENCES assumptions(id),
                FOREIGN KEY(child_id) REFERENCES assumptions(id)
            );
            CREATE TABLE IF NOT EXISTS risk_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                risk_index REAL NOT NULL,
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT,
                logged_at TEXT NOT NULL
            );
        """)
        existing = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not existing:
            now = datetime.now().isoformat()
            conn.execute(
                "INSERT INTO users(username,password_hash,role,is_active,created_at) VALUES(?,?,?,1,?)",
                ("admin", hash_password("admin123"), "Administrator", now)
            )

def log_audit(conn, user_id, action, entity_type=None, entity_id=None, details=None):
    conn.execute(
        "INSERT INTO audit_log(user_id,action,entity_type,entity_id,details,logged_at) VALUES(?,?,?,?,?,?)",
        (user_id, action, entity_type, entity_id, details, datetime.now().isoformat())
    )

def get_version_number(conn, assumption_id):
    row = conn.execute(
        "SELECT COALESCE(MAX(version_number),0) FROM assumption_versions WHERE assumption_id=?",
        (assumption_id,)
    ).fetchone()
    return row[0] + 1

def save_version(conn, assumption_id, user_id, comment=None):
    row = conn.execute("SELECT * FROM assumptions WHERE id=?", (assumption_id,)).fetchone()
    if not row:
        return
    vnum = get_version_number(conn, assumption_id)
    conn.execute(
        """INSERT INTO assumption_versions
           (assumption_id,description,category,confidence_level,impact_weight,status,owner_id,
            expiration_date,justification,version_number,modified_by,modified_at,comment)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (assumption_id, row["description"], row["category"], row["confidence_level"],
         row["impact_weight"], row["status"], row["owner_id"], row["expiration_date"],
         row["justification"], vnum, user_id, datetime.now().isoformat(), comment)
    )

def has_circular_dependency(conn, parent_id, child_id):
    if parent_id == child_id:
        return True
    visited = set()
    stack = [child_id]
    while stack:
        node = stack.pop()
        if node == parent_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        children = conn.execute(
            "SELECT child_id FROM dependencies WHERE parent_id=?", (node,)
        ).fetchall()
        for c in children:
            stack.append(c["child_id"])
    return False

def get_all_dependents(conn, assumption_id):
    result = []
    stack = [assumption_id]
    visited = set()
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        children = conn.execute(
            "SELECT child_id FROM dependencies WHERE parent_id=?", (node,)
        ).fetchall()
        for c in children:
            if c["child_id"] not in visited:
                result.append(c["child_id"])
                stack.append(c["child_id"])
    return result

def get_depth_from_root(conn, assumption_id):
    stack = [(assumption_id, 0)]
    visited = set()
    max_depth = 0
    while stack:
        node, d = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        if d > max_depth:
            max_depth = d
        parents = conn.execute(
            "SELECT parent_id FROM dependencies WHERE child_id=?", (node,)
        ).fetchall()
        for p in parents:
            stack.append((p["parent_id"], d + 1))
    return max_depth

def cascade_evaluate(conn, assumption_id, user_id):
    dependents = get_all_dependents(conn, assumption_id)
    root = conn.execute("SELECT status FROM assumptions WHERE id=?", (assumption_id,)).fetchone()
    if not root:
        return []
    root_status = root["status"]
    changed = []
    for dep_id in dependents:
        depth = get_depth_from_root(conn, dep_id)
        dep = conn.execute("SELECT * FROM assumptions WHERE id=?", (dep_id,)).fetchone()
        if not dep:
            continue
        new_status = dep["status"]
        if root_status == "Invalid":
            if depth <= 2:
                new_status = "Invalid"
            else:
                new_status = "At Risk"
        elif root_status == "At Risk":
            new_status = "At Risk"
        elif root_status == "Valid":
            parents = conn.execute(
                "SELECT a.status FROM dependencies d JOIN assumptions a ON d.parent_id=a.id WHERE d.child_id=?",
                (dep_id,)
            ).fetchall()
            statuses = [p["status"] for p in parents]
            if all(s == "Valid" for s in statuses):
                new_status = "Valid"
            elif any(s == "Invalid" for s in statuses):
                new_status = "At Risk"
        if new_status != dep["status"]:
            save_version(conn, dep_id, user_id, "Cascade evaluation update")
            conn.execute(
                "UPDATE assumptions SET status=?,updated_at=? WHERE id=?",
                (new_status, datetime.now().isoformat(), dep_id)
            )
            changed.append(dep_id)
    return changed

def calculate_risk_index(conn, project_id):
    assumptions = conn.execute(
        "SELECT * FROM assumptions WHERE project_id=?", (project_id,)
    ).fetchall()
    if not assumptions:
        return 0.0
    total = 0.0
    weight_sum = 0.0
    for a in assumptions:
        if a["status"] == "Invalid":
            status_factor = 1.0
        elif a["status"] == "At Risk":
            status_factor = 0.5
        else:
            status_factor = 0.0
        risk = (1 - a["confidence_level"] / 100) * (a["impact_weight"] / 10) * status_factor
        total += risk * a["impact_weight"]
        weight_sum += a["impact_weight"]
    if weight_sum == 0:
        return 0.0
    return round((total / weight_sum) * 100, 2)

def get_user_projects(conn, user_id, role):
    if role == "Administrator":
        return conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    elif role == "Project Owner":
        return conn.execute(
            "SELECT * FROM projects WHERE owner_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT p.* FROM projects p
               JOIN project_members pm ON p.id=pm.project_id
               WHERE pm.user_id=? ORDER BY p.created_at DESC""",
            (user_id,)
        ).fetchall()
        return rows

def can_access_project(conn, user_id, project_id, role):
    if role == "Administrator":
        return True
    if role == "Project Owner":
        with get_conn() as c:
            row = c.execute(
                "SELECT id FROM projects WHERE id=? AND owner_id=?", (project_id, user_id)
            ).fetchone()
        return row is not None
    with get_conn() as c:
        row = c.execute(
            "SELECT id FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user_id)
        ).fetchone()
    return row is not None

def get_project_role(conn, user_id, project_id, global_role):
    if global_role == "Administrator":
        return "Administrator"
    if global_role == "Project Owner":
        row = conn.execute(
            "SELECT id FROM projects WHERE id=? AND owner_id=?", (project_id, user_id)
        ).fetchone()
        if row:
            return "Project Owner"
    row = conn.execute(
        "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
        (project_id, user_id)
    ).fetchone()
    if row:
        return row["role"]
    return None

def sidebar_nav():
    user = st.session_state.get("user")

    st.sidebar.markdown("""
    <div style="font-size:22px;font-weight:bold;color:#38bdf8;">
    ADITS System
    </div>
    """, unsafe_allow_html=True)

    if user:
        st.sidebar.markdown(f"""
        <div style="margin-top:10px;padding:10px;background:#1e293b;border-radius:10px;">
        👤 {user['username']}<br>
        <span style="color:#94a3b8;">{user['role']}</span>
        </div>
        """, unsafe_allow_html=True)

        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

    if user and user["role"] == "Administrator":
        pages = ["Dashboard", "Projects", "Users", "Profile"]
    else:
        pages = ["Dashboard", "Projects", "Profile"]

    choice = st.sidebar.radio("Navigation", pages)

    return choice

def login_page():
    st.markdown('<div class="title">ADITS Platform</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Assumption Dependency and Impact Tracking System</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        st.markdown('<div class="card">', unsafe_allow_html=True)

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if not username or not password:
                st.error("Enter credentials")
                return

            with get_conn() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE username=? AND password_hash=?",
                    (username, hash_password(password))
                ).fetchone()

                if not user:
                    st.error("Invalid login")
                    return

                if not user["is_active"]:
                    st.error("Account disabled")
                    return

                st.session_state["user"] = dict(user)

            st.success("Welcome back")
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="card">', unsafe_allow_html=True)

        username = st.text_input("New Username")
        password = st.text_input("New Password", type="password")
        role = st.selectbox("Role", ["Project Owner", "Analyst", "Viewer"])

        if st.button("Register"):
            if not username or not password:
                st.error("All fields required")
                return

            with get_conn() as conn:
                existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
                if existing:
                    st.error("User exists")
                    return

                conn.execute(
                    "INSERT INTO users(username,password_hash,role,is_active,created_at) VALUES(?,?,?,1,?)",
                    (username, hash_password(password), role, datetime.now().isoformat())
                )

            st.success("Account created")

        st.markdown('</div>', unsafe_allow_html=True)

def dashboard_page():
    user = st.session_state["user"]

    st.markdown('<div class="title">Dashboard Overview</div>', unsafe_allow_html=True)

    with get_conn() as conn:
        projects = get_user_projects(conn, user["id"], user["role"])

        total_projects = len(projects)
        total_assumptions = 0
        at_risk = 0
        invalid = 0

        for p in projects:
            rows = conn.execute(
                "SELECT status FROM assumptions WHERE project_id=?", (p["id"],)
            ).fetchall()

            for r in rows:
                total_assumptions += 1
                if r["status"] == "At Risk":
                    at_risk += 1
                elif r["status"] == "Invalid":
                    invalid += 1

    c1, c2, c3, c4 = st.columns(4)

    c1.markdown(f'<div class="metric-card">Projects<br><h2>{total_projects}</h2></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card">Assumptions<br><h2>{total_assumptions}</h2></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card">At Risk<br><h2>{at_risk}</h2></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="metric-card">Invalid<br><h2>{invalid}</h2></div>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown('<div class="title">Your Projects</div>', unsafe_allow_html=True)

    if not projects:
        st.info("No projects available")
        return

    for p in projects:
        col1, col2 = st.columns([4,1])

        with col1:
            st.markdown(f"""
            <div class="card">
            <div style="font-size:18px;font-weight:bold;color:#38bdf8;">
            {p['name']}
            </div>
            <div style="color:#94a3b8;">
            {p['description'] or "No description"}
            </div>
            <br>
            Status: {"🟢 Active" if p['is_active'] else "🔴 Inactive"}
            </div>
            """, unsafe_allow_html=True)

        with col2:
            if st.button("Open", key=f"open_{p['id']}"):
                st.session_state["active_project_id"] = p["id"]
                st.session_state["force_page"] = "Projects"
                st.rerun()

def users_page():
    user = st.session_state["user"]
    if user["role"] != "Administrator":
        st.error("Access denied.")
        return
    st.title("User Management")
    tab1, tab2 = st.tabs(["All Users", "Create User"])
    with tab1:
        with get_conn() as conn:
            users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        for u in users:
            with st.expander(f"{u['username']} - {u['role']} ({'Active' if u['is_active'] else 'Inactive'})"):
                st.write(f"Created: {u['created_at'][:16]}")
                if u["id"] != user["id"]:
                    if u["is_active"]:
                        if st.button("Deactivate", key=f"deact_{u['id']}"):
                            with get_conn() as conn:
                                conn.execute("UPDATE users SET is_active=0 WHERE id=?", (u["id"],))
                                log_audit(conn, user["id"], "DEACTIVATE_USER", "User", u["id"])
                            st.success("User deactivated.")
                            st.rerun()
                    else:
                        if st.button("Activate", key=f"act_{u['id']}"):
                            with get_conn() as conn:
                                conn.execute("UPDATE users SET is_active=1 WHERE id=?", (u["id"],))
                                log_audit(conn, user["id"], "ACTIVATE_USER", "User", u["id"])
                            st.success("User activated.")
                            st.rerun()
    with tab2:
        st.subheader("Create New User")
        with st.form("create_user_form"):
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["Administrator", "Project Owner", "Analyst", "Viewer"])
            submit = st.form_submit_button("Create User")
        if submit:
            if not new_username or not new_password:
                st.error("All fields required.")
            else:
                try:
                    with get_conn() as conn:
                        conn.execute(
                            "INSERT INTO users(username,password_hash,role,is_active,created_at) VALUES(?,?,?,1,?)",
                            (new_username, hash_password(new_password), new_role, datetime.now().isoformat())
                        )
                        log_audit(conn, user["id"], "CREATE_USER", "User", None, new_username)
                    st.success(f"User '{new_username}' created.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username already exists.")

def profile_page():
    user = st.session_state["user"]
    st.title("My Profile")
    st.write(f"Username: {user['username']}")
    st.write(f"Role: {user['role']}")
    st.divider()
    st.subheader("Change Password")
    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        submit = st.form_submit_button("Update Password")
    if submit:
        if not current_password or not new_password or not confirm_password:
            st.error("All fields required.")
        elif new_password != confirm_password:
            st.error("New passwords do not match.")
        else:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT id FROM users WHERE id=? AND password_hash=?",
                    (user["id"], hash_password(current_password))
                ).fetchone()
                if not row:
                    st.error("Current password is incorrect.")
                else:
                    conn.execute(
                        "UPDATE users SET password_hash=? WHERE id=?",
                        (hash_password(new_password), user["id"])
                    )
                    log_audit(conn, user["id"], "CHANGE_PASSWORD", "User", user["id"])
                    st.success("Password updated.")

def projects_page():
    user = st.session_state["user"]
    st.title("Projects")
    active_project_id = st.session_state.get("active_project_id")
    if active_project_id:
        accessible = can_access_project(None, user["id"], active_project_id, user["role"])
        if accessible:
            if st.button("Back to Projects List"):
                st.session_state.pop("active_project_id", None)
                st.rerun()
            project_detail_page(active_project_id)
            return
        else:
            st.session_state.pop("active_project_id", None)

    tab_labels = ["All Projects"]
    if user["role"] in ("Administrator", "Project Owner"):
        tab_labels.append("Create Project")
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        with get_conn() as conn:
            projects = get_user_projects(conn, user["id"], user["role"])
        if not projects:
            st.info("No projects available.")
        for p in projects:
            with st.expander(f"{p['name']} - {'Active' if p['is_active'] else 'Inactive'}"):
                st.write(f"Description: {p['description'] or 'N/A'}")
                st.write(f"Start Date: {p['start_date'] or 'N/A'}")
                with get_conn() as conn:
                    owner = conn.execute("SELECT username FROM users WHERE id=?", (p["owner_id"],)).fetchone()
                    risk = calculate_risk_index(conn, p["id"])
                st.write(f"Owner: {owner['username'] if owner else 'N/A'}")
                st.markdown('<div class="title">Risk Overview</div>', unsafe_allow_html=True)

                st.progress(risk/100)

                st.markdown(f"""
                <div class="card">
                Current Risk Index: <b>{risk}%</b>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Open", key=f"proj_{p['id']}"):
                    st.session_state["active_project_id"] = p["id"]
                    st.rerun()

    if len(tabs) > 1:
        with tabs[1]:
            create_project_form(user)

def create_project_form(user):
    st.subheader("Create New Project")
    with get_conn() as conn:
        owners = conn.execute(
            "SELECT id, username FROM users WHERE role='Project Owner' AND is_active=1"
        ).fetchall()
    owner_options = {o["username"]: o["id"] for o in owners}
    with st.form("create_project_form"):
        name = st.text_input("Project Name")
        description = st.text_area("Description")
        start_date = st.date_input("Start Date", value=date.today())
        selected_owner = None
        if user["role"] == "Administrator":
            if owner_options:
                selected_owner = st.selectbox("Assign Project Owner", list(owner_options.keys()))
            else:
                st.info("No Project Owner accounts exist. Create one in User Management first.")
        submit = st.form_submit_button("Create Project")
    if submit:
        if not name:
            st.error("Project name required.")
            return
        owner_id = None
        if user["role"] == "Administrator" and owner_options and selected_owner:
            owner_id = owner_options.get(selected_owner)
        elif user["role"] == "Project Owner":
            owner_id = user["id"]
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO projects(name,description,start_date,owner_id,is_active,created_at) VALUES(?,?,?,?,1,?)",
                (name, description, str(start_date), owner_id, datetime.now().isoformat())
            )
            log_audit(conn, user["id"], "CREATE_PROJECT", "Project", None, name)
        st.success(f"Project '{name}' created.")
        st.rerun()

def project_detail_page(project_id):
    user = st.session_state["user"]
    with get_conn() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            st.error("Project not found.")
            return
        proj_role = get_project_role(conn, user["id"], project_id, user["role"])

    st.header(f"Project: {project['name']}")
    st.caption(f"Status: {'Active' if project['is_active'] else 'Inactive'} | Your Role: {proj_role}")

    if proj_role in ("Administrator", "Project Owner"):
        tab_labels = ["Assumptions", "Dependencies", "Risk and Reports", "Search and Filter", "Expired Assumptions", "Project Settings", "Membership"]
    else:
        tab_labels = ["Assumptions", "Dependencies", "Risk and Reports", "Search and Filter", "Expired Assumptions"]

    tabs = st.tabs(tab_labels)

    with tabs[0]:
        assumptions_tab(project_id, proj_role, project)
    with tabs[1]:
        dependencies_tab(project_id, proj_role)
    with tabs[2]:
        risk_reports_tab(project_id, proj_role)
    with tabs[3]:
        search_filter_tab(project_id)
    with tabs[4]:
        expired_assumptions_tab(project_id, proj_role)
    if proj_role in ("Administrator", "Project Owner"):
        with tabs[5]:
            project_settings_tab(project_id, proj_role, project)
        with tabs[6]:
            membership_tab(project_id, proj_role)

def assumptions_tab(project_id, proj_role, project):
    user = st.session_state["user"]
    st.subheader("Assumptions")
    with get_conn() as conn:
        assumptions = conn.execute(
            """SELECT a.*, u.username as owner_name
               FROM assumptions a LEFT JOIN users u ON a.owner_id=u.id
               WHERE a.project_id=? ORDER BY a.created_at DESC""",
            (project_id,)
        ).fetchall()
        all_users = conn.execute("SELECT id, username FROM users WHERE is_active=1").fetchall()

    user_map = {u["username"]: u["id"] for u in all_users}

    if proj_role in ("Project Owner", "Analyst", "Administrator") and project["is_active"]:
        with st.expander("Create New Assumption"):
            with st.form("create_assumption_form"):
                desc = st.text_area("Description")
                cat_options = ["Financial", "Market", "Technical", "Regulatory", "Resource", "Stakeholder", "Other"]
                cat = st.selectbox("Category", cat_options)
                conf = st.slider("Confidence Level (%)", 0.0, 100.0, 80.0, 1.0)
                impact = st.slider("Impact Weight (1-10)", 1.0, 10.0, 5.0, 0.5)
                exp_date = st.date_input("Expiration Date (optional)", value=None)
                owner_name = st.selectbox("Assumption Owner (optional)", ["None"] + list(user_map.keys()))
                submit_a = st.form_submit_button("Create Assumption")
            if submit_a:
                if not desc:
                    st.error("Description required.")
                else:
                    owner_id = user_map.get(owner_name) if owner_name != "None" else None
                    now = datetime.now().isoformat()
                    with get_conn() as conn:
                        cur = conn.execute(
                            "INSERT INTO assumptions(project_id,description,category,confidence_level,impact_weight,status,owner_id,expiration_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (project_id, desc, cat, conf, impact, "Valid", owner_id, str(exp_date) if exp_date else None, now, now)
                        )
                        aid = cur.lastrowid
                        save_version(conn, aid, user["id"], "Initial version")
                        log_audit(conn, user["id"], "CREATE_ASSUMPTION", "Assumption", aid)
                    st.success("Assumption created.")
                    st.rerun()

    if not assumptions:
        st.info("No assumptions yet.")
        return

    cat_options_edit = ["Financial", "Market", "Technical", "Regulatory", "Resource", "Stakeholder", "Other"]

    for a in assumptions:
        with st.expander(f"[{a['status']}]  {a['description'][:80]}"):
            col1, col2 = st.columns(2)
            col1.write(f"Category: {a['category']}")
            col1.write(f"Confidence: {a['confidence_level']}%")
            col1.write(f"Impact Weight: {a['impact_weight']}")
            col2.write(f"Owner: {a['owner_name'] or 'Unassigned'}")
            col2.write(f"Expiration: {a['expiration_date'] or 'None'}")
            col2.write(f"Created: {a['created_at'][:10]}")
            col2.write(f"Updated: {a['updated_at'][:10]}")
            if a["justification"]:
                st.write(f"Justification: {a['justification']}")

            if proj_role in ("Project Owner", "Analyst", "Administrator") and project["is_active"]:
                st.divider()
                act_cols = st.columns(5)

                if act_cols[0].button("Edit", key=f"edit_btn_{a['id']}"):
                    st.session_state[f"editing_{a['id']}"] = not st.session_state.get(f"editing_{a['id']}", False)

                if st.session_state.get(f"editing_{a['id']}"):
                    with st.form(f"edit_form_{a['id']}"):
                        new_desc = st.text_area("Description", value=a["description"])
                        cur_cat_idx = cat_options_edit.index(a["category"]) if a["category"] in cat_options_edit else 0
                        new_cat = st.selectbox("Category", cat_options_edit, index=cur_cat_idx)
                        new_conf = st.slider("Confidence Level (%)", 0.0, 100.0, float(a["confidence_level"]), 1.0, key=f"conf_{a['id']}")
                        new_impact = st.slider("Impact Weight", 1.0, 10.0, float(a["impact_weight"]), 0.5, key=f"imp_{a['id']}")
                        new_status = st.selectbox("Status", ["Valid", "At Risk", "Invalid"], index=["Valid", "At Risk", "Invalid"].index(a["status"]))
                        new_owner = st.selectbox("Owner", ["None"] + list(user_map.keys()))
                        raw_exp = a["expiration_date"]
                        new_exp = st.date_input("Expiration Date", value=date.fromisoformat(raw_exp) if raw_exp else None)
                        justification = st.text_area("Justification Note")
                        version_comment = st.text_input("Version Comment")
                        save_edit = st.form_submit_button("Save Changes")
                        cancel_edit = st.form_submit_button("Cancel")
                    if cancel_edit:
                        st.session_state.pop(f"editing_{a['id']}", None)
                        st.rerun()
                    if save_edit:
                        new_owner_id = user_map.get(new_owner) if new_owner != "None" else None
                        with get_conn() as conn:
                            save_version(conn, a["id"], user["id"], version_comment or "Manual update")
                            conn.execute(
                                "UPDATE assumptions SET description=?,category=?,confidence_level=?,impact_weight=?,status=?,owner_id=?,expiration_date=?,justification=?,updated_at=? WHERE id=?",
                                (new_desc, new_cat, new_conf, new_impact, new_status, new_owner_id, str(new_exp) if new_exp else None, justification, datetime.now().isoformat(), a["id"])
                            )
                            log_audit(conn, user["id"], "UPDATE_ASSUMPTION", "Assumption", a["id"])
                        st.session_state.pop(f"editing_{a['id']}", None)
                        st.success("Assumption updated.")
                        st.rerun()

                if a["status"] != "Invalid":
                    if act_cols[1].button("Invalidate", key=f"inv_btn_{a['id']}"):
                        st.session_state[f"invalidating_{a['id']}"] = True

                if st.session_state.get(f"invalidating_{a['id']}"):
                    with st.form(f"inv_form_{a['id']}"):
                        just = st.text_area("Justification for invalidation")
                        confirm_inv = st.form_submit_button("Confirm Invalidate")
                        cancel_inv = st.form_submit_button("Cancel")
                    if cancel_inv:
                        st.session_state.pop(f"invalidating_{a['id']}", None)
                        st.rerun()
                    if confirm_inv:
                        with get_conn() as conn:
                            save_version(conn, a["id"], user["id"], "Invalidated")
                            conn.execute(
                                "UPDATE assumptions SET status='Invalid', justification=?, updated_at=? WHERE id=?",
                                (just, datetime.now().isoformat(), a["id"])
                            )
                            changed = cascade_evaluate(conn, a["id"], user["id"])
                            log_audit(conn, user["id"], "INVALIDATE_ASSUMPTION", "Assumption", a["id"], f"Cascade changed: {len(changed)}")
                        st.session_state.pop(f"invalidating_{a['id']}", None)
                        st.success(f"Invalidated. {len(changed)} dependent(s) updated.")
                        st.rerun()

                if a["status"] == "Invalid":
                    if act_cols[2].button("Restore", key=f"rest_btn_{a['id']}"):
                        with get_conn() as conn:
                            save_version(conn, a["id"], user["id"], "Restored to Valid")
                            conn.execute(
                                "UPDATE assumptions SET status='Valid', updated_at=? WHERE id=?",
                                (datetime.now().isoformat(), a["id"])
                            )
                            changed = cascade_evaluate(conn, a["id"], user["id"])
                            log_audit(conn, user["id"], "RESTORE_ASSUMPTION", "Assumption", a["id"])
                        st.success(f"Restored. {len(changed)} dependent(s) updated.")
                        st.rerun()

                if proj_role in ("Project Owner", "Administrator"):
                    if act_cols[3].button("Delete", key=f"del_btn_{a['id']}"):
                        with get_conn() as conn:
                            deps = conn.execute(
                                "SELECT id FROM dependencies WHERE parent_id=? OR child_id=?",
                                (a["id"], a["id"])
                            ).fetchall()
                            if deps:
                                st.error("Cannot delete: has dependencies. Remove them first.")
                            else:
                                conn.execute("DELETE FROM assumption_versions WHERE assumption_id=?", (a["id"],))
                                conn.execute("DELETE FROM assumptions WHERE id=?", (a["id"],))
                                log_audit(conn, user["id"], "DELETE_ASSUMPTION", "Assumption", a["id"])
                                st.success("Deleted.")
                                st.rerun()

                if act_cols[4].button("Versions", key=f"ver_btn_{a['id']}"):
                    st.session_state[f"show_versions_{a['id']}"] = not st.session_state.get(f"show_versions_{a['id']}", False)

                if st.session_state.get(f"show_versions_{a['id']}"):
                    versions_panel(a["id"])

def versions_panel(assumption_id):
    st.markdown("**Version History**")
    with get_conn() as conn:
        versions = conn.execute(
            """SELECT av.*, u.username as modified_by_name
               FROM assumption_versions av LEFT JOIN users u ON av.modified_by=u.id
               WHERE av.assumption_id=? ORDER BY av.version_number DESC""",
            (assumption_id,)
        ).fetchall()
    if not versions:
        st.info("No version history.")
        return
    for v in versions:
        with st.expander(f"Version {v['version_number']} - {v['modified_at'][:16]}"):
            col1, col2 = st.columns(2)
            col1.write(f"Status: {v['status']}")
            col1.write(f"Confidence: {v['confidence_level']}%")
            col2.write(f"Impact: {v['impact_weight']}")
            col2.write(f"Modified by: {v['modified_by_name'] or 'System'}")
            if v["comment"]:
                st.write(f"Comment: {v['comment']}")
            if v["justification"]:
                st.write(f"Justification: {v['justification']}")

    if len(versions) >= 2:
        st.markdown("**Compare Two Versions**")
        v_nums = [str(v["version_number"]) for v in versions]
        col1, col2 = st.columns(2)
        v1_num = col1.selectbox("Version A", v_nums, key=f"va_{assumption_id}")
        v2_num = col2.selectbox("Version B", v_nums, index=min(1, len(v_nums) - 1), key=f"vb_{assumption_id}")
        if st.button("Compare Versions", key=f"cmp_{assumption_id}"):
            v1 = next((v for v in versions if str(v["version_number"]) == v1_num), None)
            v2 = next((v for v in versions if str(v["version_number"]) == v2_num), None)
            if v1 and v2:
                fields = ["status", "confidence_level", "impact_weight", "description", "category"]
                for f in fields:
                    val1 = v1[f]
                    val2 = v2[f]
                    if val1 != val2:
                        st.warning(f"{f.upper()}: V{v1_num}=`{val1}` vs V{v2_num}=`{val2}`")
                    else:
                        st.success(f"{f.upper()}: unchanged (`{val1}`)")

def dependencies_tab(project_id, proj_role):
    user = st.session_state["user"]
    st.subheader("Dependency Management")
    with get_conn() as conn:
        assumptions = conn.execute(
            "SELECT id, description, status FROM assumptions WHERE project_id=? ORDER BY description",
            (project_id,)
        ).fetchall()
        deps = conn.execute(
            """SELECT d.id, d.parent_id, d.child_id,
                      ap.description as parent_desc, ac.description as child_desc,
                      ap.status as parent_status, ac.status as child_status
               FROM dependencies d
               JOIN assumptions ap ON d.parent_id=ap.id
               JOIN assumptions ac ON d.child_id=ac.id
               WHERE ap.project_id=?""",
            (project_id,)
        ).fetchall()

    a_map = {a["description"][:70]: a["id"] for a in assumptions}

    st.markdown("**Existing Dependencies**")
    if not deps:
        st.info("No dependencies defined.")
    else:
        for d in deps:
            col1, col2 = st.columns([4, 1])
            col1.write(f"[{d['parent_status']}] {d['parent_desc'][:50]}  depends on  [{d['child_status']}] {d['child_desc'][:50]}")
            if proj_role in ("Project Owner", "Analyst", "Administrator"):
                with col2:
                    if st.button("Remove", key=f"remdep_{d['id']}"):
                        with get_conn() as conn:
                            conn.execute("DELETE FROM dependencies WHERE id=?", (d["id"],))
                            log_audit(conn, user["id"], "REMOVE_DEPENDENCY", "Dependency", d["id"])
                        st.success("Dependency removed.")
                        st.rerun()

    st.divider()
    if proj_role in ("Project Owner", "Analyst", "Administrator") and len(assumptions) >= 2:
        st.markdown("**Add New Dependency**")
        all_descs = list(a_map.keys())
        with st.form("add_dep_form"):
            parent_desc = st.selectbox("Parent Assumption", all_descs, key="dep_parent")
            child_desc = st.selectbox("Child Assumption (depended upon)", all_descs, key="dep_child")
            submit_dep = st.form_submit_button("Add Dependency")
        if submit_dep:
            parent_id = a_map.get(parent_desc)
            child_id = a_map.get(child_desc)
            if parent_id == child_id:
                st.error("Cannot create self-dependency.")
            else:
                with get_conn() as conn:
                    if has_circular_dependency(conn, parent_id, child_id):
                        st.error("This would create a circular dependency. Action blocked.")
                    else:
                        try:
                            conn.execute(
                                "INSERT INTO dependencies(parent_id,child_id,created_at) VALUES(?,?,?)",
                                (parent_id, child_id, datetime.now().isoformat())
                            )
                            log_audit(conn, user["id"], "ADD_DEPENDENCY", "Dependency", None, f"{parent_id}->{child_id}")
                            st.success("Dependency added.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("This dependency already exists.")

    st.divider()
    st.markdown("**View Dependency Chain**")
    if assumptions:
        all_descs_list = [a["description"][:70] for a in assumptions]
        selected_desc = st.selectbox("Select Assumption to trace", all_descs_list, key="depchain_sel")
        selected_id = next((a["id"] for a in assumptions if a["description"][:70] == selected_desc), None)
        if selected_id:
            if st.button("Show Dependency Chain"):
                chain = build_dependency_chain(selected_id)
                st.json(chain)

def build_dependency_chain(assumption_id):
    with get_conn() as conn:
        assumption = conn.execute("SELECT * FROM assumptions WHERE id=?", (assumption_id,)).fetchone()
        if not assumption:
            return {}
        children = conn.execute(
            "SELECT child_id FROM dependencies WHERE parent_id=?", (assumption_id,)
        ).fetchall()
        result = {
            "id": assumption["id"],
            "description": assumption["description"][:60],
            "status": assumption["status"],
            "confidence": assumption["confidence_level"],
            "impact": assumption["impact_weight"],
            "children": [build_dependency_chain(c["child_id"]) for c in children]
        }
    return result

def risk_reports_tab(project_id, proj_role):
    user = st.session_state["user"]
    st.subheader("Risk Index and Reports")

    with get_conn() as conn:
        current_risk = calculate_risk_index(conn, project_id)
        history = conn.execute(
            "SELECT * FROM risk_history WHERE project_id=? ORDER BY calculated_at DESC LIMIT 10",
            (project_id,)
        ).fetchall()
        assumptions = conn.execute(
            "SELECT * FROM assumptions WHERE project_id=?", (project_id,)
        ).fetchall()

    st.metric("Current Risk Index", f"{current_risk}%")
    status_summary = {"Valid": 0, "At Risk": 0, "Invalid": 0}
    for a in assumptions:
        status_summary[a["status"]] = status_summary.get(a["status"], 0) + 1

    col1, col2, col3 = st.columns(3)
    col1.metric("Valid", status_summary["Valid"])
    col2.metric("At Risk", status_summary["At Risk"])
    col3.metric("Invalid", status_summary["Invalid"])

    st.divider()
    if proj_role in ("Project Owner", "Analyst", "Administrator"):
        action_cols = st.columns(3)

        if action_cols[0].button("Recalculate and Save Risk Index"):
            with get_conn() as conn:
                risk = calculate_risk_index(conn, project_id)
                conn.execute(
                    "INSERT INTO risk_history(project_id,risk_index,calculated_at) VALUES(?,?,?)",
                    (project_id, risk, datetime.now().isoformat())
                )
                log_audit(conn, user["id"], "CALCULATE_RISK", "Project", project_id, str(risk))
            st.success(f"Risk Index saved: {risk}%")
            st.rerun()

        if action_cols[1].button("Run Cascade Evaluation"):
            with get_conn() as conn:
                invalid_set = conn.execute(
                    "SELECT id FROM assumptions WHERE project_id=? AND status='Invalid'",
                    (project_id,)
                ).fetchall()
                total_changed = 0
                for a in invalid_set:
                    changed = cascade_evaluate(conn, a["id"], user["id"])
                    total_changed += len(changed)
                log_audit(conn, user["id"], "CASCADE_EVALUATION", "Project", project_id)
            st.success(f"Cascade complete. {total_changed} assumptions updated.")
            st.rerun()

        if action_cols[2].button("Flag At Risk by Depth"):
            with get_conn() as conn:
                all_assum = conn.execute(
                    "SELECT id FROM assumptions WHERE project_id=?", (project_id,)
                ).fetchall()
                flagged = 0
                for a in all_assum:
                    depth = get_depth_from_root(conn, a["id"])
                    row = conn.execute("SELECT status FROM assumptions WHERE id=?", (a["id"],)).fetchone()
                    if depth >= 3 and row and row["status"] == "Valid":
                        save_version(conn, a["id"], user["id"], "Flagged at risk by depth rule")
                        conn.execute(
                            "UPDATE assumptions SET status='At Risk', updated_at=? WHERE id=?",
                            (datetime.now().isoformat(), a["id"])
                        )
                        flagged += 1
                log_audit(conn, user["id"], "FLAG_AT_RISK_DEPTH", "Project", project_id)
            st.success(f"{flagged} assumptions flagged as At Risk by dependency depth.")
            st.rerun()

    st.divider()
    st.markdown("**Risk History**")
    if history:
        for h in history:
            st.write(f"{h['calculated_at'][:16]}  -  Risk Index: {h['risk_index']}%")
        if len(history) >= 2:
            before = history[-1]["risk_index"]
            after = history[0]["risk_index"]
            delta = round(after - before, 2)
            st.info(f"Change from oldest to latest saved: {delta:+.2f}%")
    else:
        st.info("No risk history saved yet.")

    st.divider()
    st.markdown("**Impact Analysis Report**")
    if proj_role in ("Project Owner", "Analyst", "Administrator"):
        if st.button("Generate Impact Report"):
            with get_conn() as conn:
                report_lines = generate_impact_report(conn, project_id)
            for line in report_lines:
                st.write(line)

        if st.button("Export Risk Summary as CSV"):
            with get_conn() as conn:
                csv_data = export_risk_summary(conn, project_id, current_risk, status_summary)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"risk_summary_project_{project_id}.csv",
                mime="text/csv"
            )
    else:
        with get_conn() as conn:
            report_lines = generate_impact_report(conn, project_id)
        for line in report_lines:
            st.write(line)

def generate_impact_report(conn, project_id):
    project = conn.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
    assumptions = conn.execute(
        "SELECT a.*, u.username as owner_name FROM assumptions a LEFT JOIN users u ON a.owner_id=u.id WHERE a.project_id=?",
        (project_id,)
    ).fetchall()
    lines = []
    lines.append(f"Impact Analysis Report")
    lines.append(f"Project: {project['name'] if project else project_id}")
    lines.append(f"Generated: {datetime.now().isoformat()[:16]}")
    lines.append("---")
    affected = [a for a in assumptions if a["status"] in ("At Risk", "Invalid")]
    if not affected:
        lines.append("No At Risk or Invalid assumptions found.")
    else:
        lines.append(f"Affected Assumptions: {len(affected)}")
        lines.append("")
        for a in affected:
            lines.append(f"[{a['status']}] {a['description'][:80]}")
            lines.append(f"  Owner: {a['owner_name'] or 'Unassigned'}  |  Confidence: {a['confidence_level']}%  |  Impact Weight: {a['impact_weight']}")
            if a["justification"]:
                lines.append(f"  Justification: {a['justification']}")
            lines.append("")
    return lines

def export_risk_summary(conn, project_id, risk_index, status_summary):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Project ID", "Risk Index (%)", "Valid", "At Risk", "Invalid", "Generated At"])
    writer.writerow([project_id, risk_index, status_summary["Valid"], status_summary["At Risk"], status_summary["Invalid"], datetime.now().isoformat()])
    writer.writerow([])
    writer.writerow(["Assumption ID", "Description", "Status", "Confidence", "Impact", "Owner", "Category", "Expiration"])
    assumptions = conn.execute(
        "SELECT a.*, u.username as owner_name FROM assumptions a LEFT JOIN users u ON a.owner_id=u.id WHERE a.project_id=?",
        (project_id,)
    ).fetchall()
    for a in assumptions:
        writer.writerow([
            a["id"], a["description"][:80], a["status"],
            a["confidence_level"], a["impact_weight"],
            a["owner_name"] or "Unassigned", a["category"],
            a["expiration_date"] or "None"
        ])
    return output.getvalue()

def search_filter_tab(project_id):
    st.subheader("Search and Filter Assumptions")
    col1, col2, col3, col4 = st.columns(4)
    keyword = col1.text_input("Keyword Search", key=f"kw_{project_id}")
    category_filter = col2.selectbox("Category", ["All", "Financial", "Market", "Technical", "Regulatory", "Resource", "Stakeholder", "Other"], key=f"cf_{project_id}")
    status_filter = col3.selectbox("Status", ["All", "Valid", "At Risk", "Invalid"], key=f"sf_{project_id}")

    with get_conn() as conn:
        users = conn.execute("SELECT id, username FROM users").fetchall()
    user_names = ["All"] + [u["username"] for u in users]
    user_id_map = {u["username"]: u["id"] for u in users}
    owner_filter = col4.selectbox("Owner", user_names, key=f"of_{project_id}")

    query = """SELECT a.*, u.username as owner_name
               FROM assumptions a LEFT JOIN users u ON a.owner_id=u.id
               WHERE a.project_id=?"""
    params = [project_id]
    if keyword:
        query += " AND a.description LIKE ?"
        params.append(f"%{keyword}%")
    if category_filter != "All":
        query += " AND a.category=?"
        params.append(category_filter)
    if status_filter != "All":
        query += " AND a.status=?"
        params.append(status_filter)
    if owner_filter != "All":
        owner_id_val = user_id_map.get(owner_filter)
        query += " AND a.owner_id=?"
        params.append(owner_id_val)

    with get_conn() as conn:
        results = conn.execute(query, params).fetchall()

    st.write(f"Found {len(results)} assumption(s).")
    for a in results:
        with st.expander(f"[{a['status']}] {a['description'][:80]}"):
            st.write(f"Category: {a['category']}  |  Confidence: {a['confidence_level']}%  |  Impact: {a['impact_weight']}")
            st.write(f"Owner: {a['owner_name'] or 'Unassigned'}  |  Expiration: {a['expiration_date'] or 'None'}")
            st.write(f"Created: {a['created_at'][:10]}  |  Updated: {a['updated_at'][:10]}")
            if a["justification"]:
                st.write(f"Justification: {a['justification']}")

def expired_assumptions_tab(project_id, proj_role):
    user = st.session_state["user"]
    st.subheader("Expired Assumptions")
    today = str(date.today())
    with get_conn() as conn:
        expired = conn.execute(
            """SELECT a.*, u.username as owner_name
               FROM assumptions a LEFT JOIN users u ON a.owner_id=u.id
               WHERE a.project_id=? AND a.expiration_date IS NOT NULL AND a.expiration_date < ?""",
            (project_id, today)
        ).fetchall()

    if not expired:
        st.info("No expired assumptions found.")
        return

    st.write(f"{len(expired)} expired assumption(s) found.")
    for a in expired:
        with st.expander(f"[{a['status']}] {a['description'][:80]} (Expired: {a['expiration_date']})"):
            st.write(f"Category: {a['category']}  |  Confidence: {a['confidence_level']}%  |  Impact: {a['impact_weight']}")
            st.write(f"Owner: {a['owner_name'] or 'Unassigned'}")
            if proj_role in ("Project Owner", "Analyst", "Administrator"):
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Revalidate", key=f"reval_{a['id']}"):
                        with get_conn() as conn:
                            save_version(conn, a["id"], user["id"], "Revalidated after expiry review")
                            conn.execute(
                                "UPDATE assumptions SET status='Valid', updated_at=? WHERE id=?",
                                (datetime.now().isoformat(), a["id"])
                            )
                            changed = cascade_evaluate(conn, a["id"], user["id"])
                            log_audit(conn, user["id"], "REVALIDATE_EXPIRED", "Assumption", a["id"])
                        st.success(f"Revalidated. {len(changed)} dependent(s) updated.")
                        st.rerun()
                with col2:
                    if st.button("Initiate Re-evaluation", key=f"reeval_{a['id']}"):
                        with get_conn() as conn:
                            changed = cascade_evaluate(conn, a["id"], user["id"])
                            log_audit(conn, user["id"], "REEVALUATE_EXPIRED", "Assumption", a["id"])
                        st.success(f"Re-evaluation complete. {len(changed)} dependent(s) updated.")
                        st.rerun()

def project_settings_tab(project_id, proj_role, project):
    user = st.session_state["user"]
    st.subheader("Project Settings")

    with st.form("update_project_form"):
        new_name = st.text_input("Project Name", value=project["name"])
        new_desc = st.text_area("Description", value=project["description"] or "")
        new_start = st.date_input("Start Date", value=date.fromisoformat(project["start_date"]) if project["start_date"] else date.today())
        submit_proj = st.form_submit_button("Update Project")
    if submit_proj:
        if not new_name:
            st.error("Name required.")
        else:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE projects SET name=?, description=?, start_date=? WHERE id=?",
                    (new_name, new_desc, str(new_start), project_id)
                )
                log_audit(conn, user["id"], "UPDATE_PROJECT", "Project", project_id)
            st.success("Project updated.")
            st.rerun()

    st.divider()
    if proj_role == "Administrator":
        if project["is_active"]:
            if st.button("Deactivate Project"):
                with get_conn() as conn:
                    conn.execute("UPDATE projects SET is_active=0 WHERE id=?", (project_id,))
                    log_audit(conn, user["id"], "DEACTIVATE_PROJECT", "Project", project_id)
                st.success("Project deactivated.")
                st.rerun()
        else:
            if st.button("Activate Project"):
                with get_conn() as conn:
                    conn.execute("UPDATE projects SET is_active=1 WHERE id=?", (project_id,))
                    log_audit(conn, user["id"], "ACTIVATE_PROJECT", "Project", project_id)
                st.success("Project activated.")
                st.rerun()

    st.divider()
    if proj_role in ("Administrator", "Project Owner"):
        st.markdown("**Assign New Project Owner**")
        with get_conn() as conn:
            po_users = conn.execute(
                "SELECT id, username FROM users WHERE role='Project Owner' AND is_active=1"
            ).fetchall()
        po_map = {u["username"]: u["id"] for u in po_users}
        if po_map:
            with st.form("assign_owner_form"):
                new_owner_name = st.selectbox("New Project Owner", list(po_map.keys()))
                assign_submit = st.form_submit_button("Assign Owner")
            if assign_submit:
                new_owner_id = po_map[new_owner_name]
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE projects SET owner_id=? WHERE id=?",
                        (new_owner_id, project_id)
                    )
                    log_audit(conn, user["id"], "ASSIGN_OWNER", "Project", project_id, new_owner_name)
                st.success(f"Owner assigned to {new_owner_name}.")
                st.rerun()
        else:
            st.info("No Project Owner accounts available.")

def membership_tab(project_id, proj_role):
    user = st.session_state["user"]
    st.subheader("Project Membership")

    with get_conn() as conn:
        members = conn.execute(
            """SELECT pm.id, pm.role, u.username, u.id as user_id
               FROM project_members pm JOIN users u ON pm.user_id=u.id
               WHERE pm.project_id=?""",
            (project_id,)
        ).fetchall()
        project = conn.execute("SELECT owner_id FROM projects WHERE id=?", (project_id,)).fetchone()
        all_users = conn.execute(
            "SELECT id, username, role FROM users WHERE is_active=1 AND role IN ('Analyst','Viewer')"
        ).fetchall()

    member_ids = {m["user_id"] for m in members}
    if project:
        member_ids.add(project["owner_id"])

    st.markdown("**Current Members**")
    if not members:
        st.info("No additional members assigned.")
    for m in members:
        col1, col2 = st.columns([3, 1])
        col1.write(f"{m['username']} ({m['role']})")
        if proj_role in ("Project Owner", "Administrator"):
            with col2:
                if st.button("Remove", key=f"remmem_{m['id']}"):
                    with get_conn() as conn:
                        conn.execute("DELETE FROM project_members WHERE id=?", (m["id"],))
                        log_audit(conn, user["id"], "REMOVE_MEMBER", "ProjectMember", m["id"], m["username"])
                    st.success(f"Removed {m['username']}.")
                    st.rerun()

    st.divider()
    st.markdown("**Add New Member**")
    eligible = [u for u in all_users if u["id"] not in member_ids]
    if not eligible:
        st.info("No eligible users to add.")
        return
    eligible_map = {u["username"]: u["id"] for u in eligible}
    with st.form("add_member_form"):
        selected_user = st.selectbox("User", list(eligible_map.keys()))
        selected_role = st.selectbox("Role", ["Analyst", "Viewer"])
        add_submit = st.form_submit_button("Add Member")
    if add_submit:
        uid = eligible_map[selected_user]
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?)",
                    (project_id, uid, selected_role)
                )
                log_audit(conn, user["id"], "ADD_MEMBER", "ProjectMember", None, f"{selected_user} as {selected_role}")
            st.success(f"Added {selected_user} as {selected_role}.")
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("User is already a member.")

def main():
    load_css()
    st.set_page_config(page_title="ADITS", page_icon=None, layout="wide")
    init_db()
    if "user" not in st.session_state:
        login_page()
        return
    page = st.session_state.get("force_page", None)


    if not page:
        page = sidebar_nav()
    else:
        st.session_state.pop("force_page")

    if page == "Dashboard":
        dashboard_page()
    elif page == "Projects":
        projects_page()
    elif page == "Users":
        users_page()
    elif page == "Profile":
        profile_page()

if __name__ == "__main__":
    main()