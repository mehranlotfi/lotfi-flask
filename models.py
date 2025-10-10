from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    national_id = db.Column(db.String(10), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    grade_label = db.Column(db.String(50), nullable=False)

    submitted_at = db.Column(db.DateTime)   # زمان ارسال فرم
    table = db.Column(db.Text)              # ذخیره جدول خروجی الگوریتم
    table_generated_at = db.Column(db.DateTime, nullable=True)  # NEW
    @property
    def password(self):
        return self.password_hash

    @password.setter
    def password(self, hashed):
        self.password_hash = hashed

    def __repr__(self):
        return f"<User {self.name} ({self.grade_label})>"


class Answer(db.Model):
    __tablename__ = "answers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    question_number = db.Column(db.String(50), nullable=False)
    question = db.Column(db.Text, nullable=True)
    answer = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="answers")

    def __repr__(self):
        return f"<Answer q{self.question_number}={self.answer} for user {self.user_id}>"


class ProgramRequest(db.Model):
    __tablename__ = "program_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    program_type = db.Column(db.String(50), nullable=True)   # عادی / اولتیماتوم
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="program_requests")

    def __repr__(self):
        return f"<ProgramRequest {self.id} for user {self.user_id}>"


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Question {self.number}: {self.text}>"
