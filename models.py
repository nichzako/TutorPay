from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    students = db.relationship('Student', backref='owner', lazy=True, cascade='all, delete-orphan')
    expenses = db.relationship('Expense', backref='owner', lazy=True, cascade='all, delete-orphan')


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), default='')
    email = db.Column(db.String(120), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    courses = db.relationship('Course', backref='student', lazy=True, cascade='all, delete-orphan')
    hourly_lessons = db.relationship('HourlyLesson', backref='student', lazy=True, cascade='all, delete-orphan')

    @property
    def enrollment_types(self):
        types = []
        if self.courses:
            types.append('คอร์ส')
        if self.hourly_lessons:
            types.append('รายชั่วโมง')
        return types if types else ['ยังไม่มีการลงทะเบียน']

    @property
    def total_income(self):
        course_income = sum(c.price_per_course for c in self.courses)
        hourly_income = sum(h.hours * h.rate_per_hour for h in self.hourly_lessons)
        return course_income + hourly_income


class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    course_name = db.Column(db.String(200), nullable=False)
    total_sessions = db.Column(db.Integer, nullable=False)
    completed_sessions = db.Column(db.Integer, default=0)
    price_per_course = db.Column(db.Float, nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(50), default='โอนธนาคาร')
    transfer_ref = db.Column(db.String(100), default='')
    payment_date = db.Column(db.Date, nullable=True)   # วันที่รับเงิน (กำหนดเองได้)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    sessions = db.relationship('CourseSession', backref='course', lazy=True,
                               cascade='all, delete-orphan',
                               order_by='CourseSession.session_number.desc()')

    @property
    def progress_percent(self):
        if self.total_sessions == 0:
            return 0
        return round((self.completed_sessions / self.total_sessions) * 100)

    @property
    def remaining_sessions(self):
        return max(0, self.total_sessions - self.completed_sessions)


class CourseSession(db.Model):
    __tablename__ = 'course_sessions'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    session_number = db.Column(db.Integer, nullable=False)
    session_date = db.Column(db.Date, nullable=False, default=date.today)
    session_time = db.Column(db.String(10), default='')
    topic = db.Column(db.String(500), default='')
    issues = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class HourlyLesson(db.Model):
    __tablename__ = 'hourly_lessons'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    hours = db.Column(db.Float, nullable=False)
    rate_per_hour = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(300), default='')
    payment_method = db.Column(db.String(50), default='โอนธนาคาร')
    transfer_ref = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_amount(self):
        return self.hours * self.rate_per_hour


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(300), default='')
    date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
