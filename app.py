import os
import calendar
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from models import db, User, Student, Course, CourseSession, HourlyLesson, Expense

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tutorpay-secret-key-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'tutorpay.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'กรุณาเข้าสู่ระบบก่อน'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============================================================
# Database Init + Seed Migration
# ============================================================
with app.app_context():
    db.create_all()

    # --- Schema migration: add user_id columns to existing tables ---
    import sqlalchemy
    inspector = sqlalchemy.inspect(db.engine)

    # Add user_id to students if missing
    student_cols = [c['name'] for c in inspector.get_columns('students')]
    if 'user_id' not in student_cols:
        db.session.execute(sqlalchemy.text('ALTER TABLE students ADD COLUMN user_id INTEGER REFERENCES users(id)'))
        db.session.commit()

    # Add user_id to expenses if missing
    expense_cols = [c['name'] for c in inspector.get_columns('expenses')]
    if 'user_id' not in expense_cols:
        db.session.execute(sqlalchemy.text('ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id)'))
        db.session.commit()

    # --- Seed user + data migration ---
    seed_email = 'nichchanprakhunt@gmail.com'
    seed_user = User.query.filter_by(email=seed_email).first()
    if not seed_user:
        seed_user = User(
            email=seed_email,
            password_hash=bcrypt.generate_password_hash('Nichchan_1993').decode('utf-8'),
            display_name='Nichchan',
        )
        db.session.add(seed_user)
        db.session.commit()

    # Assign orphan students (user_id is NULL) to seed user
    Student.query.filter(Student.user_id.is_(None)).update({'user_id': seed_user.id})
    Expense.query.filter(Expense.user_id.is_(None)).update({'user_id': seed_user.id})
    db.session.commit()

    # --- Schema migration: payment_method / transfer_ref ---
    hourly_cols = [c['name'] for c in inspector.get_columns('hourly_lessons')]
    if 'payment_method' not in hourly_cols:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE hourly_lessons ADD COLUMN payment_method VARCHAR(50) DEFAULT 'โอนธนาคาร'"
        ))
        db.session.commit()
    if 'transfer_ref' not in hourly_cols:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE hourly_lessons ADD COLUMN transfer_ref VARCHAR(100) DEFAULT ''"
        ))
        db.session.commit()

    course_cols_all = [c['name'] for c in inspector.get_columns('courses')]
    if 'payment_method' not in course_cols_all:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE courses ADD COLUMN payment_method VARCHAR(50) DEFAULT 'โอนธนาคาร'"
        ))
        db.session.commit()
    if 'transfer_ref' not in course_cols_all:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE courses ADD COLUMN transfer_ref VARCHAR(100) DEFAULT ''"
        ))
        db.session.commit()
    if 'payment_date' not in course_cols_all:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE courses ADD COLUMN payment_date DATE"
        ))
        db.session.commit()
        # Backfill old records to use created_at date
        db.session.execute(sqlalchemy.text(
            "UPDATE courses SET payment_date = date(created_at) WHERE payment_date IS NULL"
        ))
        db.session.commit()
    if 'expiry_date' not in course_cols_all:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE courses ADD COLUMN expiry_date DATE"
        ))
        db.session.commit()

    session_cols_all = [c['name'] for c in inspector.get_columns('course_sessions')]
    if 'status' not in session_cols_all:
        db.session.execute(sqlalchemy.text(
            "ALTER TABLE course_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'present'"
        ))
        db.session.commit()


