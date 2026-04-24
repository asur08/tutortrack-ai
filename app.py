import os
import datetime
import matplotlib
matplotlib.use('Agg')  # Headless mode for matplolib
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_local_secret_key_change_in_production")

# Setup Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Configuration
DB_URL = os.environ.get('DATABASE_URL')
if DB_URL and DB_URL.startswith('postgres'):
    USE_POSTGRES = True
    if DB_URL.startswith('postgres://'):
        DB_URL = DB_URL.replace('postgres://', 'postgresql://', 1)
else:
    USE_POSTGRES = False

def get_db_connection():
    if USE_POSTGRES:
        import psycopg2
        from psycopg2.extras import DictCursor
        conn = psycopg2.connect(DB_URL, cursor_factory=DictCursor)
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect('tutortrack.db')
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(conn, query, params=(), commit=False, fetchone=False, fetchall=False):
    if USE_POSTGRES:
        query = query.replace('?', '%s')
    cur = conn.cursor()
    cur.execute(query, params)
    if commit:
        conn.commit()
    result = None
    if fetchone:
        result = cur.fetchone()
    elif fetchall:
        result = cur.fetchall()
    cur.close()
    return result

# User Model for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, password_hash, role):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_data = execute_query(conn, 'SELECT * FROM users WHERE id = ?', (user_id,), fetchone=True)
    conn.close()
    if user_data:
        return User(id=str(user_data['id']), username=user_data['username'], password_hash=user_data['password_hash'], role=user_data['role'])
    return None

def init_db():
    conn = get_db_connection()
    if USE_POSTGRES:
        pk_type = "SERIAL PRIMARY KEY"
        bool_default = "DEFAULT FALSE"
    else:
        pk_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
        bool_default = "DEFAULT 0"

    execute_query(conn, f'''
        CREATE TABLE IF NOT EXISTS users (
            id {pk_type},
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'tutor'
        )
    ''', commit=True)

    execute_query(conn, f'''
        CREATE TABLE IF NOT EXISTS students (
            id {pk_type},
            student_name TEXT NOT NULL,
            subject_topic TEXT NOT NULL,
            marks_obtained INTEGER NOT NULL,
            total_marks INTEGER DEFAULT 100,
            test_date DATE NOT NULL
        )
    ''', commit=True)
    
    execute_query(conn, f'''
        CREATE TABLE IF NOT EXISTS syllabus (
            id {pk_type},
            topic_name TEXT NOT NULL,
            status BOOLEAN {bool_default}
        )
    ''', commit=True)
    
    conn.close()

init_db()

# --- Auth Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        existing_user = execute_query(conn, 'SELECT id FROM users WHERE username = ?', (username,), fetchone=True)
        
        if existing_user:
            conn.close()
            flash('Username already exists.', 'error')
            return redirect(url_for('signup'))
            
        hashed_password = generate_password_hash(password)
        execute_query(conn, 'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', 
                      (username, hashed_password, 'tutor'), commit=True)
        conn.close()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user_data = execute_query(conn, 'SELECT * FROM users WHERE username = ?', (username,), fetchone=True)
        conn.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(id=str(user_data['id']), username=user_data['username'], password_hash=user_data['password_hash'], role=user_data['role'])
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Main App Routes ---
@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    records = execute_query(conn, 'SELECT * FROM students ORDER BY test_date DESC', fetchall=True)
    syllabus_items = execute_query(conn, 'SELECT * FROM syllabus ORDER BY id DESC', fetchall=True)
    conn.close()
    
    pending_topics = [item for item in syllabus_items if not item['status']]
    covered_topics = [item for item in syllabus_items if item['status']]
    
    # Format date for dashboard
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    return render_template('index.html', records=records, pending_topics=pending_topics, covered_topics=covered_topics, current_date=current_date)

