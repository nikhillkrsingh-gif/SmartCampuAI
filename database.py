import sqlite3
from werkzeug.security import generate_password_hash
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS campus_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        total_chunks INTEGER NOT NULL,
        uploader_role TEXT NOT NULL,
        access_level TEXT NOT NULL DEFAULT 'public_student',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS document_vectors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        section_label TEXT NOT NULL,
        chunk_text TEXT NOT NULL,
        uploader_role TEXT NOT NULL,
        access_level TEXT NOT NULL DEFAULT 'public_student'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        username TEXT NOT NULL,
        sender TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    def seed_user(uname, email, pwd, role):
        if not c.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone():
            c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                      (uname, email, generate_password_hash(pwd), role))

    seed_user("admin", "admin@smartcampus.edu", "admin123", "admin")
    seed_user("faculty1", "faculty@smartcampus.edu", "faculty123", "faculty")
    seed_user("student1", "student@smartcampus.edu", "student123", "student")

    conn.commit()
    conn.close()

def auto_detect_and_save_memory(user, query):
    pass