# ============================================================
# Authentication Routes
# ============================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            flash(f'ยินดีต้อนรับ {user.display_name}! 🎉', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('อีเมลหรือรหัสผ่านไม่ถูกต้อง', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not display_name or not email or not password:
            flash('กรุณากรอกข้อมูลให้ครบ', 'error')
            return redirect(url_for('register'))

        if password != confirm:
            flash('รหัสผ่านไม่ตรงกัน', 'error')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('อีเมลนี้ถูกใช้งานแล้ว', 'error')
            return redirect(url_for('register'))

        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            display_name=display_name,
        )
        db.session.add(user)
        db.session.commit()

        login_user(user, remember=True)
        flash(f'ลงทะเบียนสำเร็จ! ยินดีต้อนรับ {display_name} 🎉', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ออกจากระบบเรียบร้อย', 'success')
    return redirect(url_for('login'))


# ============================================================
# Shared: Period filter helper
# ============================================================
THAI_MONTHS = [
    '', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน',
    'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม',
    'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


def calculate_tax(net_income):
    """Calculate Thai personal income tax brackets (ภ.ง.ด.90)."""
    if net_income <= 0:
        return 0.0
    brackets = [
        (150_000,   0.00),
        (300_000,   0.05),
        (500_000,   0.10),
        (750_000,   0.15),
        (1_000_000, 0.20),
        (2_000_000, 0.25),
        (5_000_000, 0.30),
        (float('inf'), 0.35),
    ]
    tax, prev = 0.0, 0
    for ceiling, rate in brackets:
        if net_income <= prev:
            break
        chunk = min(net_income, ceiling) - prev
        tax += chunk * rate
        prev = ceiling
    return tax


def parse_period_filters():
    """Parse period/month/year query params and return filter context dict."""
    period = request.args.get('period', 'month')
    today = date.today()

    report_month = request.args.get('report_month', today.month, type=int)
    report_year = request.args.get('report_year', today.year, type=int)

    report_month = max(1, min(12, report_month))
    report_year = max(2020, min(2099, report_year))

    if period == 'year':
        date_from = date(report_year, 1, 1)
        date_to = date(report_year, 12, 31)
    elif period == 'custom':
        try:
            date_from = datetime.strptime(request.args.get('date_from', ''), '%Y-%m-%d').date()
            date_to = datetime.strptime(request.args.get('date_to', ''), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_from = today.replace(day=1)
            date_to = today
    else:
        period = 'month'
        _, last_day = calendar.monthrange(report_year, report_month)
        date_from = date(report_year, report_month, 1)
        date_to = date(report_year, report_month, last_day)

    if period == 'month':
        period_label = f'{THAI_MONTHS[report_month]} {report_year}'
    elif period == 'year':
        period_label = f'ปี {report_year}'
    else:
        period_label = f'{date_from.strftime("%d/%m/%Y")} — {date_to.strftime("%d/%m/%Y")}'

    available_years = list(range(2020, today.year + 2))

    return {
        'period': period,
        'report_month': report_month,
        'report_year': report_year,
        'date_from': date_from,
        'date_to': date_to,
        'period_label': period_label,
        'thai_months': THAI_MONTHS,
        'available_years': available_years,
    }


def my_students():
    """Return students belonging to current user."""
    return Student.query.filter_by(user_id=current_user.id)


def my_student_ids():
    """Return list of student IDs belonging to current user."""
    return [s.id for s in my_students().all()]


SESSIONS_PER_MONTH = 4  # อัตรามาตรฐาน 4 ครั้ง/เดือน


def calc_course_duration(course):
    """คำนวณระยะเวลาจริง vs คาด และ opportunity cost"""
    if not course.payment_date:
        return None
    start = course.payment_date
    end = date.today() if not course.is_completed else None

    # หาวันสุดท้ายจาก session ถ้ามี
    if course.sessions:
        sessions_sorted = sorted(course.sessions, key=lambda s: s.session_date)
        last_session_date = sessions_sorted[-1].session_date
        if course.is_completed:
            end = last_session_date
        else:
            # ยังไม่จบ → ใช้ today แต่เทียบกับ last session ด้วย
            end = date.today()
    elif not course.is_completed:
        end = date.today()
    else:
        end = start  # completed but no sessions recorded

    actual_days = max(0, (end - start).days)
    actual_months = round(actual_days / 30, 1)
    expected_months = round(course.total_sessions / SESSIONS_PER_MONTH, 1)
    delay_months = round(actual_months - expected_months, 1)
    rate_per_month = course.price_per_course / expected_months if expected_months > 0 else 0
    opp_cost = round(max(0.0, delay_months) * rate_per_month)

    return {
        'start': start,
        'end': end,
        'actual_months': actual_months,
        'expected_months': expected_months,
        'delay_months': delay_months,
        'rate_per_month': round(rate_per_month),
        'opp_cost': opp_cost,
        'is_on_time': delay_months <= 0,
        'is_completed': course.is_completed,
    }


# ============================================================
# Dashboard
# ============================================================
@app.route('/')
@login_required
def dashboard():
    pf = parse_period_filters()
    date_from = pf['date_from']
    date_to = pf['date_to']

    sid_list = my_student_ids()
    students = my_students().all()

    # Filtered queries — scoped to current user's students
    hourly_lessons = HourlyLesson.query.filter(
        HourlyLesson.student_id.in_(sid_list),
        HourlyLesson.date >= date_from, HourlyLesson.date <= date_to,
    ).order_by(HourlyLesson.date.desc()).all()

    courses = Course.query.filter(
        Course.student_id.in_(sid_list),
        Course.payment_date >= date_from,
        Course.payment_date <= date_to,
    ).order_by(Course.payment_date.desc()).all()

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= date_from, Expense.date <= date_to,
    ).all()

    total_hourly = sum(h.hours * h.rate_per_hour for h in hourly_lessons)
    total_course = sum(c.price_per_course for c in courses)
    total_income = total_hourly + total_course
    total_expenses = sum(e.amount for e in expenses)

    completed_courses = [c for c in courses if c.is_completed]
    near_complete_courses = [c for c in courses if not c.is_completed and c.remaining_sessions <= 2 and c.remaining_sessions > 0]
    active_course_list = [c for c in courses if not c.is_completed]

    return render_template('dashboard.html',
        **pf,
        filter_action=url_for('dashboard'),
        total_income=total_income,
        total_expenses=total_expenses,
        student_count=len(students),
        active_courses=len(active_course_list),
        completed_course_count=len(completed_courses),
        completed_courses=completed_courses,
        near_complete_courses=near_complete_courses,
        active_course_list=active_course_list,
        recent_lessons=hourly_lessons[:10],
    )


# ============================================================
# Students
# ============================================================
@app.route('/students')
@login_required
def students_page():
    pf = parse_period_filters()
    date_from = pf['date_from']
    date_to = pf['date_to']
    active_only = request.args.get('active_only', 0, type=int)

    sid_list = my_student_ids()
    students = my_students().order_by(Student.name).all()

    # Filter active students: มีคอร์สที่ยังไม่จบ และ payment_date <= date_to
    if active_only:
        active_sids = {
            c.student_id for c in Course.query.filter(
                Course.student_id.in_(sid_list),
                Course.payment_date <= date_to,
                Course.is_completed == False,
            ).all()
        }
        students = [s for s in students if s.id in active_sids]

    # Compute per-student income within the period
    cur_sid_list = [s.id for s in students]
    filtered_lessons = HourlyLesson.query.filter(
        HourlyLesson.student_id.in_(cur_sid_list),
        HourlyLesson.date >= date_from, HourlyLesson.date <= date_to,
    ).all()
    filtered_courses = Course.query.filter(
        Course.student_id.in_(cur_sid_list),
        Course.payment_date >= date_from,
        Course.payment_date <= date_to,
    ).all()

    student_income_map = {}
    for h in filtered_lessons:
        student_income_map[h.student_id] = student_income_map.get(h.student_id, 0) + h.total_amount
    for c in filtered_courses:
        student_income_map[c.student_id] = student_income_map.get(c.student_id, 0) + c.price_per_course

    return render_template('students.html',
        **pf,
        filter_action=url_for('students_page'),
        students=students,
        student_income_map=student_income_map,
        active_only=active_only,
    )


@app.route('/students/add', methods=['POST'])
@login_required
def add_student():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()

    if not name:
        flash('กรุณากรอกชื่อนักเรียน', 'error')
        return redirect(url_for('students_page'))

    student = Student(name=name, phone=phone, email=email, user_id=current_user.id)
    db.session.add(student)
    db.session.commit()
    flash(f'เพิ่มนักเรียน "{name}" เรียบร้อยแล้ว', 'success')
    return redirect(url_for('students_page'))


@app.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    if student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์ลบนักเรียนนี้', 'error')
        return redirect(url_for('students_page'))
    name = student.name
    db.session.delete(student)
    db.session.commit()
    flash(f'ลบนักเรียน "{name}" เรียบร้อยแล้ว', 'success')
    return redirect(url_for('students_page'))


# ============================================================
# Student Courses
# ============================================================
@app.route('/students/<int:student_id>/courses')
@login_required
def student_courses(student_id):
    student = Student.query.get_or_404(student_id)
    if student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์เข้าถึงข้อมูลนี้', 'error')
        return redirect(url_for('students_page'))
    courses = Course.query.filter_by(student_id=student_id).order_by(
        Course.payment_date.desc(), Course.created_at.desc()
    ).all()
    # คำนวณ duration stats ต่อคอร์ส
    duration_map = {c.id: calc_course_duration(c) for c in courses}
    return render_template('student_courses.html',
        student=student,
        courses=courses,
        duration_map=duration_map,
        today_date=date.today(),
    )


@app.route('/students/<int:student_id>/courses/add', methods=['POST'])
@login_required
def add_course(student_id):
    student = Student.query.get_or_404(student_id)
    if student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์เพิ่มคอร์สให้นักเรียนนี้', 'error')
        return redirect(url_for('students_page'))

    course_name = request.form.get('course_name', '').strip()
    total_sessions = request.form.get('total_sessions', type=int)
    price_per_course = request.form.get('price_per_course', type=float)
    payment_method = request.form.get('payment_method', 'โอนธนาคาร').strip()
    transfer_ref = request.form.get('transfer_ref', '').strip()
    payment_date_str = request.form.get('payment_date', '').strip()
    expiry_date_str = request.form.get('expiry_date', '').strip()

    if not course_name or not total_sessions or price_per_course is None:
        flash('กรุณากรอกข้อมูลให้ครบ', 'error')
        return redirect(url_for('student_courses', student_id=student_id))

    # Parse dates
    try:
        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date() if payment_date_str else date.today()
    except ValueError:
        payment_date = date.today()
        
    expiry_date = None
    if expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    course = Course(
        student_id=student_id,
        course_name=course_name,
        total_sessions=total_sessions,
        price_per_course=price_per_course,
        payment_method=payment_method,
        transfer_ref=transfer_ref,
        payment_date=payment_date,
        expiry_date=expiry_date,
    )
    db.session.add(course)
    db.session.commit()
    flash(f'เพิ่มคอร์ส "{course_name}" ให้ {student.name} เรียบร้อยแล้ว', 'success')
    return redirect(url_for('student_courses', student_id=student_id))


@app.route('/courses/<int:course_id>/edit', methods=['POST'])
@login_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('students_page'))

    course_name = request.form.get('course_name', '').strip()
    total_sessions = request.form.get('total_sessions', type=int)
    price_per_course = request.form.get('price_per_course', type=float)
    payment_method = request.form.get('payment_method', 'โอนธนาคาร').strip()
    transfer_ref = request.form.get('transfer_ref', '').strip()
    payment_date_str = request.form.get('payment_date', '').strip()
    expiry_date_str = request.form.get('expiry_date', '').strip()

    if not course_name or not total_sessions or price_per_course is None:
        flash('กรุณากรอกข้อมูลให้ครบ', 'error')
        return redirect(url_for('student_courses', student_id=course.student_id))

    if total_sessions < course.completed_sessions:
        flash(f'จำนวนครั้งต้องไม่น้อยกว่าที่เรียนไปแล้ว ({course.completed_sessions} ครั้ง)', 'error')
        return redirect(url_for('student_courses', student_id=course.student_id))

    try:
        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date() if payment_date_str else course.payment_date
    except ValueError:
        payment_date = course.payment_date

    expiry_date = None
    if expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    course.course_name = course_name
    course.total_sessions = total_sessions
    course.price_per_course = price_per_course
    course.payment_method = payment_method
    course.transfer_ref = transfer_ref
    course.payment_date = payment_date
    course.expiry_date = expiry_date
    # Re-evaluate completion status
    course.is_completed = course.completed_sessions >= course.total_sessions
    db.session.commit()
    flash(f'แก้ไขคอร์ส "{course_name}" เรียบร้อยแล้ว', 'success')
    return redirect(url_for('student_courses', student_id=course.student_id))


@app.route('/courses/<int:course_id>/delete', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์ลบคอร์สนี้', 'error')
        return redirect(url_for('students_page'))
    student_id = course.student_id
    name = course.course_name
    db.session.delete(course)
    db.session.commit()
    flash(f'ลบคอร์ส "{name}" เรียบร้อยแล้ว', 'success')
    return redirect(url_for('student_courses', student_id=student_id))


# ============================================================
# Course Detail & Session Tracking
# ============================================================
@app.route('/courses/<int:course_id>')
@login_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    if course.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์เข้าถึงข้อมูลนี้', 'error')
        return redirect(url_for('dashboard'))
    sessions = CourseSession.query.filter_by(course_id=course_id).order_by(CourseSession.session_number.desc()).all()
    return render_template('course_detail.html',
        course=course,
        sessions=sessions,
        today=date.today().isoformat(),
        today_date=date.today(),
    )


@app.route('/courses/<int:course_id>/record', methods=['POST'])
@login_required
def record_session(course_id):
    course = Course.query.get_or_404(course_id)
    if course.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('dashboard'))

    if course.is_completed:
        flash('คอร์สนี้เรียนครบแล้ว!', 'warning')
        return redirect(url_for('course_detail', course_id=course_id))

    course.completed_sessions += 1

    # Create session record
    session_date_str = request.form.get('session_date', '')
    is_late_cancel = request.form.get('is_late_cancel') == 'yes'
    
    session_record = CourseSession(
        course_id=course_id,
        session_number=course.completed_sessions,
        session_date=datetime.strptime(session_date_str, '%Y-%m-%d').date() if session_date_str else date.today(),
        session_time=request.form.get('session_time', '').strip(),
        topic=request.form.get('topic', '').strip(),
        issues=request.form.get('issues', '').strip(),
        status='late_cancel' if is_late_cancel else 'present'
    )
    db.session.add(session_record)

    if course.completed_sessions >= course.total_sessions:
        course.is_completed = True
        flash(f'🎉 คอร์ส "{course.course_name}" เรียนครบแล้ว! ({course.completed_sessions}/{course.total_sessions} ครั้ง)', 'warning')
    elif course.remaining_sessions <= 2:
        flash(f'📢 เหลืออีก {course.remaining_sessions} ครั้งก็จะจบคอร์ส!', 'warning')
    else:
        if is_late_cancel:
            flash(f'บันทึกลาล่าช้า/ขาดเรียน (ถูกหัก 1 ครั้ง)', 'warning')
        else:
            flash(f'บันทึกเรียนครั้งที่ {course.completed_sessions} เรียบร้อย', 'success')

    db.session.commit()
    return redirect(url_for('course_detail', course_id=course_id))


@app.route('/courses/<int:course_id>/undo', methods=['POST'])
@login_required
def undo_session(course_id):
    course = Course.query.get_or_404(course_id)
    if course.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('dashboard'))

    if course.completed_sessions > 0:
        latest = CourseSession.query.filter_by(
            course_id=course_id, session_number=course.completed_sessions
        ).first()
        if latest:
            db.session.delete(latest)

        course.completed_sessions -= 1
        course.is_completed = False
        db.session.commit()
        flash('ยกเลิกการบันทึกครั้งล่าสุดเรียบร้อย', 'success')
    else:
        flash('ไม่มีรายการให้ยกเลิก', 'error')

    return redirect(url_for('course_detail', course_id=course_id))


