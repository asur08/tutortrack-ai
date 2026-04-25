import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
import google.generativeai as genai
from ncert_data import NCERT_MATH_SYLLABUS, NCERT_SCIENCE_SYLLABUS
import random
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

# Mail Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 'yes']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@tutortrack.ai')

mail = Mail(app)
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
    role = db.Column(db.String(20), default='student')
    is_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    courses = db.relationship('CourseClass', backref='tutor', lazy=True, cascade="all, delete-orphan")
    is_superadmin = db.Column(db.Boolean, default=False)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    referral_code = db.Column(db.String(50), unique=True, nullable=True)
    referred_by = db.Column(db.String(50), nullable=True)
    is_approved = db.Column(db.Boolean, default=False)
    is_suspended = db.Column(db.Boolean, default=False)
    account_status = db.Column(db.String(20), default='active')  # active, deleted
    tickets = db.relationship('SupportTicket', backref='user', lazy=True, cascade="all, delete-orphan")

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class MasterSyllabus(db.Model):
    __tablename__ = 'master_syllabus'
    id = db.Column(db.Integer, primary_key=True)
    grade_level = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    topic_name = db.Column(db.String(200), nullable=False)

class CourseClass(db.Model):
    __tablename__ = 'course_classes'
    id = db.Column(db.Integer, primary_key=True)
    grade_level = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    class_code = db.Column(db.String(6), unique=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    students = db.relationship('Student', backref='course', lazy=True, cascade="all, delete-orphan")
    topics = db.relationship('Topic', backref='course', lazy=True, cascade="all, delete-orphan")

class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('course_classes.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    
    student_user = db.relationship('User', backref='enrollments', lazy=True)
    course = db.relationship('CourseClass', backref='course_enrollments', lazy=True)

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    roll_number = db.Column(db.String(50))
    parent_phone = db.Column(db.String(20), nullable=True)
    fee_status = db.Column(db.Boolean, default=False)
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
    
    # --- Auto-migration for existing databases (e.g. Render PostgreSQL) ---
    # db.create_all() only creates NEW tables; it won't add columns to existing ones.
    # This block safely patches any missing columns so old user rows don't crash.
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    
    if 'users' in inspector.get_table_names():
        existing_columns = {col['name'] for col in inspector.get_columns('users')}
        
        migrations = {
            'is_verified': "ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE",
            'otp_code': "ALTER TABLE users ADD COLUMN otp_code VARCHAR(6)",
            'otp_expiry': "ALTER TABLE users ADD COLUMN otp_expiry TIMESTAMP",
            'is_superadmin': "ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE",
            'trial_ends_at': "ALTER TABLE users ADD COLUMN trial_ends_at TIMESTAMP",
            'referral_code': "ALTER TABLE users ADD COLUMN referral_code VARCHAR(50)",
            'referred_by': "ALTER TABLE users ADD COLUMN referred_by VARCHAR(50)",
            'is_approved': "ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT FALSE",
            'is_suspended': "ALTER TABLE users ADD COLUMN is_suspended BOOLEAN DEFAULT FALSE",
            'account_status': "ALTER TABLE users ADD COLUMN account_status VARCHAR(20) DEFAULT 'active'",
        }
        
        for col_name, alter_sql in migrations.items():
            if col_name not in existing_columns:
                try:
                    db.session.execute(text(alter_sql))
                    db.session.commit()
                    print(f"[MIGRATION] Added missing column: users.{col_name}")
                except Exception as e:
                    db.session.rollback()
                    print(f"[MIGRATION] Skipping users.{col_name}: {e}")
        
        # Mark all pre-existing users as verified and approved so they can log in
        try:
            db.session.execute(text("UPDATE users SET is_verified = TRUE WHERE is_verified IS NULL OR is_verified = FALSE"))
            db.session.execute(text("UPDATE users SET is_approved = TRUE WHERE is_approved IS NULL OR is_approved = FALSE"))
            # Ensure the master admin account has superadmin privileges
            db.session.execute(text("UPDATE users SET is_superadmin = TRUE, role = 'admin' WHERE username = 'tutortrackerai@gmail.com'"))
            db.session.commit()
            print("[MIGRATION] Marked existing users as verified/approved. Master admin promoted.")
        except Exception as e:
            db.session.rollback()
            print(f"[MIGRATION] Could not update existing users: {e}")
    
    # Pre-load MasterSyllabus if empty
    if MasterSyllabus.query.count() == 0:
        for grade, topics in NCERT_MATH_SYLLABUS.items():
            for t in topics:
                db.session.add(MasterSyllabus(grade_level=grade, subject='Math', topic_name=t))
        for grade, topics in NCERT_SCIENCE_SYLLABUS.items():
            for t in topics:
                db.session.add(MasterSyllabus(grade_level=grade, subject='Science', topic_name=t))
        db.session.commit()


# --- Auth Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username/Email already exists.', 'error')
            return redirect(url_for('signup'))
            
        hashed_password = generate_password_hash(password)
        role = request.form.get('role', 'student')
        if role not in ['teacher', 'student', 'admin']:
            role = 'student'
            
        is_superadmin = False
        is_approved = True
        referral_code = None
        referred_by = request.form.get('referred_by', None)
        
        if username == 'tutortrackerai@gmail.com':
            role = 'admin'
            is_superadmin = True
            is_approved = True
            
        if role == 'teacher':
            is_approved = False
            import string
            import random
            while True:
                code = 'TCH-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                if not User.query.filter_by(referral_code=code).first():
                    referral_code = code
                    break
            
        otp = str(random.randint(100000, 999999))
        expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        new_user = User(username=username, password_hash=hashed_password, role=role, otp_code=otp, otp_expiry=expiry,
                        is_superadmin=is_superadmin, is_approved=is_approved, referral_code=referral_code, referred_by=referred_by)
        db.session.add(new_user)
        db.session.commit()
        
        try:
            msg = Message("Your TutorTrack AI Verification Code", recipients=[username])
            msg.body = f"Your verification code is: {otp}. It expires in 10 minutes."
            mail.send(msg)
            flash('Verification code sent to your email.', 'success')
        except Exception as e:
            print(f"FAILED TO SEND EMAIL. OTP IS: {otp}")
            flash('Failed to send email. Check console for OTP in development.', 'error')
            
        return redirect(url_for('verify', user_id=new_user.id))
        
    return render_template('signup.html')

@app.route('/verify/<int:user_id>', methods=['GET', 'POST'])
def verify(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_verified:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        otp_input = request.form.get('otp')
        if user.otp_code == otp_input and user.otp_expiry and datetime.datetime.now() <= user.otp_expiry:
            user.is_verified = True
            user.otp_code = None
            user.otp_expiry = None
            db.session.commit()
            flash('Account verified successfully! You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid or expired OTP. Please try again.', 'error')
            
    return render_template('verify.html', user_id=user_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Block suspended or soft-deleted accounts
            if user.is_suspended or (hasattr(user, 'account_status') and user.account_status == 'deleted'):
                flash('This account has been suspended or deleted. Please contact support.', 'error')
                return redirect(url_for('login'))
            
            if not user.is_verified:
                otp = str(random.randint(100000, 999999))
                user.otp_code = otp
                user.otp_expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)
                db.session.commit()
                try:
                    msg = Message("Your TutorTrack AI Verification Code", recipients=[username])
                    msg.body = f"Your new verification code is: {otp}. It expires in 10 minutes."
                    mail.send(msg)
                except Exception as e:
                    print(f"FAILED TO SEND EMAIL. OTP IS: {otp}")
                flash('Please verify your account first. A new code has been sent.', 'error')
                return redirect(url_for('verify', user_id=user.id))
                
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

from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    pending_teachers = User.query.filter_by(role='teacher', is_approved=False).all()
    all_teachers = User.query.filter_by(role='teacher').all()
    all_students = User.query.filter_by(role='student').all()
    open_tickets = SupportTicket.query.filter_by(status='open').all()
    now = datetime.datetime.now()
    active_trials = User.query.filter(User.role == 'student', User.trial_ends_at != None, User.trial_ends_at > now).count()
    expired_trials = User.query.filter(User.role == 'student', User.trial_ends_at != None, User.trial_ends_at <= now).count()
    referrals_count = User.query.filter(User.referred_by != None, User.referred_by != '').count()
    
    return render_template('admin_dashboard.html', 
                           pending_teachers=pending_teachers,
                           all_teachers=all_teachers,
                           all_students=all_students,
                           open_tickets=open_tickets,
                           active_trials=active_trials,
                           expired_trials=expired_trials,
                           referrals_count=referrals_count)

@app.route('/admin/approve_teacher/<int:teacher_id>', methods=['POST'])
@login_required
@admin_required
def approve_teacher(teacher_id):
    teacher = User.query.get_or_404(teacher_id)
    if teacher.role == 'teacher':
        teacher.is_approved = True
        db.session.commit()
        flash(f'Teacher {teacher.username} approved.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/resolve_ticket/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def resolve_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    ticket.status = 'resolved'
    db.session.commit()
    flash(f'Ticket #{ticket.id} marked as resolved.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/suspend_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash('Cannot suspend a superadmin account.', 'error')
        return redirect(url_for('admin_dashboard'))
    user.is_suspended = True
    db.session.commit()
    flash(f'User {user.username} has been suspended.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/unsuspend_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def unsuspend_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_suspended = False
    db.session.commit()
    flash(f'User {user.username} has been reactivated.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash('Cannot delete a superadmin account.', 'error')
        return redirect(url_for('admin_dashboard'))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User {username} has been permanently deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash('Cannot change the role of a superadmin.', 'error')
        return redirect(url_for('admin_dashboard'))
    new_role = request.form.get('role')
    if new_role not in ['teacher', 'student', 'parent', 'admin']:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('admin_dashboard'))
    user.role = new_role
    db.session.commit()
    flash(f'User role updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/delete_my_account', methods=['POST'])
@login_required
def delete_my_account():
    user = current_user
    if user.is_superadmin:
        flash('Superadmin accounts cannot be self-deleted.', 'error')
        return redirect(url_for('settings'))
    user.account_status = 'deleted'
    db.session.commit()
    logout_user()
    flash('Your account has been deleted. We are sorry to see you go.', 'success')
    return redirect(url_for('signup'))

@app.route('/submit_ticket', methods=['POST'])
@login_required
def submit_ticket():
    subject = request.form.get('subject')
    message = request.form.get('message')
    
    ticket = SupportTicket(user_id=current_user.id, subject=subject, message=message)
    db.session.add(ticket)
    db.session.commit()
    
    try:
        msg = Message(f"New Ticket from {current_user.username}: {subject}", recipients=['tutortrackerai@gmail.com'])
        msg.body = f"User: {current_user.username}\nRole: {current_user.role}\n\nSubject: {subject}\n\nMessage:\n{message}"
        mail.send(msg)
    except Exception as e:
        print(f"FAILED TO SEND TICKET EMAIL: {e}")
        
    flash('Your support ticket has been submitted successfully.', 'success')
    return redirect(request.referrer or url_for('dashboard'))


# --- Main App Routes ---
@app.route('/')
@login_required
def dashboard():
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    if current_user.is_superadmin:
        return redirect(url_for('admin_dashboard'))
    
    if current_user.role == 'teacher':
        if not current_user.is_approved:
            return render_template('index.html', unapproved_teacher=True, current_date=current_date)
            
        courses = CourseClass.query.filter_by(user_id=current_user.id).all()
        course_ids = [c.id for c in courses]
        pending_requests = Enrollment.query.filter(Enrollment.class_id.in_(course_ids), Enrollment.status == 'pending').all() if course_ids else []
        
        all_students = []
        for c in courses:
            all_students.extend(c.students)
            
        return render_template('index.html', courses=courses, pending_requests=pending_requests, all_students=all_students, current_date=current_date)
    else:
        enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
        return render_template('index.html', enrollments=enrollments, current_date=current_date)

@app.route('/create_course', methods=['POST'])
@login_required
def create_course():
    if current_user.role != 'teacher' or not current_user.is_approved:
        return "Unauthorized", 403
        
    import string
    
    grade_level = int(request.form['grade_level'])
    subject = request.form['subject']
    import_ncert = request.form.get('import_ncert') == 'on'
    
    # Generate unique 6-character code
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not CourseClass.query.filter_by(class_code=code).first():
            break
            
    new_course = CourseClass(grade_level=grade_level, subject=subject, class_code=code, user_id=current_user.id)
    db.session.add(new_course)
    db.session.flush() # Get ID before commit
    
    # Auto-populate NCERT syllabus if requested
    if import_ncert:
        topics = MasterSyllabus.query.filter_by(grade_level=grade_level, subject=subject).all()
        for t in topics:
            new_topic = Topic(name=t.topic_name, course_id=new_course.id, is_custom=False)
            db.session.add(new_topic)
            
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/join_class', methods=['POST'])
@login_required
def join_class():
    if current_user.role != 'student':
        return "Unauthorized", 403
        
    class_code = request.form.get('class_code')
    course = CourseClass.query.filter_by(class_code=class_code).first()
    
    if not course:
        flash('Invalid class code.', 'error')
        return redirect(url_for('dashboard'))
        
    existing_enrollment = Enrollment.query.filter_by(student_id=current_user.id, class_id=course.id).first()
    if existing_enrollment:
        flash('You have already joined or requested to join this class.', 'error')
        return redirect(url_for('dashboard'))
        
    new_enrollment = Enrollment(student_id=current_user.id, class_id=course.id, status='pending')
    db.session.add(new_enrollment)
    
    if not current_user.trial_ends_at:
        current_user.trial_ends_at = datetime.datetime.now() + datetime.timedelta(days=30)
        
    db.session.commit()
    flash(f'Request to join {course.subject} Class {course.grade_level} sent! Waiting for teacher approval.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/approve_request/<int:enrollment_id>', methods=['POST'])
@login_required
def approve_request(enrollment_id):
    if current_user.role != 'teacher':
        return "Unauthorized", 403
        
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    if enrollment.course.user_id != current_user.id:
        return "Unauthorized", 403
        
    enrollment.status = 'approved'
    db.session.commit()
    flash(f'Approved student {enrollment.student_user.username}.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/reject_request/<int:enrollment_id>', methods=['POST'])
@login_required
def reject_request(enrollment_id):
    if current_user.role != 'teacher':
        return "Unauthorized", 403
        
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    if enrollment.course.user_id != current_user.id:
        return "Unauthorized", 403
        
    db.session.delete(enrollment)
    db.session.commit()
    flash('Rejected student request.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/course/<int:course_id>')
@login_required
def view_course(course_id):
    course = CourseClass.query.get_or_404(course_id)
    
    # Check access permissions
    if current_user.role == 'teacher':
        if course.user_id != current_user.id:
            return "Unauthorized", 403
    elif current_user.role == 'student':
        enrollment = Enrollment.query.filter_by(student_id=current_user.id, class_id=course.id, status='approved').first()
        if not enrollment:
            return "Unauthorized. You are not approved for this class.", 403
    else:
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
    now = datetime.datetime.now()
    is_trial_expired = False
    if current_user.role == 'student' and current_user.trial_ends_at:
        if current_user.trial_ends_at < now:
            is_trial_expired = True
    
    return render_template('course.html', course=course, students=students, 
                           pending_topics=pending_topics, covered_topics=covered_topics,
                           class_average=class_average, top_performers=top_performers, 
                           needs_support=needs_support, current_date=current_date, is_trial_expired=is_trial_expired)

@app.route('/course/<int:course_id>/add_student', methods=['POST'])
@login_required
def add_student(course_id):
    if current_user.role == 'student': return "Unauthorized", 403
    name = request.form['student_name']
    roll_number = request.form.get('roll_number', '')
    parent_phone = request.form.get('parent_phone', '')
    
    new_student = Student(name=name, roll_number=roll_number, parent_phone=parent_phone, course_id=course_id)
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

@app.route('/toggle_fee/<int:student_id>', methods=['POST'])
@login_required
def toggle_fee(student_id):
    if current_user.role != 'teacher': return "Unauthorized", 403
    student = Student.query.get_or_404(student_id)
    if student.course.user_id != current_user.id: return "Unauthorized", 403
        
    student.fee_status = not student.fee_status
    db.session.commit()
    flash(f"Fee status updated for {student.name}", 'success')
    return redirect(url_for('dashboard'))

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
    app.run(debug=True, port=5001)
