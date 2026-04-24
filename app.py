import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
from ncert_data import NCERT_MATH_SYLLABUS

load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_local_secret_key_change_in_production")

# Database Configuration
DB_URL = os.environ.get('DATABASE_URL')
if DB_URL and DB_URL.startswith('postgres://'):
    DB_URL = DB_URL.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL or 'sqlite:///tutortrack.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='tutor')
    courses = db.relationship('CourseClass', backref='tutor', lazy=True, cascade="all, delete-orphan")

class CourseClass(db.Model):
    __tablename__ = 'course_classes'
    id = db.Column(db.Integer, primary_key=True)
    grade_level = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    students = db.relationship('Student', backref='course', lazy=True, cascade="all, delete-orphan")
    topics = db.relationship('Topic', backref='course', lazy=True, cascade="all, delete-orphan")

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    roll_number = db.Column(db.String(50))
    course_id = db.Column(db.Integer, db.ForeignKey('course_classes.id'), nullable=False)
    test_records = db.relationship('TestRecord', backref='student', lazy=True, cascade="all, delete-orphan")
    
    @property
    def average_percentage(self):
        if not self.test_records: return 0.0
        total_perc = sum((r.marks_obtained / r.total_marks) * 100 for r in self.test_records)
        return total_perc / len(self.test_records)

class Topic(db.Model):
    __tablename__ = 'topics'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    is_custom = db.Column(db.Boolean, default=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course_classes.id'), nullable=False)

class TestRecord(db.Model):
    __tablename__ = 'test_records'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    topic_name = db.Column(db.String(200), nullable=True) # Optional link to what test was about
    marks_obtained = db.Column(db.Integer, nullable=False)
    total_marks = db.Column(db.Integer, default=100)
    test_date = db.Column(db.Date, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize DB tables
with app.app_context():
    db.create_all()


# --- Auth Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('signup'))
            
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password, role='tutor')
        db.session.add(new_user)
        db.session.commit()
        
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
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
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
    courses = CourseClass.query.filter_by(user_id=current_user.id).all()
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    return render_template('index.html', courses=courses, current_date=current_date)

@app.route('/create_course', methods=['POST'])
@login_required
def create_course():
    grade_level = int(request.form['grade_level'])
    subject = request.form['subject']
    
    new_course = CourseClass(grade_level=grade_level, subject=subject, user_id=current_user.id)
    db.session.add(new_course)
    db.session.flush() # Get ID before commit
    
    # Auto-populate NCERT syllabus if applicable
    if subject.lower() == 'math' and grade_level in NCERT_MATH_SYLLABUS:
        for topic_name in NCERT_MATH_SYLLABUS[grade_level]:
            t = Topic(name=topic_name, course_id=new_course.id, is_custom=False)
            db.session.add(t)
            
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/course/<int:course_id>')
@login_required
def view_course(course_id):
    course = CourseClass.query.get_or_404(course_id)
    if course.user_id != current_user.id:
        return "Unauthorized", 403
        
    students = course.students
    topics = course.topics
    pending_topics = [t for t in topics if not t.is_completed]
    covered_topics = [t for t in topics if t.is_completed]
    
    # Analytics Logic
    class_average = 0.0
    students_with_records = [s for s in students if len(s.test_records) > 0]
    
    top_performers = []
    needs_support = []
    
    if students_with_records:
        class_average = sum(s.average_percentage for s in students_with_records) / len(students_with_records)
        for s in students_with_records:
            if s.average_percentage < (class_average * 0.8):
                needs_support.append(s)
            elif s.average_percentage > (class_average * 1.1):
                top_performers.append(s)

    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    return render_template('course.html', course=course, students=students, 
                           pending_topics=pending_topics, covered_topics=covered_topics,
                           class_average=class_average, top_performers=top_performers, 
                           needs_support=needs_support, current_date=current_date)

@app.route('/course/<int:course_id>/add_student', methods=['POST'])
@login_required
def add_student(course_id):
    name = request.form['student_name']
    roll_number = request.form['roll_number']
    
    new_student = Student(name=name, roll_number=roll_number, course_id=course_id)
    db.session.add(new_student)
    db.session.commit()
    return redirect(url_for('view_course', course_id=course_id))

@app.route('/student/<int:student_id>/add_marks', methods=['POST'])
@login_required
def add_marks(student_id):
    student = Student.query.get_or_404(student_id)
    if student.course.user_id != current_user.id:
        return "Unauthorized", 403
        
    topic_name = request.form['topic_name']
    marks_obtained = int(request.form['marks_obtained'])
    total_marks = int(request.form.get('total_marks', 100))
    # Parse date from YYYY-MM-DD
    test_date_str = request.form['test_date']
    test_date = datetime.datetime.strptime(test_date_str, "%Y-%m-%d").date()

    record = TestRecord(student_id=student.id, topic_name=topic_name, marks_obtained=marks_obtained, 
                        total_marks=total_marks, test_date=test_date)
    db.session.add(record)
    db.session.commit()
    
    return redirect(url_for('view_course', course_id=student.course_id))

@app.route('/course/<int:course_id>/add_topic', methods=['POST'])
@login_required
def add_topic(course_id):
    name = request.form['topic_name']
    t = Topic(name=name, course_id=course_id, is_custom=True)
    db.session.add(t)
    db.session.commit()
    return redirect(url_for('view_course', course_id=course_id))

@app.route('/topic/<int:topic_id>/toggle', methods=['POST'])
@login_required
def toggle_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    if topic.course.user_id != current_user.id: return "Unauthorized", 403
    
    topic.is_completed = not topic.is_completed
    db.session.commit()
    return redirect(url_for('view_course', course_id=topic.course_id))

@app.route('/topic/<int:topic_id>/delete', methods=['POST'])
@login_required
def delete_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    if topic.course.user_id != current_user.id: return "Unauthorized", 403
    course_id = topic.course_id
    db.session.delete(topic)
    db.session.commit()
    return redirect(url_for('view_course', course_id=course_id))

@app.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    if student.course.user_id != current_user.id: return "Unauthorized", 403
    course_id = student.course_id
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for('view_course', course_id=course_id))

# --- AI Insight Route ---
@app.route('/ai_insight/<int:student_id>')
@login_required
def ai_insight(student_id):
    if not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API key is not configured. Please add GEMINI_API_KEY to your environment variables."}), 500
        
    student = Student.query.get_or_404(student_id)
    if student.course.user_id != current_user.id: return jsonify({"error": "Unauthorized"}), 403
    
    # Fetch last 5 records
    records = TestRecord.query.filter_by(student_id=student.id).order_by(TestRecord.test_date.desc()).limit(5).all()

    if not records:
        return jsonify({"error": "No records found for this student to analyze."}), 404

    marks_summary = []
    for r in reversed(records):
        marks_summary.append(f"- {r.test_date} ({r.topic_name}): {r.marks_obtained}/{r.total_marks}")
    
    marks_text = "\n".join(marks_summary)
    
    prompt = f"Analyze these test marks for a math teacher. Identify the overall performance trend and give ONE concise, actionable teaching suggestion.\n\nStudent: {student.name}\nRecent Marks:\n{marks_text}"
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        insight_text = response.text.strip()
        return jsonify({"insight": insight_text})
    except Exception as e:
        return jsonify({"error": f"Failed to generate insight: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