@app.route('/sessions/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_session(session_id):
    session_record = CourseSession.query.get_or_404(session_id)
    course = session_record.course
    if course.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('dashboard'))
    course_id = course.id

    if course.completed_sessions > 0:
        course.completed_sessions -= 1
        course.is_completed = False

    db.session.delete(session_record)
    db.session.commit()
    flash('ลบบันทึกการเรียนเรียบร้อย', 'success')
    return redirect(url_for('course_detail', course_id=course_id))


# ============================================================
# Income — Hourly Lessons
# ============================================================
@app.route('/income')
@login_required
def income_page():
    pf = parse_period_filters()
    date_from = pf['date_from']
    date_to = pf['date_to']

    sid_list = my_student_ids()
    students = my_students().order_by(Student.name).all()

    hourly_lessons = HourlyLesson.query.filter(
        HourlyLesson.student_id.in_(sid_list),
        HourlyLesson.date >= date_from, HourlyLesson.date <= date_to,
    ).order_by(HourlyLesson.date.desc()).all()

    courses = Course.query.filter(
        Course.student_id.in_(sid_list),
        Course.payment_date >= date_from,
        Course.payment_date <= date_to,
    ).order_by(Course.payment_date.desc()).all()

    hourly_income = sum(h.hours * h.rate_per_hour for h in hourly_lessons)
    course_income = sum(c.price_per_course for c in courses)

    return render_template('income.html',
        **pf,
        filter_action=url_for('income_page'),
        students=students,
        hourly_lessons=hourly_lessons,
        courses=courses,
        hourly_income=hourly_income,
        course_income=course_income,
        today=date.today().isoformat(),
    )


