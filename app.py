import os
import matplotlib
matplotlib.use('Agg')  # Headless mode for matplolib
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)

# Determine if we should use PostgreSQL or fallback to SQLite
DB_URL = os.environ.get('DATABASE_URL')
# Render provides postgres:// sometimes instead of postgresql://
if DB_URL and DB_URL.startswith('postgres'):
    USE_POSTGRES = True
    # Fix older postgres:// URI formats for sqlalchemy/psycopg2 if needed
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
    """A database-agnostic query executor."""
    # Convert SQLite '?' parameters to PostgreSQL '%s' if necessary
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

def init_db():
    conn = get_db_connection()
    
    # Database-specific syntax
    if USE_POSTGRES:
        pk_type = "SERIAL PRIMARY KEY"
        bool_default = "DEFAULT FALSE"
    else:
        pk_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
        bool_default = "DEFAULT 0"

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

# Initialize db at startup
init_db()

@app.route('/')
def dashboard():
    conn = get_db_connection()
    records = execute_query(conn, 'SELECT * FROM students ORDER BY test_date DESC', fetchall=True)
    syllabus_items = execute_query(conn, 'SELECT * FROM syllabus ORDER BY id DESC', fetchall=True)
    conn.close()
    
    pending_topics = [item for item in syllabus_items if not item['status']]
    covered_topics = [item for item in syllabus_items if item['status']]
    
    return render_template('index.html', records=records, pending_topics=pending_topics, covered_topics=covered_topics)

@app.route('/add_marks', methods=['POST'])
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
def add_topic():
    topic_name = request.form['topic_name']
    conn = get_db_connection()
    # Using 0/1 for fallback logic as SQLite booleans are just ints and Postgres handles it fine. 
    # Or explicitly use False to be Postgres native (SQLite supports True/False by casting to 1/0).
    val = False if USE_POSTGRES else 0
    execute_query(conn, 'INSERT INTO syllabus (topic_name, status) VALUES (?, ?)', (topic_name, val), commit=True)
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/toggle_topic/<int:topic_id>', methods=['POST'])
def toggle_topic(topic_id):
    conn = get_db_connection()
    topic = execute_query(conn, 'SELECT status FROM syllabus WHERE id = ?', (topic_id,), fetchone=True)
    if topic is not None:
        # Flip the status boolean
        new_status = not bool(topic['status'])
        # Depending on engine, ensure format is correct
        if not USE_POSTGRES:
            new_status = 1 if new_status else 0
            
        execute_query(conn, 'UPDATE syllabus SET status = ? WHERE id = ?', (new_status, topic_id), commit=True)
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_topic/<int:topic_id>', methods=['POST'])
def delete_topic(topic_id):
    conn = get_db_connection()
    execute_query(conn, 'DELETE FROM syllabus WHERE id = ?', (topic_id,), commit=True)
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
