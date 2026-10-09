import os
import re
import random
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, session
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from database import init_db, get_db, auto_detect_and_save_memory
from pdf_handler import index_campus_file, retrieve_best_chunks, allowed_file
from ai_service import generate_ai_response

app = Flask(__name__)
app.config.from_object(Config)

mail = Mail(app)

# Cache for registration OTPs: { "user_email": { "otp": "123456", "expires": timestamp } }
REGISTRATION_OTP_CACHE = {}

GREETING_PATTERNS = [
    r"^(hi|hello|hey|hola|greetings|namaste)\b",
    r"^(good\s+(morning|afternoon|evening|night))\b"
]

IDENTITY_PATTERNS = [
    r"^(who\s+am\s+i|what\s+is\s+my\s+name|my\s+name|my\s+username|mera\s+naam)\b"
]

CREATOR_PATTERNS = [
    r"^(who\s+are\s+you|what\s+is\s+your\s+name|who\s+made\s+you|who\s+is\s+the\s+founder)\b"
]

def matches_any(patterns, text):
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', text.strip().lower())
    for p in patterns:
        if re.search(p, clean):
            return True
    return False

@app.route("/")
def home():
    return redirect("/chat" if "username" in session else "/login")

@app.route("/login")
def login_page():
    return redirect("/chat") if "username" in session else render_template("login.html")

@app.route("/chat")
def chat_page():
    if "username" not in session:
        return redirect("/login")
    return render_template("chat.html", username=session["username"], role=session["role"])

# --- SIMPLE USERNAME & PASSWORD LOGIN (NO OTP REQUIRED HERE) ---
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "student")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password cannot be empty."}), 400

    conn = get_db()
    row = conn.cursor().execute("SELECT * FROM users WHERE LOWER(username) = ?", (username.lower(),)).fetchone()
    conn.close()

    if not row or not check_password_hash(row["password"], password):
        return jsonify({"success": False, "error": "Invalid Username or Password! Please re-check."}), 401

    if row["role"] != role:
        return jsonify({"success": False, "error": f"Role mismatch. Account is registered as '{row['role']}'."}), 403

    # Sign in directly
    session["username"] = row["username"]
    session["role"] = row["role"]
    return jsonify({"success": True, "redirect": "/chat"})