@app.route('/income/hourly/add', methods=['POST'])
@login_required
def add_hourly_lesson():
    student_id = request.form.get('student_id', type=int)
    lesson_date = request.form.get('date')
    hours = request.form.get('hours', type=float)
    rate_per_hour = request.form.get('rate_per_hour', type=float)
    note = request.form.get('note', '').strip()
    payment_method = request.form.get('payment_method', 'โอนธนาคาร').strip()
    transfer_ref = request.form.get('transfer_ref', '').strip()

    if not student_id or not hours or not rate_per_hour:
        flash('กรุณากรอกข้อมูลให้ครบ', 'error')
        return redirect(url_for('income_page'))

    # Verify student belongs to current user
    student = Student.query.get_or_404(student_id)
    if student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('income_page'))

    lesson = HourlyLesson(
        student_id=student_id,
        date=datetime.strptime(lesson_date, '%Y-%m-%d').date() if lesson_date else date.today(),
        hours=hours,
        rate_per_hour=rate_per_hour,
        note=note,
        payment_method=payment_method,
        transfer_ref=transfer_ref,
    )
    db.session.add(lesson)
    db.session.commit()

    flash(f'บันทึกสอน {student.name} {hours} ชม. (฿{hours * rate_per_hour:,.0f}) เรียบร้อย', 'success')
    return redirect(url_for('income_page'))


