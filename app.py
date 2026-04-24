import os
import sqlite3
import matplotlib
matplotlib.use('Agg')  # Headless mode for matplolib
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
DB_FILE = 'tutortrack.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            subject_topic TEXT NOT NULL,
            marks_obtained INTEGER NOT NULL,
            total_marks INTEGER DEFAULT 100,
            test_date DATE NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS syllabus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_name TEXT NOT NULL,
            status BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# Initialize db at startup
init_db()

@app.route('/')
def dashboard():
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM students ORDER BY test_date DESC').fetchall()
    
    # Fetch syllabus items
    syllabus_items = conn.execute('SELECT * FROM syllabus ORDER BY id DESC').fetchall()
    pending_topics = [item for item in syllabus_items if not item['status']]
    covered_topics = [item for item in syllabus_items if item['status']]
    
    conn.close()
    return render_template('index.html', records=records, pending_topics=pending_topics, covered_topics=covered_topics)

@app.route('/add_marks', methods=['POST'])
def add_marks():
    student_name = request.form['student_name']
    subject_topic = request.form['subject_topic']
    marks_obtained = int(request.form['marks_obtained'])
    total_marks = int(request.form.get('total_marks', 100))
    test_date = request.form['test_date']

    conn = get_db_connection()
    conn.execute('INSERT INTO students (student_name, subject_topic, marks_obtained, total_marks, test_date) VALUES (?, ?, ?, ?, ?)',
                 (student_name, subject_topic, marks_obtained, total_marks, test_date))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/generate_report/<student_name>')
def generate_report(student_name):
    conn = get_db_connection()
    records = conn.execute('''
        SELECT test_date, marks_obtained, total_marks
        FROM students 
        WHERE student_name = ?
        ORDER BY test_date ASC
    ''', (student_name,)).fetchall()
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
    conn.execute('INSERT INTO syllabus (topic_name, status) VALUES (?, 0)', (topic_name,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/toggle_topic/<int:topic_id>', methods=['POST'])
def toggle_topic(topic_id):
    conn = get_db_connection()
    topic = conn.execute('SELECT status FROM syllabus WHERE id = ?', (topic_id,)).fetchone()
    if topic is not None:
        new_status = 1 if topic['status'] == 0 else 0
        conn.execute('UPDATE syllabus SET status = ? WHERE id = ?', (new_status, topic_id))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_topic/<int:topic_id>', methods=['POST'])
def delete_topic(topic_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM syllabus WHERE id = ?', (topic_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