@app.route('/add_marks', methods=['POST'])
@login_required
def add_marks():
    student_name = request.form['student_name']
    subject_topic = request.form['subject_topic']
    marks_obtained = int(request.form['marks_obtained'])
    total_marks = int(request.form.get('total_marks', 100))
    test_date = request.form['test_date']

    conn = get_db_connection()
    execute_query(conn, 
        'INSERT INTO students (student_name, subject_topic, marks_obtained, total_marks, test_date) VALUES (?, ?, ?, ?, ?)',
        (student_name, subject_topic, marks_obtained, total_marks, test_date),
        commit=True
    )
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/generate_report/<student_name>')
@login_required
def generate_report(student_name):
    conn = get_db_connection()
    records = execute_query(conn, '''
        SELECT test_date, marks_obtained, total_marks
        FROM students 
        WHERE student_name = ?
        ORDER BY test_date ASC
    ''', (student_name,), fetchall=True)
    conn.close()

    if not records:
        return "No records found", 404

    dates = []
    percentages = []
    for r in records:
        dates.append(r['test_date'])
        perc = (r['marks_obtained'] / r['total_marks']) * 100
        percentages.append(perc)

    plt.figure(figsize=(10, 6))
    plt.plot(dates, percentages, marker='o', linestyle='-', color='#6366f1', linewidth=2, markersize=8)
    plt.title(f'Performance Trend: {student_name}', fontsize=16)
    plt.xlabel('Test Date', fontsize=12)
    plt.ylabel('Percentage (%)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.ylim(0, 105)
    plt.xticks(rotation=45)
    plt.tight_layout()

    report_dir = os.path.join(app.static_folder, 'reports')
    os.makedirs(report_dir, exist_ok=True)
    report_filename = f'{student_name.replace(" ", "_")}_report.png'
    report_path = os.path.join(report_dir, report_filename)
    
    plt.savefig(report_path)
    plt.close()

    return redirect(url_for('static', filename=f'reports/{report_filename}'))

@app.route('/add_topic', methods=['POST'])
@login_required
def add_topic():
    topic_name = request.form['topic_name']
    conn = get_db_connection()
    val = False if USE_POSTGRES else 0
    execute_query(conn, 'INSERT INTO syllabus (topic_name, status) VALUES (?, ?)', (topic_name, val), commit=True)
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/toggle_topic/<int:topic_id>', methods=['POST'])
@login_required
def toggle_topic(topic_id):
    conn = get_db_connection()
    topic = execute_query(conn, 'SELECT status FROM syllabus WHERE id = ?', (topic_id,), fetchone=True)
    if topic is not None:
        new_status = not bool(topic['status'])
        if not USE_POSTGRES:
            new_status = 1 if new_status else 0
        execute_query(conn, 'UPDATE syllabus SET status = ? WHERE id = ?', (new_status, topic_id), commit=True)
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_topic/<int:topic_id>', methods=['POST'])
@login_required
def delete_topic(topic_id):
    conn = get_db_connection()
    execute_query(conn, 'DELETE FROM syllabus WHERE id = ?', (topic_id,), commit=True)
    conn.close()
    return redirect(url_for('dashboard'))

# --- AI Insight Route ---
@app.route('/ai_insight/<student_name>')
@login_required
def ai_insight(student_name):
    if not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API key is not configured. Please add GEMINI_API_KEY to your environment variables."}), 500
        
    conn = get_db_connection()
    # Fetch last 5 records
    records = execute_query(conn, '''
        SELECT subject_topic, marks_obtained, total_marks, test_date
        FROM students 
        WHERE student_name = ?
        ORDER BY test_date DESC
        LIMIT 5
    ''', (student_name,), fetchall=True)
    conn.close()

    if not records:
        return jsonify({"error": "No records found for this student to analyze."}), 404

    # Format data for prompt
    marks_summary = []
    for r in reversed(records): # Reverse to be chronological for AI
        marks_summary.append(f"- {r['test_date']} ({r['subject_topic']}): {r['marks_obtained']}/{r['total_marks']}")
    
    marks_text = "\n".join(marks_summary)
    
    prompt = f"Analyze these test marks for a math teacher. Identify the overall performance trend and give ONE concise, actionable teaching suggestion.\n\nStudent: {student_name}\nRecent Marks:\n{marks_text}"
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        insight_text = response.text.strip()
        return jsonify({"insight": insight_text})
    except Exception as e:
        return jsonify({"error": f"Failed to generate insight from Gemini API: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