@app.route('/income/hourly/<int:lesson_id>/delete', methods=['POST'])
@login_required
def delete_lesson(lesson_id):
    lesson = HourlyLesson.query.get_or_404(lesson_id)
    if lesson.student.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('income_page'))
    db.session.delete(lesson)
    db.session.commit()
    flash('ลบรายการสอนเรียบร้อย', 'success')
    return redirect(url_for('income_page'))


# ============================================================
# Expenses
# ============================================================
@app.route('/expenses')
@login_required
def expenses_page():
    pf = parse_period_filters()
    date_from = pf['date_from']
    date_to = pf['date_to']

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= date_from, Expense.date <= date_to,
    ).order_by(Expense.date.desc()).all()

    total_expenses = sum(e.amount for e in expenses)

    category_totals = {}
    for e in expenses:
        category_totals[e.category] = category_totals.get(e.category, 0) + e.amount

    return render_template('expenses.html',
        **pf,
        filter_action=url_for('expenses_page'),
        expenses=expenses,
        total_expenses=total_expenses,
        category_totals=category_totals,
        today=date.today().isoformat(),
    )


@app.route('/expenses/add', methods=['POST'])
@login_required
def add_expense():
    category = request.form.get('category', '').strip()
    amount = request.form.get('amount', type=float)
    description = request.form.get('description', '').strip()
    expense_date = request.form.get('date')

    if not category or not amount:
        flash('กรุณากรอกข้อมูลให้ครบ', 'error')
        return redirect(url_for('expenses_page'))

    expense = Expense(
        user_id=current_user.id,
        category=category,
        amount=amount,
        description=description,
        date=datetime.strptime(expense_date, '%Y-%m-%d').date() if expense_date else date.today(),
    )
    db.session.add(expense)
    db.session.commit()
    flash(f'บันทึกค่าใช้จ่าย "{category}" ฿{amount:,.0f} เรียบร้อย', 'success')
    return redirect(url_for('expenses_page'))