# --- STEP 1 OF REGISTRATION: DISPATCH OTP TO GMAIL ---
@app.route("/api/register/send_otp", methods=["POST"])
def register_send_otp():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Please enter a valid Gmail / Email address."}), 400

    conn = get_db()
    existing_user = conn.cursor().execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,)).fetchone()
    conn.close()

    if existing_user:
        return jsonify({"success": False, "error": "This email is already registered. Please sign in directly."}), 409

    # Generate 6-digit OTP code
    otp_code = f"{random.randint(100000, 999999)}"
    REGISTRATION_OTP_CACHE[email] = {
        "otp": otp_code,
        "expires": time.time() + 300  # Valid for 5 minutes
    }

    # Dispatch to Gmail inbox
    try:
        msg = Message(
            subject=f"SmartCampus AI — Student Registration Code: {otp_code}",
            recipients=[email]
        )
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; background:#0f172a; color:#f8fafc; padding:24px; border-radius:12px; max-width:480px; margin:auto;">
            <h2 style="color:#818cf8; margin-bottom:6px;">SmartCampus AI</h2>
            <p style="color:#94a3b8; font-size:14px;">Team FutureMind — Student Account Verification</p>
            <hr style="border:0; border-top:1px solid #1e293b; margin:16px 0;">
            <p style="font-size:15px;">Your verification code to complete student registration is:</p>
            <div style="background:#1e293b; color:#ffffff; font-size:32px; font-weight:bold; letter-spacing:8px; text-align:center; padding:16px; border-radius:8px; margin:20px 0;">
                {otp_code}
            </div>
            <p style="font-size:13px; color:#94a3b8;">This code is valid for 5 minutes. Enter this code to verify your email and activate your account.</p>
        </div>
        """
        mail.send(msg)
        print(f"\n[LIVE GMAIL SENT] Registration OTP {otp_code} sent to {email}\n")
    except Exception as e:
        print(f"\n[SMTP WARNING]: Could not dispatch email ({e}).")

    # Local terminal printout
    print(f"\n==========================================")
    print(f" [REGISTRATION OTP] Email: {email} | Code: {otp_code}")
    print(f"==========================================\n")

    return jsonify({"success": True, "message": f"Verification code sent to {email}"})

# --- STEP 2 OF REGISTRATION: VERIFY OTP AND SAVE STUDENT IN DATABASE ---
@app.route("/api/register/verify_and_create", methods=["POST"])
def register_verify_and_create():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    otp_code = data.get("otp", "").strip()

    if not username or not email or not password or not otp_code:
        return jsonify({"success": False, "error": "All fields (Username, Email, Password, OTP) are required."}), 400

    cached_record = REGISTRATION_OTP_CACHE.get(email)
    if not cached_record:
        return jsonify({"success": False, "error": "No OTP was requested for this email, or it has expired."}), 400

    if time.time() > cached_record["expires"]:
        REGISTRATION_OTP_CACHE.pop(email, None)
        return jsonify({"success": False, "error": "Verification code expired. Please request a new one."}), 400

    if cached_record["otp"] != otp_code:
        return jsonify({"success": False, "error": "Invalid verification code! Please check your Gmail."}), 401

    conn = get_db()
    c = conn.cursor()
    # Check if username is already taken
    if c.execute("SELECT id FROM users WHERE LOWER(username) = ?", (username.lower(),)).fetchone():
        conn.close()
        return jsonify({"success": False, "error": "Username is already taken. Please choose another."}), 409

    try:
        c.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, 'student')",
            (username, email, generate_password_hash(password))
        )
        conn.commit()
        REGISTRATION_OTP_CACHE.pop(email, None)
        return jsonify({"success": True, "message": "Email verified! Student account created. You can now log in with your Username and Password."})
    except Exception as err:
        return jsonify({"success": False, "error": "Could not create user account."}), 500
    finally:
        conn.close()

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "redirect": "/login"})

@app.route("/api/admin/create_faculty", methods=["POST"])
def create_faculty():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin credentials required."}), 403

    data = request.get_json() or {}
    u = data.get("username", "").strip()
    e = data.get("email", "").strip().lower()
    p = data.get("password", "").strip()

    if not u or not p or not e:
        return jsonify({"success": False, "error": "All fields are required."}), 400

    conn = get_db()
    try:
        conn.cursor().execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, 'faculty')",
            (u, e, generate_password_hash(p))
        )
        conn.commit()
        return jsonify({"success": True, "message": f"Faculty '{u}' registered successfully!"})
    except Exception:
        return jsonify({"success": False, "error": "Username or email already exists."}), 409
    finally:
        conn.close()

@app.route("/api/documents", methods=["GET"])
def list_documents():
    role = session.get("role")
    if role not in ["admin", "faculty"]:
        return jsonify({"success": False, "error": "Unauthorized."}), 403

    conn = get_db()
    c = conn.cursor()
    rows = c.execute("SELECT filename, total_chunks, access_level, uploaded_at FROM campus_documents ORDER BY uploaded_at DESC").fetchall()
    conn.close()
    return jsonify({"success": True, "documents": [dict(r) for r in rows]})

@app.route("/api/delete_document", methods=["POST"])
def delete_document():
    role = session.get("role")
    if role not in ["admin", "faculty"]:
        return jsonify({"success": False, "error": "Unauthorized."}), 403

    data = request.get_json() or {}
    filename = data.get("filename", "").strip()
    if not filename:
        return jsonify({"success": False, "error": "Filename required."}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM document_vectors WHERE filename = ?", (filename,))
    c.execute("DELETE FROM campus_documents WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()

    file_path = os.path.join(Config.UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    return jsonify({"success": True, "message": f"'{filename}' deleted successfully."})

@app.route("/api/upload_document", methods=["POST"])
def upload_document():
    role = session.get("role")
    if role not in ["admin", "faculty"]:
        return jsonify({"success": False, "error": "Unauthorized."}), 403

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    file = request.files["file"]
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Supported formats: PDF, DOCX, CSV, PNG, JPG"}), 400

    filepath = os.path.join(Config.UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    ok, msg = index_campus_file(file.filename, role)
    return jsonify({"success": ok, "message": msg})

@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = conn.cursor().execute(
        "SELECT session_id, title FROM chat_sessions WHERE username = ? ORDER BY created_at DESC", 
        (session["username"],)
    ).fetchall()
    conn.close()
    return jsonify({"sessions": [{"session_id": r["session_id"], "title": r["title"]} for r in rows]})

@app.route("/api/delete_session", methods=["POST"])
def delete_session():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    session_id = data.get("session_id", "").strip()
    if not session_id:
        return jsonify({"success": False, "error": "Session ID required"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM chat_messages WHERE session_id = ? AND username = ?", (session_id, session["username"]))
    c.execute("DELETE FROM chat_sessions WHERE session_id = ? AND username = ?", (session_id, session["username"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Thread deleted."})

@app.route("/api/history/<sid>", methods=["GET"])
def get_history(sid):
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = conn.cursor().execute(
        "SELECT sender, content FROM chat_messages WHERE session_id = ? AND username = ? ORDER BY id ASC", 
        (sid, session["username"])
    ).fetchall()
    conn.close()
    return jsonify({"history": [dict(r) for r in rows]})

@app.route("/api/chat", methods=["POST"])
def chat():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user = session["username"]
    role = session["role"]
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    session_id = data.get("session_id", "").strip()

    if not query:
        return jsonify({"error": "Query cannot be blank."}), 400

    auto_detect_and_save_memory(user, query)

    conn = get_db()
    c = conn.cursor()

    if not session_id:
        session_id = "session_" + str(int(datetime.now().timestamp()))
        title = query[:30] + ("..." if len(query) > 30 else "")
        c.execute("INSERT INTO chat_sessions (session_id, username, title) VALUES (?, ?, ?)",
                  (session_id, user, title))
        conn.commit()

    answer = None

    if matches_any(IDENTITY_PATTERNS, query):
        if role == "admin":
            answer = "You are logged in as the Administrator (Admin)."
        elif role == "faculty":
            answer = f"You are logged in as Faculty member '{user}'."
        else:
            answer = f"You are logged in as {user}."

    elif matches_any(CREATOR_PATTERNS, query):
        answer = "I was founded and built by Nikhil Kumar Singh and Team FutureMind in October 2026."

    elif matches_any(GREETING_PATTERNS, query):
        if role == "admin":
            answer = "Hello Admin! Welcome back."
        elif role == "faculty":
            answer = f"Hello Faculty {user}!"
        else:
            answer = f"Hello {user}! How can I help you today?"

    if answer:
        c.execute("INSERT INTO chat_messages (session_id, username, sender, content) VALUES (?, ?, 'user', ?)", (session_id, user, query))
        c.execute("INSERT INTO chat_messages (session_id, username, sender, content) VALUES (?, ?, 'bot', ?)", (session_id, user, answer))
        conn.commit()
        conn.close()
        return jsonify({"answer": answer, "session_id": session_id})

    doc_context = retrieve_best_chunks(query=query, user_role=role, top_k=4)

    c.execute(
        "SELECT sender, content FROM chat_messages WHERE session_id = ? AND username = ? ORDER BY id DESC LIMIT 2", 
        (session_id, user)
    )
    recent_turns = list(reversed(c.fetchall()))

    system_instruction = f"""You are SmartCampus AI, built by Nikhil Kumar Singh & Team FutureMind (October 2026).

CURRENT USER:
- Username: {user}
- Role: {role.upper()}

CAMPUS DATABASE EXCERPTS:
{doc_context}

RULES:
1. Speak helpfully, candidly, and clearly.
2. Read the CAMPUS DATABASE EXCERPTS carefully. Quote exact figures, rosters, schedules, and details.
3. Conclude verified answers derived from documents with: "(Official Campus Record)".
4. Only if the excerpts truly have NO relevance, reply: "There is no official information about this in my database."
"""

    answer = generate_ai_response(system_instruction, recent_turns, query)
    if not answer:
        answer = "There is no official information about this in my database."

    c.execute("INSERT INTO chat_messages (session_id, username, sender, content) VALUES (?, ?, 'user', ?)",
              (session_id, user, query))
    c.execute("INSERT INTO chat_messages (session_id, username, sender, content) VALUES (?, ?, 'bot', ?)",
              (session_id, user, answer))
    conn.commit()
    conn.close()

    return jsonify({"answer": answer, "session_id": session_id})

if __name__ == "__main__":
    init_db()
    app.run(debug=Config.DEBUG, port=Config.PORT)