@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.user_id != current_user.id:
        flash('ไม่มีสิทธิ์', 'error')
        return redirect(url_for('expenses_page'))
    db.session.delete(expense)
    db.session.commit()
    flash('ลบรายการค่าใช้จ่ายเรียบร้อย', 'success')
    return redirect(url_for('expenses_page'))


# ============================================================
# Reports
# ============================================================
@app.route('/reports')
@login_required
def reports_page():
    pf = parse_period_filters()
    date_from = pf['date_from']
    date_to = pf['date_to']
    student_id = request.args.get('student_id', 0, type=int)

    sid_list = my_student_ids()

    # --- Query hourly lessons ---
    lesson_query = HourlyLesson.query.filter(
        HourlyLesson.student_id.in_(sid_list),
        HourlyLesson.date >= date_from, HourlyLesson.date <= date_to,
    )
    if student_id:
        lesson_query = lesson_query.filter_by(student_id=student_id)
    filtered_lessons = lesson_query.order_by(HourlyLesson.date.desc()).all()

    # --- Query courses ---
    course_query = Course.query.filter(
        Course.student_id.in_(sid_list),
        Course.payment_date >= date_from,
        Course.payment_date <= date_to,
    )
    if student_id:
        course_query = course_query.filter_by(student_id=student_id)
    filtered_courses = course_query.order_by(Course.payment_date.desc()).all()

    # --- Query expenses ---
    expense_query = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= date_from, Expense.date <= date_to,
    )
    filtered_expenses = expense_query.order_by(Expense.date.desc()).all()

    # --- Summaries ---
    hourly_income = sum(h.hours * h.rate_per_hour for h in filtered_lessons)
    course_income = sum(c.price_per_course for c in filtered_courses)
    total_income = hourly_income + course_income
    total_expenses = sum(e.amount for e in filtered_expenses)
    net_profit = total_income - total_expenses

    # --- Build combined transactions list ---
    transactions = []
    for h in filtered_lessons:
        transactions.append({
            'date': h.date,
            'type': 'income',
            'category': 'รายชั่วโมง',
            'description': f'{h.student.name} — {h.hours} ชม. × ฿{h.rate_per_hour:,.0f}',
            'student': h.student.name,
            'amount': h.total_amount,
        })
    for c in filtered_courses:
        transactions.append({
            'date': c.payment_date or date_from,
            'type': 'income',
            'category': 'คอร์ส',
            'description': f'{c.student.name} — {c.course_name}',
            'student': c.student.name,
            'amount': c.price_per_course,
        })
    for e in filtered_expenses:
        transactions.append({
            'date': e.date,
            'type': 'expense',
            'category': e.category,
            'description': e.description or e.category,
            'student': '—',
            'amount': e.amount,
        })

    transactions.sort(key=lambda x: x['date'], reverse=True)

    students = my_students().order_by(Student.name).all()

    return render_template('reports.html',
        **pf,
        filter_action=url_for('reports_page'),
        student_id=student_id,
        filter_students=students,
        students=students,
        hourly_income=hourly_income,
        course_income=course_income,
        total_income=total_income,
        total_expenses=total_expenses,
        net_profit=net_profit,
        transactions=transactions,
    )


# ============================================================
# Course Analytics — Opportunity Cost Summary
# ============================================================
@app.route('/analytics/courses')
@login_required
def course_analytics():
    today = date.today()
    # ใช้ period filter แบบ year หรือ all
    view = request.args.get('view', 'active')  # active | all
    filter_year = request.args.get('year', 0, type=int)

    sid_list = my_student_ids()

    courses_q = Course.query.filter(Course.student_id.in_(sid_list))
    if view == 'active':
        courses_q = courses_q.filter(Course.is_completed == False)
    elif view == 'completed':
        courses_q = courses_q.filter(Course.is_completed == True)
    if filter_year:
        courses_q = courses_q.filter(
            Course.payment_date >= date(filter_year, 1, 1),
            Course.payment_date <= date(filter_year, 12, 31),
        )

    courses = courses_q.order_by(Course.payment_date.desc()).all()

    # คำนวณ duration ทุกคอร์ส
    analytics = []
    total_opp_cost = 0
    total_expected_months = 0
    total_actual_months = 0
    on_time_count = 0

    for c in courses:
        d = calc_course_duration(c)
        if d:
            total_opp_cost += d['opp_cost']
            total_expected_months += d['expected_months']
            total_actual_months += d['actual_months']
            if d['is_on_time']:
                on_time_count += 1
        analytics.append({'course': c, 'duration': d})

    available_years = list(range(2020, today.year + 2))

    return render_template('course_analytics.html',
        analytics=analytics,
        view=view,
        filter_year=filter_year,
        available_years=available_years,
        total_opp_cost=total_opp_cost,
        total_expected_months=round(total_expected_months, 1),
        total_actual_months=round(total_actual_months, 1),
        on_time_count=on_time_count,
        total_courses=len(analytics),
        today=today,
        sessions_per_month=SESSIONS_PER_MONTH,
    )


# ============================================================
# Tax Summary
# ============================================================
@app.route('/tax')
@login_required
def tax_summary_page():
    today = date.today()
    tax_year = request.args.get('tax_year', today.year, type=int)
    extra_deductions = request.args.get('extra_deductions', 0.0, type=float)

    date_from = date(tax_year, 1, 1)
    date_to = date(tax_year, 12, 31)

    sid_list = my_student_ids()

    hourly_lessons = HourlyLesson.query.filter(
        HourlyLesson.student_id.in_(sid_list),
        HourlyLesson.date >= date_from,
        HourlyLesson.date <= date_to,
    ).order_by(HourlyLesson.date).all()

    courses = Course.query.filter(
        Course.student_id.in_(sid_list),
        Course.payment_date >= date_from,
        Course.payment_date <= date_to,
    ).all()

    hourly_total = sum(h.total_amount for h in hourly_lessons)
    course_total = sum(c.price_per_course for c in courses)
    total_income = hourly_total + course_total

    # Payment method breakdown
    payment_breakdown = {}
    for h in hourly_lessons:
        pm = h.payment_method or 'โอนธนาคาร'
        payment_breakdown[pm] = payment_breakdown.get(pm, 0) + h.total_amount
    for c in courses:
        pm = c.payment_method or 'โอนธนาคาร'
        payment_breakdown[pm] = payment_breakdown.get(pm, 0) + c.price_per_course

    # Monthly income breakdown
    monthly_income = {m: 0.0 for m in range(1, 13)}
    for h in hourly_lessons:
        monthly_income[h.date.month] += h.total_amount
    for c in courses:
        m = c.payment_date.month if c.payment_date else 1
        monthly_income[m] += c.price_per_course

    # Tax calculation — Section 40(8) flat 60% expense deduction
    expense_deduction = total_income * 0.60
    personal_deduction = 60_000.0
    total_deductions = expense_deduction + personal_deduction + extra_deductions
    net_income = max(0.0, total_income - total_deductions)
    tax_amount = calculate_tax(net_income)

    available_years = list(range(2020, today.year + 2))

    return render_template('tax_summary.html',
        tax_year=tax_year,
        available_years=available_years,
        total_income=total_income,
        hourly_total=hourly_total,
        course_total=course_total,
        expense_deduction=expense_deduction,
        personal_deduction=personal_deduction,
        extra_deductions=extra_deductions,
        total_deductions=total_deductions,
        net_income=net_income,
        tax_amount=tax_amount,
        payment_breakdown=payment_breakdown,
        monthly_income=monthly_income,
        lesson_count=len(hourly_lessons),
        course_count=len(courses),
        thai_months=THAI_MONTHS,
    )


# ============================================================
# Export Income CSV
# ============================================================
@app.route('/export/income.csv')
@login_required
def export_income_csv():
    import csv
    import io

    tax_year = request.args.get('tax_year', date.today().year, type=int)
    date_from = date(tax_year, 1, 1)
    date_to = date(tax_year, 12, 31)

    sid_list = my_student_ids()

    hourly_lessons = HourlyLesson.query.filter(
        HourlyLesson.student_id.in_(sid_list),
        HourlyLesson.date >= date_from,
        HourlyLesson.date <= date_to,
    ).order_by(HourlyLesson.date).all()

    courses = Course.query.filter(
        Course.student_id.in_(sid_list),
        Course.payment_date >= date_from,
        Course.payment_date <= date_to,
    ).order_by(Course.payment_date).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'วันที่', 'ประเภท', 'ชื่อนักเรียน', 'รายละเอียด',
        'จำนวนชั่วโมง', 'เรท/ชม.', 'ช่องทางรับเงิน',
        'เลขอ้างอิง/สลิป', 'จำนวนเงิน (บาท)'
    ])
    for h in hourly_lessons:
        writer.writerow([
            h.date.strftime('%d/%m/%Y'), 'รายชั่วโมง', h.student.name,
            h.note or '', h.hours, h.rate_per_hour,
            h.payment_method or 'โอนธนาคาร', h.transfer_ref or '',
            h.total_amount,
        ])
    for c in courses:
        writer.writerow([
            c.payment_date.strftime('%d/%m/%Y') if c.payment_date else '',
            'คอร์ส', c.student.name, c.course_name,
            '', '', c.payment_method or 'โอนธนาคาร', c.transfer_ref or '',
            c.price_per_course,
        ])
    total = sum(h.total_amount for h in hourly_lessons) + sum(c.price_per_course for c in courses)
    writer.writerow([])
    writer.writerow(['', '', '', '', '', '', '', 'รวมทั้งหมด', total])

    output.seek(0)
    from flask import Response
    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=income_{tax_year}.csv'}
    )


# ============================================================
# Run
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)

