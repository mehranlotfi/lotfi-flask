from flask import Flask, render_template, request, redirect, session, flash, url_for
from models import db, User, Answer, ProgramRequest, Question
from flask_sqlalchemy import SQLAlchemy
from flask import render_template, request, redirect, url_for, flash
from models import db, User, Answer
import json
from datetime import datetime, timezone, timedelta
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
import os
import random 
from flask_migrate import Migrate
from models import db



app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "instance", "site.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "secret_key"
db.init_app(app)
with app.app_context():
 db.create_all()

migrate = Migrate(app, db)


@app.route("/")
def home():
    return redirect(url_for("signup"))

@app.route("/index", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("wait.html")
# --- GRADE RESULT (جایگزین grade_result فعلی) ---
@app.route("/grade_result")
def grade_result():
    if "uid" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["uid"])
    if not user:
        session.pop("uid", None)
        return redirect(url_for("login"))

    # اگر هنوز جدول ساخته نشده، بساز
    if not user.table:
        answers = {ans.question_number: ans.answer for ans in user.answers}
        table = run_algorithm(answers)
        user.table = json.dumps(table, ensure_ascii=False)
        user.table_generated_at = datetime.now(timezone.utc)
        db.session.commit()
    else:
        try:
            table = json.loads(user.table)
        except Exception:
            table = user.table

    return render_template("grade_result.html", user=user, table=table)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    # گرفتن اطلاعات فرم
    name = request.form.get("name", "").strip()
    national_id = request.form.get("national_id", "").strip()
    password = request.form.get("password", "")
    grade_label = request.form.get("grade_label")  # دقیقا همون name از select

    if not name or not national_id or not password or not grade_label:
        return "همه فیلدها الزامی است.", 400

    # چک کردن کاربر تکراری
    if User.query.filter_by(national_id=national_id).first():
        return "این کد ملی قبلاً ثبت‌نام کرده است.", 400

    # ساخت یوزر جدید
    user = User(
        name=name,
        national_id=national_id,
        password_hash=generate_password_hash(password),
        grade_label=grade_label,   # همون چیزی که از فرم اومده مثل grade_12_tajrobi
    )
    db.session.add(user)
    db.session.commit()

    # ذخیره session
    session["uid"] = user.id 

    
    # اگر جدول آماده بود، مستقیم grade_result
    if user.table:
        return redirect(url_for("grade_result"))
    

    # هدایت به گرید خودش
    return redirect(url_for("grade_page", grade_label=grade_label))


@app.route("/<grade_label>")
def grade_page(grade_label):
    # فقط نام فایل‌هایی که واقعاً گرید هستند
    allowed_grades = [
        "grade_7","grade_8","grade_9","grade_10","grade_11_tajrobi",
        "grade_12_tajrobi","grade_12_riazi","grade_12_ensani",
        "graduate_tajrobi","graduate_riazi","graduate_ensani",
    ]
    if grade_label not in allowed_grades:
        return "صفحه مربوط به این پایه/رشته پیدا نشد.", 404

    return render_template(f"{grade_label}.html")

# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         national_id = request.form["national_id"].strip()
#         password = request.form["password"].strip()

#         user = User.query.filter_by(national_id=national_id, password=password).first()

#         if user:
#             session["uid"] = user.id

#             # اگر کاربر قبلاً پاسخ داده
#             if user.submitted_at:
#                 now = datetime.utcnow()
#                 diff = now - user.submitted_at

#                 # اگر کمتر از 1 دقیقه گذشته → برو به wait
#                 if diff < timedelta(seconds=60):
#                     return redirect(url_for("wait"))

#                 # اگر بین 1 دقیقه تا 7 روز گذشته → برو به grade_result
#                 elif diff < timedelta(days=7):
#                     return redirect(url_for("grade_result"))

#             # در غیر این صورت (کاربر جدید)
#             return redirect(url_for("grade_12_tajrobi"))

#         return render_template("login.html", error="کد ملی یا رمز اشتباه است")

#     return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # اگر POST — پردازش لاگین
    if request.method == "POST":
        national_id = request.form.get("national_id", "").strip()
        password = request.form.get("password", "").strip()

        if not national_id or not password:
            flash("لطفاً همه فیلدها را پر کنید.")
            return redirect(url_for("login"))

        user = User.query.filter_by(national_id=national_id).first()
        if not user:
            flash("کاربری با این کد ملی یافت نشد.")
            return redirect(url_for("login"))

        if not check_password_hash(user.password_hash, password):
            flash("رمز عبور اشتباه است.")
            return redirect(url_for("login"))

        # ثبت session
        session["uid"] = int(user.id)
        now = datetime.now(timezone.utc)

        # 1) اگر جدول قبلاً ساخته شده و کمتر از 7 روز از تولیدش گذشته -> مستقیم نمایش دهید
        gen_at = getattr(user, "table_generated_at", None)
        if user.table and gen_at:
            if gen_at.tzinfo is None:
                gen_at = gen_at.replace(tzinfo=timezone.utc)
            if now - gen_at <= timedelta(days=7):
                try:
                    table = json.loads(user.table) if isinstance(user.table, str) else user.table
                except Exception:
                    table = user.table or {}
                return render_template("grade_result.html", user=user, table=table)

        # 2) اگر پاسخی درج شده ولی هنوز 6 ساعت نگذشته -> نمایش wait با remaining_seconds
        if user.submitted_at:
            submitted_at = user.submitted_at
            if submitted_at.tzinfo is None:
                submitted_at = submitted_at.replace(tzinfo=timezone.utc)

            ready_time = submitted_at + timedelta(hours=6)   # <-- 6 ساعت
            if now < ready_time:
                remaining = ready_time - now
                remaining_seconds = int(remaining.total_seconds())
                hours = remaining_seconds // 3600
                minutes = (remaining_seconds % 3600) // 60
                seconds = remaining_seconds % 60
                return render_template("grade_result.html",
                                       hours=hours, minutes=minutes, seconds=seconds,
                                       remaining_seconds=remaining_seconds)

        # 3) در غیر این صورت (اگر 6 ساعت گذشته یا پاسخی نبود) -> تولید جدول و نمایش result
        answers = {ans.question_number: ans.answer for ans in user.answers}
        table = run_algorithm(answers)
        user.table = json.dumps(table, ensure_ascii=False, default=str)
        user.table_generated_at = now
        db.session.commit()
        return render_template("grade_result.html", user=user, table=table)

    # اگر GET — فقط صفحه لاگین را نمایش بده (بدون دسترسی به user)
    return render_template("login.html")



def map_grade_to_label(grade_fa):
    """
    نگاشت پایه/رشته از ورودی فرم به نام فایل HTML
    """
    mapping = {
        "grade_7": "grade_7",
        "grade_8": "grade_8",
        "grade_9": "grade_9",
        "grade_10_riazi": "grade_10_riazi",
        "grade_10_tajrobi": "grade_10_tajrobi",
        "grade_10_ensani": "grade_10_ensani",
        "grade_10_tajrobi": "grade_11_tajrobi",
        "grade_11_ensani": "grade_11_ensani",
        "grade_11_riazi": "grade_11_riazi",
        "grade_12_tajrobi": "grade_12_tajrobi",
        "grade_12_riazi": "grade_12_riazi",
        "grade_12_ensani": "grade_12_ensani",
        "graduate_tajrobi": "graduate_tajrobi",
        "graduate_riazi": "graduate_riazi",
        "graduate_ensani": "graduate_ensani",
        "grade_result": "grade_result",
    }
    return mapping.get(grade_fa, None)



@app.route("/wait")
def wait():
    if "uid" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["uid"])
    if not user:
        session.pop("uid", None)
        return redirect(url_for("login"))

    if not user.submitted_at:
        flash("شما هنوز پاسخی ارسال نکرده‌اید.", "warning")
        return redirect(url_for("index"))

    submitted_at = user.submitted_at
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    ready_time = submitted_at + timedelta(hours=6)   # ← 6 ساعت
    remaining_seconds = int(max(0, (ready_time - now).total_seconds()))

    if remaining_seconds <= 0:
        # اگر زمان گذشته، مستقیم بفرست grade_result
        return redirect(url_for("grade_result"))

    # محاسبه برای نمایش اولیه (اختیاری)
    hours = remaining_seconds // 3600
    minutes = (remaining_seconds % 3600) // 60
    seconds = remaining_seconds % 60

    # پاس دادن total ثانیه به قالب تا جاوااسکریپت استفاده کنه
    return render_template("wait.html",
                           hours=hours, minutes=minutes, seconds=seconds,
                           remaining_seconds=remaining_seconds)


@app.route("/submit-answers", methods=["POST"])
def submit_answers():
    if "uid" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["uid"])
    if not user:
        session.pop("uid", None)
        return redirect(url_for("login"))

    Answer.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    answers_form = {k: v.strip() for k, v in request.form.items() if v.strip()}
    for key, val in answers_form.items():
        ans = Answer(user_id=user.id, question_number=key, answer=val)
        db.session.add(ans)
    db.session.commit()

    user.submitted_at = datetime.now(timezone.utc)
    user.table = None
    user.table_generated_at = None
    db.session.commit()

    return redirect(url_for("wait"))



def run_algorithm(answers):
    table = {}
 
    q1_answer = answers.get("q1", "")
    topic1 = answers.get("topic_q1", "")
    if q1_answer == "گزینه اول":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه +15 تشریحی"
        table["cell_r3_c1"] = "35 تست"
        table["cell_r4_c1"] = "40تست "
        table["cell_r5_c1"] = "45تست "
        table["cell_r6_c1"] = "35تست "
        table["cell_r7_c1"] = "25تست "
    elif q1_answer == "گزینه دوم":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه + 10 تشریحی"
        table["cell_r3_c1"] = "مطالعه +15 تشریحی"
        table["cell_r4_c1"] = "50تست "
        table["cell_r5_c1"] = "50تست "
        table["cell_r6_c1"] = "40تست "
        table["cell_r7_c1"] = "35تست "
    elif q1_answer=="گزینه سوم":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه"
        table["cell_r3_c1"] = "مطالعه+10 تشریحی"
        table["cell_r4_c1"] = " مطالعه+15 تشریحی"
        table["cell_r5_c1"] = "35 تست"
        table["cell_r6_c1"] = "35تست "
        table["cell_r7_c1"] = "35تست "
        
    elif q1_answer=="گزینه چهارم":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه"
        table["cell_r3_c1"] = "مطالعه+10 تشریحی"
        table["cell_r4_c1"] = "مطالعه+15 تشریحی"
        table["cell_r5_c1"] ="مطالعه+20 تشریحی"
        table["cell_r6_c1"] = "50تست "
        table["cell_r7_c1"] = "50تست "
        
    elif q1_answer=="گزینه پنجم":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه"
        table["cell_r3_c1"] = "مطالعه"
        table["cell_r4_c1"] = " مطالعه "
        table["cell_r5_c1"] = "مطالعه+10 تشریحی"
        table["cell_r6_c1"] = "مطالعه+10 تشریحی"
        table["cell_r7_c1"] = "50تست "
    elif q1_answer=="گزینه ششم":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه"
        table["cell_r3_c1"] = "مطالعه+20 تشریحی"
        table["cell_r4_c1"] = " 30تمرین تشریحی "
        table["cell_r5_c1"] = "30 تمرین تشریحی "
        table["cell_r6_c1"] = "20 تشریحی"
        table["cell_r7_c1"] = "50تست "

    elif q1_answer=="گزینه هفتم":
        table["cell_r1_c1"] = "مرور+50تست"
        table["cell_r2_c1"] = "50 تست"
        table["cell_r3_c1"] = ""
        table["cell_r4_c1"] = ""
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = "ازمون"
        table["cell_r7_c1"] = ""
    elif q1_answer=="گزینه هشتم":
        table["cell_r1_c1"] = "مرور+20 تست"
        table["cell_r2_c1"] = "50 تست"
        table["cell_r3_c1"] = "50 تست"
        table["cell_r4_c1"] = "50 تست"
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = "مرور +ازمون"

    elif q1_answer=="گزینه نهم":
        table["cell_r1_c1"] = "مرور+20 تست"
        table["cell_r2_c1"] = "مرور+20 تست"
        table["cell_r3_c1"] = "40 تست"
        table["cell_r4_c1"] = " 40تست "
        table["cell_r5_c1"] = "40 تست "
        table["cell_r6_c1"] = "ازمون "
        table["cell_r7_c1"] = ""
    elif q1_answer=="گزینه دهم":
        table["cell_r1_c1"] = "مرور+20 تست"
        table["cell_r2_c1"] = " مرور+20 تست"
        table["cell_r3_c1"] = "35تست"
        table["cell_r4_c1"] = "35تست "
        table["cell_r5_c1"] = "35تست "
        table["cell_r6_c1"] = "35تست "
        table["cell_r7_c1"] = "35تست "
    elif q1_answer=="گزینه یازدهم":
        table["cell_r1_c1"] = "50 تست"
        table["cell_r2_c1"] = "50 تست"
        table["cell_r3_c1"] = "45 تست"
        table["cell_r4_c1"] = " 35 تست "
        table["cell_r5_c1"] = "35 تست"
        table["cell_r6_c1"] = "25تست "
        table["cell_r7_c1"] = "25تست "
    elif q1_answer=="گزینه دوازدهم":
        table["cell_r1_c1"] = "70 تست"
        table["cell_r2_c1"] = "70 تست"
        table["cell_r3_c1"] = "50 تست"
        table["cell_r4_c1"] = " 50 تست "
        table["cell_r5_c1"] = "50 تست "
        table["cell_r6_c1"] = "30 تست "
        table["cell_r7_c1"] = "20 تست "

    elif q1_answer=="گزینه سیزدهم":
        table["cell_r1_c1"] = "مرور+10 تشریحی"
        table["cell_r2_c1"] = "مرور+20 تست"
        table["cell_r3_c1"] = ""
        table["cell_r4_c1"] = "20 تست"
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = "مرور+ ازمون"

    elif q1_answer=="گزینه چهاردهم":
        table["cell_r1_c1"] = " ازمون"
        table["cell_r2_c1"] = ""
        table["cell_r3_c1"] = "20 سوال غلط و نزده"
        table["cell_r4_c1"] = ""
        table["cell_r5_c1"] = " ازمون "
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = "20 سوال سخت"
    elif q1_answer=="گزینه پانزدهم":
        table["cell_r1_c1"] = " مطالعه +20 تشریحی"
        table["cell_r2_c1"] = " مطالعه + 20 تشریحی"
        table["cell_r3_c1"] = " مطالعه + 20 تشریحی"
        table["cell_r4_c1"] = " مطالعه + 20 تشریحی"
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = " حل نمونه سوال نهایی"
        table["cell_r7_c1"] = ""
    elif q1_answer=="گزینه شانزدهم":
        table["cell_r1_c1"] = "ویدیو"
        table["cell_r2_c1"] = "ویدیو"
        table["cell_r3_c1"] = "ویدیو +20 تشریحی"
        table["cell_r4_c1"] = "30تست "
        table["cell_r5_c1"] = "30تست "
        table["cell_r6_c1"] = "30تست "
        table["cell_r7_c1"] = "30تست "
    elif q1_answer=="گزینه هفدهتم":
        table["cell_r1_c1"] = "ویدیو"
        table["cell_r2_c1"] = "ویدیو"
        table["cell_r3_c1"] = "ویدیو"
        table["cell_r4_c1"] = "ویدیو +20 تشریحی"
        table["cell_r5_c1"] = "40 تست "
        table["cell_r6_c1"] = "40تست  "
        table["cell_r7_c1"] = "40تست "
    elif q1_answer=="گزینه هیجدهم":
        table["cell_r1_c1"] = "ویدیو"
        table["cell_r2_c1"] = "ویدیو"
        table["cell_r3_c1"] = "ویدیو"
        table["cell_r4_c1"] = " ویدیو +20 تشریحی "
        table["cell_r5_c1"] = " 40 تست "
        table["cell_r6_c1"] = "40تست  "
        table["cell_r7_c1"] = "40تست "
    elif q1_answer=="گزینه نوزدهم":
        table["cell_r1_c1"] = "ویدیو"
        table["cell_r2_c1"] = "ویدیو"
        table["cell_r3_c1"] = "ویدیو"
        table["cell_r4_c1"] = " ویدیو "
        table["cell_r5_c1"] = " ویدیو +20 تشریحی "
        table["cell_r6_c1"] = "ویدیو +20 تشریحی  "
        table["cell_r7_c1"] = "50تست "
    elif q1_answer=="گزینه بیستم":
        table["cell_r1_c1"] = "ویدیو"
        table["cell_r2_c1"] = "ویدیو"
        table["cell_r3_c1"] = "ویدیو"
        table["cell_r4_c1"] = " ویدیو +20 تشریحی"
        table["cell_r5_c1"] = " ویدیو +20 تشریحی"
        table["cell_r6_c1"] = "ویدیو +20 تشریحی "
        table["cell_r7_c1"] = "ویدیو +20 تشریحی"

    elif q1_answer=="گزینه بیست و یک":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه"
        table["cell_r3_c1"] = ""
        table["cell_r4_c1"] = ""
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = ""

    elif q1_answer=="گزینه بیست و دو":
        table["cell_r1_c1"] = "مطالعه"
        table["cell_r2_c1"] = "مطالعه"
        table["cell_r3_c1"] = "مطالعه"
        table["cell_r4_c1"] = "مطالعه"
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = ""

    elif q1_answer=="گزینه بیست و سه":
        table["cell_r1_c1"] = "مطالعه تشریحی و 10 سوال"
        table["cell_r2_c1"] = "مطالعه تشریحی و 10 سوال"
        table["cell_r3_c1"] = ""
        table["cell_r4_c1"] = ""
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = ""

    elif q1_answer=="گزینه بیست و چهار":
        table["cell_r1_c1"] =  "مطالعه تشریحی و 10 سوال"
        table["cell_r2_c1"] =  "مطالعه تشریحی و 10 سوال"
        table["cell_r3_c1"] =  "مطالعه تشریحی و 10 سوال"
        table["cell_r4_c1"] =  "مطالعه تشریحی و 10 سوال"
        table["cell_r5_c1"] = ""
        table["cell_r6_c1"] = ""
        table["cell_r7_c1"] = ""




    if topic1:
       for key, val in table.items():
        if key.endswith("_c1") and val:  # فقط ستون سوال 1
            table[key] = f"{val} - ({topic1})"


# بعد از اختصاص مقادیر q10


    q12_answer = answers.get("q12", "")
    topic12 = answers.get("topic_q12", "")
    if q12_answer == "گزینه اول":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "30 تست"
        table["cell_r4_c2"] = "45تست "
        table["cell_r5_c2"] = "45تست "
        table["cell_r6_c2"] = "50تست "
        table["cell_r7_c2"] = "50تست "
    elif q12_answer == "گزینه دوم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = "30تست "
        table["cell_r5_c2"] = "40تست "
        table["cell_r6_c2"] = "45تست "
        table["cell_r7_c2"] = "50تست "

    elif q12_answer=="گزینه سوم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = " مطالعه "
        table["cell_r5_c2"] = "30تست "
        table["cell_r6_c2"] = "40تست "
        table["cell_r7_c2"] = "50تست "
        
    elif q12_answer=="گزینه چهارم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = " مطالعه "
        table["cell_r5_c2"] = "مطالعه "
        table["cell_r6_c2"] = "30تست "
        table["cell_r7_c2"] = "40تست "
        
    elif q12_answer=="گزینه پنجم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = " مطالعه "
        table["cell_r5_c2"] = "مطالعه "
        table["cell_r6_c2"] = "مطالعه "
        table["cell_r7_c2"] = "50تست "
    elif q12_answer=="گزینه ششم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = " 20تمرین تشریحی "
        table["cell_r5_c2"] = "20 تمرین تشریحی "
        table["cell_r6_c2"] = " 20تمرین تشریحی "
        table["cell_r7_c2"] = " 20تمرین تشریحی "

    elif q12_answer=="گزینه هفتم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = " مطالعه "
        table["cell_r5_c2"] = "مطالعه "
        table["cell_r6_c2"] = "30 تست "
        table["cell_r7_c2"] = "40 تست "
    elif q12_answer=="گزینه هشتم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "مطالعه"
        table["cell_r4_c2"] = " 50 تست "
        table["cell_r5_c2"] = "50 تست "
        table["cell_r6_c2"] = "50 تست "
        table["cell_r7_c2"] = "50تست "

    elif q12_answer=="گزینه نهم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "مطالعه"
        table["cell_r3_c2"] = "30تست"
        table["cell_r4_c2"] = " 30تست "
        table["cell_r5_c2"] = "40تست "
        table["cell_r6_c2"] = "40تست "
        table["cell_r7_c2"] = "50تست "
    elif q12_answer=="گزینه دهم":
        table["cell_r1_c2"] = "مطالعه"
        table["cell_r2_c2"] = "30 تست"
        table["cell_r3_c2"] = "35تست"
        table["cell_r4_c2"] = " 45تست "
        table["cell_r5_c2"] = "45تست "
        table["cell_r6_c2"] = "45تست "
        table["cell_r7_c2"] = "50تست "
    elif q12_answer=="گزینه یازدهم":
        table["cell_r1_c2"] = "30 تست"
        table["cell_r2_c2"] = "30 تست"
        table["cell_r3_c2"] = "45تست"
        table["cell_r4_c2"] = " 45تست "
        table["cell_r5_c2"] = "50تست "
        table["cell_r6_c2"] = "50تست "
        table["cell_r7_c2"] = "50تست "
    elif q12_answer=="گزینه دوازدهم":
        table["cell_r1_c2"] = "50 تست"
        table["cell_r2_c2"] = "50 تست"
        table["cell_r3_c2"] = "50 تست"
        table["cell_r4_c2"] = " 50 تست "
        table["cell_r5_c2"] = "50 تست "
        table["cell_r6_c2"] = "50 تست "
        table["cell_r7_c2"] = "50 تست "

    elif q12_answer=="گزینه سیزدهم":
        table["cell_r1_c2"] = " مرور"
        table["cell_r2_c2"] = " 15 تست"
        table["cell_r3_c2"] = " مرور"
        table["cell_r4_c2"] = "  15 تست "
        table["cell_r5_c2"] = " مرور "
        table["cell_r6_c2"] = ""
        table["cell_r7_c2"] = ""

    elif q12_answer=="گزینه چهاردهم":
        table["cell_r1_c2"] = " ازمون"
        table["cell_r2_c2"] = ""
        table["cell_r3_c2"] = ""
        table["cell_r4_c2"] = ""
        table["cell_r5_c2"] = " ازمون "
        table["cell_r6_c2"] = ""
        table["cell_r7_c2"] = ""
    elif q12_answer=="گزینه پانزدهم":
        table["cell_r1_c2"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c2"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c2"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c2"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c2"] = ""
        table["cell_r6_c2"] = ""
        table["cell_r7_c2"] = ""
    elif q12_answer=="گزینه شانزدهم":
        table["cell_r1_c2"] = "ویدیو"
        table["cell_r2_c2"] = "ویدیو"
        table["cell_r3_c2"] = " ویدیو"
        table["cell_r4_c2"] = "30تست "
        table["cell_r5_c2"] = "30تست "
        table["cell_r6_c2"] = "30تست "
    elif q12_answer=="گزینه هفدهتم":
        table["cell_r1_c2"] = "ویدیو"
        table["cell_r2_c2"] = "ویدیو"
        table["cell_r3_c2"] = "ویدیو"
        table["cell_r4_c2"] = " ویدیو "
        table["cell_r5_c2"] = "30 تست "
        table["cell_r6_c2"] = "30تست  "
        table["cell_r7_c2"] = "30تست "
    elif q12_answer=="گزینه هیجدهم":
        table["cell_r1_2"] = "ویدیو"
        table["cell_r2_c2"] = "ویدیو"
        table["cell_r3_c2"] = "ویدیو"
        table["cell_r4_c2"] = " ویدیو "
        table["cell_r5_c2"] = " ویدیو "
        table["cell_r6_c2"] = "30تست  "
        table["cell_r7_c2"] = "30تست "
    elif q12_answer=="گزینه نوزدهم":
        table["cell_r1_c2"] = "ویدیو"
        table["cell_r2_c2"] = "ویدیو"
        table["cell_r3_c2"] = "ویدیو"
        table["cell_r4_c2"] = " ویدیو "
        table["cell_r5_c2"] = " ویدیو "
        table["cell_r6_c2"] = "ویدیو  "
        table["cell_r7_c2"] = "30تست "
    elif q12_answer=="گزینه بیستم":
        table["cell_r1_c2"] = "ویدیو"
        table["cell_r2_c2"] = "ویدیو"
        table["cell_r3_c2"] = "ویدیو"
        table["cell_r4_c2"] = " ویدیو "
        table["cell_r5_c2"] = " ویدیو "
        table["cell_r6_c2"] = "ویدیو  "
        table["cell_r7_c2"] = "ویدیو "
    if topic12:
     for key, val in table.items():
        if key.endswith("_c2") and val:
            table[key] = f"{val} - ({topic12})"


    q2_answer = answers.get("q2", "")
    topic2 = answers.get("topic_q2", "")
    if q2_answer == "گزینه اول":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "30 تست"
        table["cell_r4_c3"] = "30تست "
        table["cell_r5_c3"] = "30تست "
        table["cell_r6_c3"] = "30تست "
        table["cell_r7_c3"] = "30تست "
       
    elif q2_answer == "گزینه دوم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = "30تست "
        table["cell_r5_c3"] = "30تست "
        table["cell_r6_c3"] = "30تست "
        table["cell_r7_c3"] = "30تست "
    elif q2_answer=="گزینه سوم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = " مطالعه "
        table["cell_r5_c3"] = "30تست "
        table["cell_r6_c3"] = "30تست "
        table["cell_r7_c3"] = "30تست "
        
    elif q2_answer=="گزینه چهارم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = " مطالعه "
        table["cell_r5_c3"] = "مطالعه "
        table["cell_r6_c3"] = "30تست "
        table["cell_r7_c3"] = "30تست "
        
    elif q2_answer=="گزینه پنجم": 
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = " مطالعه "
        table["cell_r5_c3"] = "مطالعه "
        table["cell_r6_c3"] = "مطالعه "
        table["cell_r7_c3"] = "30تست "
    elif q2_answer=="گزینه ششم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = " 20تمرین تشریحی "
        table["cell_r5_c3"] = "20 تمرین تشریحی "
        table["cell_r6_c3"] = "20 تمرین تشریحی "
        table["cell_r7_c3"] = "20 تمرین تشریحی "

    elif q2_answer=="گزینه هفتم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = " مطالعه "
        table["cell_r5_c3"] = "مطالعه "
        table["cell_r6_c3"] = "25 تست "
        table["cell_r7_c3"] = "25 تست "
    elif q2_answer=="گزینه هشتم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "مطالعه"
        table["cell_r4_c3"] = " 25 تست "
        table["cell_r5_c3"] = "25 تست "
        table["cell_r6_c3"] = "25 تست "
        table["cell_r7_c3"] = "25تست "

    elif q2_answer=="گزینه نهم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "مطالعه"
        table["cell_r3_c3"] = "25تست"
        table["cell_r4_c3"] = " 25تست "
        table["cell_r5_c3"] = "25تست "
        table["cell_r6_c3"] = "25تست "
        table["cell_r7_c3"] = "25تست "
    elif q2_answer=="گزینه دهم":
        table["cell_r1_c3"] = "مطالعه"
        table["cell_r2_c3"] = "25 تست"
        table["cell_r3_c3"] = "25تست"
        table["cell_r4_c3"] = " 25تست "
        table["cell_r5_c3"] = "25تست "
        table["cell_r6_c3"] = "25تست "
        table["cell_r7_c3"] = "25تست "
    elif q2_answer=="گزینه یازدهم":
        table["cell_r1_c3"] = "25 تست"
        table["cell_r2_c3"] = "25 تست"
        table["cell_r3_c3"] = "25تست"
        table["cell_r4_c3"] = " 25تست "
        table["cell_r5_c3"] = "25تست "
        table["cell_r6_c3"] = "25تست "
        table["cell_r7_c3"] = "25تست "
    elif q2_answer=="گزینه دوازدهم":
        table["cell_r1_c3"] = "50 تست"
        table["cell_r2_c3"] = "50 تست"
        table["cell_r3_c3"] = "50 تست"
        table["cell_r4_c3"] = " 50 تست "
        table["cell_r5_c3"] = "50 تست "
        table["cell_r6_c3"] = "50 تست "
        table["cell_r7_c3"] = "50 تست "

    elif q2_answer=="گزینه سیزدهم":
        table["cell_r1_c3"] = " مرور"
        table["cell_r2_c3"] = " 15 تست"
        table["cell_r3_c3"] = " مرور"
        table["cell_r4_c3"] = "  15 تست "
        table["cell_r5_c3"] = " مرور "
        table["cell_r6_c3"] = ""
        table["cell_r7_c3"] = ""

    elif q2_answer=="گزینه چهاردهم":
        table["cell_r1_c3"] = " ازمون"
        table["cell_r2_c3"] = ""
        table["cell_r3_c3"] = ""
        table["cell_r4_c3"] = ""
        table["cell_r5_c3"] = " ازمون "
        table["cell_r6_c3"] = "  "
        table["cell_r7_c3"] = "  "
    elif q2_answer=="گزینه پانزدهم":
        table["cell_r1_c3"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c3"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c3"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c3"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c3"] = ""
        table["cell_r6_c3"] = ""
        table["cell_r7_c3"] = ""
    elif q2_answer=="گزینه شانزدهم":
        table["cell_r1_c3"] = "ویدیو"
        table["cell_r2_c3"] = "ویدیو"
        table["cell_r3_c3"] = " ویدیو"
        table["cell_r4_c3"] = "30تست "
        table["cell_r5_c3"] = "30تست "
        table["cell_r6_c3"] = "30تست "
    elif q2_answer=="گزینه هفدهتم":
        table["cell_r1_c3"] = "ویدیو"
        table["cell_r2_c3"] = "ویدیو"
        table["cell_r3_c3"] = "ویدیو"
        table["cell_r4_c3"] = " ویدیو "
        table["cell_r5_c3"] = "30 تست "
        table["cell_r6_c3"] = "30تست  "
        table["cell_r7_c3"] = "30تست "
    elif q2_answer=="گزینه هیجدهم":
        table["cell_r1_c3"] = "ویدیو"
        table["cell_r2_c3"] = "ویدیو"
        table["cell_r3_c3"] = "ویدیو"
        table["cell_r4_c3"] = " ویدیو "
        table["cell_r5_c3"] = " ویدیو "
        table["cell_r6_c3"] = "30تست  "
        table["cell_r7_c3"] = "30تست "
    elif q2_answer=="گزینه نوزدهم":
        table["cell_r1_c3"] = "ویدیو"
        table["cell_r2_c3"] = "ویدیو"
        table["cell_r3_c3"] = "ویدیو"
        table["cell_r4_c3"] = " ویدیو "
        table["cell_r5_c3"] = " ویدیو "
        table["cell_r6_c3"] = "ویدیو  "
        table["cell_r7_c3"] = "30تست "
    elif q2_answer=="گزینه بیستم":
        table["cell_r1_c3"] = "ویدیو"
        table["cell_r2_c3"] = "ویدیو"
        table["cell_r3_c3"] = "ویدیو"
        table["cell_r4_c3"] = " ویدیو "
        table["cell_r5_c3"] = " ویدیو "
        table["cell_r6_c3"] = "ویدیو  "
        table["cell_r7_c3"] = "ویدیو "
    if topic2:
     for key, val in table.items():
        if key.endswith("_c3") and val:
            table[key] = f"{val} - ({topic2})"





    q22_answer = answers.get("q22", "")
    topic22 = answers.get("topic_q22", "")
    if q22_answer == "گزینه اول":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "30 تست"
        table["cell_r4_c4"] = "30تست "
        table["cell_r5_c4"] = "30تست "
        table["cell_r6_c4"] = "30تست "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer == "گزینه دوم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = "30تست "
        table["cell_r5_c4"] = "30تست "
        table["cell_r6_c4"] = "30تست "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer=="گزینه سوم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = " مطالعه "
        table["cell_r5_c4"] = "30تست "
        table["cell_r6_c4"] = "30تست "
        table["cell_r7_c4"] = "30تست "
        
    elif q22_answer=="گزینه چهارم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = " مطالعه "
        table["cell_r5_c4"] = "مطالعه "
        table["cell_r6_c4"] = "30تست "
        table["cell_r7_c4"] = "30تست "
        
    elif q22_answer=="گزینه پنجم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = " مطالعه "
        table["cell_r5_c4"] = "مطالعه "
        table["cell_r6_c4"] = "مطالعه "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer=="گزینه ششم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = " 20تمرین تشریحی "
        table["cell_r5_c4"] = "20 تمرین تشریحی "
        table["cell_r6_c4"] = "20 تمرین تشریحی "
        table["cell_r7_c4"] = "20 تمرین تشریحی "

    elif q22_answer=="گزینه هفتم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = " مطالعه "
        table["cell_r5_c4"] = "مطالعه "
        table["cell_r6_c4"] = "25 تست "
        table["cell_r7_c4"] = "25 تست "
    elif q22_answer=="گزینه هشتم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "مطالعه"
        table["cell_r4_c4"] = " 25 تست "
        table["cell_r5_c4"] = "25 تست "
        table["cell_r6_c4"] = "25 تست "
        table["cell_r7_c4"] = "25تست "

    elif q22_answer=="گزینه نهم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "مطالعه"
        table["cell_r3_c4"] = "25تست"
        table["cell_r4_c4"] = " 25تست "
        table["cell_r5_c4"] = "25تست "
        table["cell_r6_c4"] = "25تست "
        table["cell_r7_c4"] = "25تست "
    elif q22_answer=="گزینه دهم":
        table["cell_r1_c4"] = "مطالعه"
        table["cell_r2_c4"] = "25 تست"
        table["cell_r3_c4"] = "25تست"
        table["cell_r4_c4"] = " 25تست "
        table["cell_r5_c4"] = "25تست "
        table["cell_r6_c4"] = "25تست "
        table["cell_r7_c4"] = "25تست "
    elif q22_answer=="گزینه یازدهم":
        table["cell_r1_c4"] = "25 تست"
        table["cell_r2_c4"] = "25 تست"
        table["cell_r3_c4"] = "25تست"
        table["cell_r4_c4"] = " 25تست "
        table["cell_r5_c4"] = "25تست "
        table["cell_r6_c4"] = "25تست "
        table["cell_r7_c4"] = "25تست "
    elif q22_answer=="گزینه دوازدهم":
        table["cell_r1_c4"] = "50 تست"
        table["cell_r2_c4"] = "50 تست"
        table["cell_r3_c4"] = "50 تست"
        table["cell_r4_c4"] = " 50 تست "
        table["cell_r5_c4"] = "50 تست "
        table["cell_r6_c4"] = "50 تست "
        table["cell_r7_c4"] = "50 تست "

    elif q22_answer=="گزینه سیزدهم":
        table["cell_r1_c4"] = " مرور"
        table["cell_r2_c4"] = " 15 تست"
        table["cell_r3_c4"] = " مرور"
        table["cell_r4_c4"] = "  15 تست "
        table["cell_r5_c4"] = " مرور "
        table["cell_r6_c4"] = ""
        table["cell_r7_c4"] = ""

    elif q22_answer=="گزینه چهاردهم":
        table["cell_r1_c4"] = " ازمون"
        table["cell_r2_c4"] = ""
        table["cell_r3_c4"] = ""
        table["cell_r4_c4"] = ""
        table["cell_r5_c4"] = " ازمون "
        table["cell_r6_c4"] = ""
        table["cell_r7_c4"] = ""
    elif q22_answer=="گزینه پانزدهم":
        table["cell_r1_c4"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c4"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c4"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c4"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c4"] = ""
        table["cell_r6_c4"] = ""
        table["cell_r7_c4"] = ""
    elif q22_answer=="گزینه شانزدهم":
        table["cell_r1_c4"] = "ویدیو"
        table["cell_r2_c4"] = "ویدیو"
        table["cell_r3_c4"] = " ویدیو"
        table["cell_r4_c4"] = "30تست "
        table["cell_r5_c4"] = "30تست "
        table["cell_r6_c4"] = "30تست "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer=="گزینه هفدهتم":
        table["cell_r1_c4"] = "ویدیو"
        table["cell_r2_c4"] = "ویدیو"
        table["cell_r3_c4"] = "ویدیو"
        table["cell_r4_c4"] = " ویدیو "
        table["cell_r5_c4"] = "30 تست "
        table["cell_r6_c4"] = "30تست  "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer=="گزینه هیجدهم":
        table["cell_r1_c4"] = "ویدیو"
        table["cell_r2_c4"] = "ویدیو"
        table["cell_r3_c4"] = "ویدیو"
        table["cell_r4_c4"] = " ویدیو "
        table["cell_r5_c4"] = " ویدیو "
        table["cell_r6_c4"] = "30تست  "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer=="گزینه نوزدهم":
        table["cell_r1_c4"] = "ویدیو"
        table["cell_r2_c4"] = "ویدیو"
        table["cell_r3_c4"] = "ویدیو"
        table["cell_r4_c4"] = " ویدیو "
        table["cell_r5_c4"] = " ویدیو "
        table["cell_r6_c4"] = "ویدیو  "
        table["cell_r7_c4"] = "30تست "
    elif q22_answer=="گزینه بیستم":
        table["cell_r1_c4"] = "ویدیو"
        table["cell_r2_c4"] = "ویدیو"
        table["cell_r3_c4"] = "ویدیو"
        table["cell_r4_c4"] = " ویدیو "
        table["cell_r5_c4"] = " ویدیو "
        table["cell_r6_c4"] = "ویدیو  "
        table["cell_r7_c4"] = "ویدیو "
    if topic22:
     for key, val in table.items():
        if key.endswith("_c4") and val:
            table[key] = f"{val} - ({topic22})"

    q3_answer = answers.get("q3", "")
    topic3 = answers.get("topic_q3", "")
    if q3_answer == "گزینه اول":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "30 تست"
        table["cell_r4_c5"] = "30تست "
        table["cell_r5_c5"] = "30تست "
        table["cell_r6_c5"] = "30تست "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer == "گزینه دوم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = "30تست "
        table["cell_r5_c5"] = "30تست "
        table["cell_r6_c5"] = "30تست "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer=="گزینه سوم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = " مطالعه "
        table["cell_r5_c5"] = "30تست "
        table["cell_r6_c5"] = "30تست "
        table["cell_r7_c5"] = "30تست "
        
    elif q3_answer=="گزینه چهارم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = " مطالعه "
        table["cell_r5_c5"] = "مطالعه "
        table["cell_r6_c5"] = "30تست "
        table["cell_r7_c5"] = "30تست "
        
    elif q3_answer=="گزینه پنجم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = " مطالعه "
        table["cell_r5_c5"] = "مطالعه "
        table["cell_r6_c5"] = "مطالعه "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer=="گزینه ششم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = " 20تمرین تشریحی "
        table["cell_r5_c5"] = "20 تمرین تشریحی "
        table["cell_r6_c5"] = "20 تمرین تشریحی "
        table["cell_r7_c5"] = "20 تمرین تشریحی "
    elif q3_answer=="گزینه هفتم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = " مطالعه "
        table["cell_r5_c5"] = "مطالعه "
        table["cell_r6_c5"] = "25 تست "
        table["cell_r7_c5"] = "25 تست "
    elif q3_answer=="گزینه هشتم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "مطالعه"
        table["cell_r4_c5"] = " 25 تست "
        table["cell_r5_c5"] = "25 تست "
        table["cell_r6_c5"] = "25 تست "
        table["cell_r7_c5"] = "25تست "

    elif q3_answer=="گزینه نهم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "مطالعه"
        table["cell_r3_c5"] = "25تست"
        table["cell_r4_c5"] = " 25تست "
        table["cell_r5_c5"] = "25تست "
        table["cell_r6_c5"] = "25تست "
        table["cell_r7_c5"] = "25تست "
    elif q3_answer=="گزینه دهم":
        table["cell_r1_c5"] = "مطالعه"
        table["cell_r2_c5"] = "25 تست"
        table["cell_r3_c5"] = "25تست"
        table["cell_r4_c5"] = " 25تست "
        table["cell_r5_c5"] = "25تست "
        table["cell_r6_c5"] = "25تست "
        table["cell_r7_c5"] = "25تست "
    elif q3_answer=="گزینه یازدهم":
        table["cell_r1_c5"] = "25 تست"
        table["cell_r2_c5"] = "25 تست"
        table["cell_r3_c5"] = "25تست"
        table["cell_r4_c5"] = " 25تست "
        table["cell_r5_c5"] = "25تست "
        table["cell_r6_c5"] = "25تست "
        table["cell_r7_c5"] = "25تست "
    elif q3_answer=="گزینه دوازدهم":
        table["cell_r1_c5"] = "50 تست"
        table["cell_r2_c5"] = "50 تست"
        table["cell_r3_c5"] = "50 تست"
        table["cell_r4_c5"] = " 50 تست "
        table["cell_r5_c5"] = "50 تست "
        table["cell_r6_c5"] = "50 تست "
        table["cell_r7_c5"] = "50 تست "

    elif q3_answer=="گزینه سیزدهم":
        table["cell_r1_c5"] = " مرور"
        table["cell_r2_c5"] = " 15 تست"
        table["cell_r3_c5"] = " مرور"
        table["cell_r4_c5"] = "  15 تست "
        table["cell_r5_c5"] = " مرور "
        table["cell_r6_c5"] = ""
        table["cell_r7_c5"] = ""

    elif q3_answer=="گزینه چهاردهم":
        table["cell_r1_c5"] = " ازمون"
        table["cell_r2_c5"] = ""
        table["cell_r3_c5"] = ""
        table["cell_r4_c5"] = ""
        table["cell_r5_c5"] = " ازمون "
        table["cell_r6_c5"] = ""
        table["cell_r7_c5"] = ""
    elif q3_answer=="گزینه پانزدهم":
        table["cell_r1_c5"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c5"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c5"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c5"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c5"] = ""
        table["cell_r6_c5"] = ""
        table["cell_r7_c5"] = ""
    elif q3_answer=="گزینه شانزدهم":
        table["cell_r1_c5"] = "ویدیو"
        table["cell_r2_c5"] = "ویدیو"
        table["cell_r3_c5"] = " ویدیو"
        table["cell_r4_c5"] = "30تست "
        table["cell_r5_c5"] = "30تست "
        table["cell_r6_c5"] = "30تست "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer=="گزینه هفدهتم":
        table["cell_r1_c5"] = "ویدیو"
        table["cell_r2_c5"] = "ویدیو"
        table["cell_r3_c5"] = "ویدیو"
        table["cell_r4_c5"] = " ویدیو "
        table["cell_r5_c5"] = "30 تست "
        table["cell_r6_c5"] = "30تست  "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer=="گزینه هیجدهم":
        table["cell_r1_c5"] = "ویدیو"
        table["cell_r2_c5"] = "ویدیو"
        table["cell_r3_c5"] = "ویدیو"
        table["cell_r4_c5"] = " ویدیو "
        table["cell_r5_c5"] = " ویدیو "
        table["cell_r6_c5"] = "30تست  "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer=="گزینه نوزدهم":
        table["cell_r1_c5"] = "ویدیو"
        table["cell_r2_c5"] = "ویدیو"
        table["cell_r3_c5"] = "ویدیو"
        table["cell_r4_c5"] = " ویدیو "
        table["cell_r5_c5"] = " ویدیو "
        table["cell_r6_c5"] = "ویدیو  "
        table["cell_r7_c5"] = "30تست "
    elif q3_answer=="گزینه بیستم":
        table["cell_r1_c5"] = "ویدیو"
        table["cell_r2_c5"] = "ویدیو"
        table["cell_r3_c5"] = "ویدیو"
        table["cell_r4_c5"] = " ویدیو "
        table["cell_r5_c5"] = " ویدیو "
        table["cell_r6_c5"] = "ویدیو  "
        table["cell_r7_c5"] = "ویدیو "
    if topic3:
     for key, val in table.items():
        if key.endswith("_c5") and val:
            table[key] = f"{val} - ({topic3})"


    q32_answer = answers.get("q32", "")
    topic32 = answers.get("topic_q32", "")
    if q32_answer == "گزینه اول":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "30 تست"
        table["cell_r4_c6"] = "30تست "
        table["cell_r5_c6"] = "30تست "
        table["cell_r6_c6"] = "30تست "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer == "گزینه دوم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = "30تست "
        table["cell_r5_c6"] = "30تست "
        table["cell_r6_c6"] = "30تست "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer=="گزینه سوم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = " مطالعه "
        table["cell_r5_c6"] = "30تست "
        table["cell_r6_c"] = "30تست "
        table["cell_r7_c6"] = "30تست "
        
    elif q32_answer=="گزینه چهارم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = " مطالعه "
        table["cell_r5_c6"] = "مطالعه "
        table["cell_r6_c6"] = "30تست "
        table["cell_r6_c6"] = "30تست "
        
    elif q32_answer=="گزینه پنجم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = " مطالعه "
        table["cell_r5_c6"] = "مطالعه "
        table["cell_r6_c6"] = "مطالعه "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer=="گزینه ششم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = " 20تمرین تشریحی "
        table["cell_r5_c6"] = "20 تمرین تشریحی "
        table["cell_r6_c6"] = "20 تمرین تشریحی "
        table["cell_r7_c6"] = "20 تمرین تشریحی "

    elif q32_answer=="گزینه هفتم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = " مطالعه "
        table["cell_r5_c6"] = "مطالعه "
        table["cell_r6_c6"] = "25 تست "
        table["cell_r7_c6"] = "25 تست "
    elif q32_answer=="گزینه هشتم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "مطالعه"
        table["cell_r4_c6"] = " 25 تست "
        table["cell_r5_c6"] = "25 تست "
        table["cell_r6_c6"] = "25 تست "
        table["cell_r7_c6"] = "25تست "

    elif q32_answer=="گزینه نهم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "مطالعه"
        table["cell_r3_c6"] = "25تست"
        table["cell_r4_c6"] = " 25تست "
        table["cell_r5_c6"] = "25تست "
        table["cell_r6_c6"] = "25تست "
        table["cell_r7_c6"] = "25تست "
    elif q32_answer=="گزینه دهم":
        table["cell_r1_c6"] = "مطالعه"
        table["cell_r2_c6"] = "25 تست"
        table["cell_r3_c6"] = "25تست"
        table["cell_r4_c6"] = " 25تست "
        table["cell_r5_c6"] = "25تست "
        table["cell_r6_c6"] = "25تست "
        table["cell_r7_c6"] = "25تست "
    elif q32_answer=="گزینه یازدهم":
        table["cell_r1_c6"] = "25 تست"
        table["cell_r2_c6"] = "25 تست"
        table["cell_r3_c6"] = "25تست"
        table["cell_r4_c6"] = " 25تست "
        table["cell_r5_c6"] = "25تست "
        table["cell_r6_c6"] = "25تست "
        table["cell_r7_c6"] = "25تست "
    elif q32_answer=="گزینه دوازدهم":
        table["cell_r1_c6"] = "50 تست"
        table["cell_r2_c6"] = "50 تست"
        table["cell_r3_c6"] = "50 تست"
        table["cell_r4_c6"] = " 50 تست "
        table["cell_r5_c6"] = "50 تست "
        table["cell_r6_c6"] = "50 تست "
        table["cell_r7_c6"] = "50 تست "
    elif q32_answer=="گزینه سیزدهم":
        table["cell_r1_c6"] = " مرور"
        table["cell_r2_c6"] = " 15 تست"
        table["cell_r3_c6"] = " مرور"
        table["cell_r4_c6"] = "  15 تست "
        table["cell_r5_c6"] = " مرور "
        table["cell_r6_c6"] = ""
        table["cell_r7_c6"] = ""

    elif q32_answer=="گزینه چهاردهم":
        table["cell_r1_c6"] = " ازمون"
        table["cell_r2_c6"] = ""
        table["cell_r3_c6"] = ""
        table["cell_r4_c6"] = ""
        table["cell_r5_c6"] = " ازمون "
        table["cell_r6_c6"] = ""
        table["cell_r7_c6"] = ""
    elif q32_answer=="گزینه پانزدهم":
        table["cell_r1_c6"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c6"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c6"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c6"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c6"] = ""
        table["cell_r6_c6"] = ""
        table["cell_r7_c6"] = ""
    elif q32_answer=="گزینه شانزدهم":
        table["cell_r1_c6"] = "ویدیو"
        table["cell_r2_c6"] = "ویدیو"
        table["cell_r3_c6"] = " ویدیو"
        table["cell_r4_c6"] = "30تست "
        table["cell_r5_c6"] = "30تست "
        table["cell_r6_c6"] = "30تست "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer=="گزینه هفدهتم":
        table["cell_r1_c6"] = "ویدیو"
        table["cell_r2_c6"] = "ویدیو"
        table["cell_r3_c6"] = "ویدیو"
        table["cell_r4_c6"] = " ویدیو "
        table["cell_r5_c6"] = "30 تست "
        table["cell_r6_c6"] = "30تست  "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer=="گزینه هیجدهم":
        table["cell_r1_c6"] = "ویدیو"
        table["cell_r2_c6"] = "ویدیو"
        table["cell_r3_c6"] = "ویدیو"
        table["cell_r4_c6"] = " ویدیو "
        table["cell_r5_c6"] = " ویدیو "
        table["cell_r6_c6"] = "30تست  "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer=="گزینه نوزدهم":
        table["cell_r1_c6"] = "ویدیو"
        table["cell_r2_c6"] = "ویدیو"
        table["cell_r3_c6"] = "ویدیو"
        table["cell_r4_c6"] = " ویدیو "
        table["cell_r5_c6"] = " ویدیو "
        table["cell_r6_c6"] = "ویدیو  "
        table["cell_r7_c6"] = "30تست "
    elif q32_answer=="گزینه بیستم":
        table["cell_r1_c6"] = "ویدیو"
        table["cell_r2_c6"] = "ویدیو"
        table["cell_r3_c6"] = "ویدیو"
        table["cell_r4_c6"] = " ویدیو "
        table["cell_r5_c6"] = " ویدیو "
        table["cell_r6_c6"] = "ویدیو  "
        table["cell_r7_c6"] = "ویدیو "
    if topic32:
     for key, val in table.items():
        if key.endswith("_c6") and val:
            table[key] = f"{val} - ({topic32})"

    q4_answer = answers.get("q4", "")
    topic4 = answers.get("topic_q4", "")
    if q4_answer == "گزینه اول":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "30 تست"
        table["cell_r4_c7"] = "30تست "
        table["cell_r5_c7"] = "30تست "
        table["cell_r6_c7"] = "30تست "
        table["cell_r7_c7"] = "30تست "
        
    elif q4_answer == "گزینه دوم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = "30تست "
        table["cell_r5_c7"] = "30تست "
        table["cell_r6_c7"] = "30تست "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه سوم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = " مطالعه "
        table["cell_r5_c7"] = "30تست "
        table["cell_r6_c7"] = "30تست "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه چهارم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = " مطالعه "
        table["cell_r5_c7"] = "مطالعه "
        table["cell_r6_c7"] = "30تست "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه پنجم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = " مطالعه "
        table["cell_r5_c7"] = "مطالعه "
        table["cell_r6_c7"] = "مطالعه "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه ششم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = " 20تمرین تشریحی "
        table["cell_r5_c7"] = "20 تمرین تشریحی "
        table["cell_r6_c7"] = "20 تمرین تشریحی "
        table["cell_r7_c7"] = "20 تمرین تشریحی "
    elif q4_answer=="گزینه هفتم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = " مطالعه "
        table["cell_r5_c7"] = "مطالعه "
        table["cell_r6_c7"] = "25 تست "
        table["cell_r7_c7"] = "25 تست "
    elif q4_answer=="گزینه هشتم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "مطالعه"
        table["cell_r4_c7"] = " 25 تست "
        table["cell_r5_c7"] = "25 تست "
        table["cell_r6_c7"] = "25 تست "
        table["cell_r7_c7"] = "25تست "

    elif q4_answer=="گزینه نهم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "مطالعه"
        table["cell_r3_c7"] = "25تست"
        table["cell_r4_c7"] = " 25تست "
        table["cell_r5_c7"] = "25تست "
        table["cell_r6_c7"] = "25تست "
        table["cell_r7_c7"] = "25تست "
    elif q4_answer=="گزینه دهم":
        table["cell_r1_c7"] = "مطالعه"
        table["cell_r2_c7"] = "25 تست"
        table["cell_r3_c7"] = "25تست"
        table["cell_r4_c7"] = " 25تست "
        table["cell_r5_c7"] = "25تست "
        table["cell_r6_c7"] = "25تست "
        table["cell_r7_c7"] = "25تست "
    elif q4_answer=="گزینه یازدهم":
        table["cell_r1_c7"] = "25 تست"
        table["cell_r2_c7"] = "25 تست"
        table["cell_r3_c7"] = "25تست"
        table["cell_r4_c7"] = " 25تست "
        table["cell_r5_c7"] = "25تست "
        table["cell_r6_c7"] = "25تست "
        table["cell_r7_c7"] = "25تست "
    elif q4_answer=="گزینه دوازدهم":
        table["cell_r1_c7"] = "50 تست"
        table["cell_r2_c7"] = "50 تست"
        table["cell_r3_c7"] = "50 تست"
        table["cell_r4_c7"] = " 50 تست "
        table["cell_r5_c7"] = "50 تست "
        table["cell_r6_c7"] = "50 تست "
        table["cell_r7_c7"] = "50 تست "

    elif q4_answer=="گزینه سیزدهم":
        table["cell_r1_c7"] = " مرور"
        table["cell_r2_c7"] = " 15 تست"
        table["cell_r3_c7"] = " مرور"
        table["cell_r4_c7"] = "  15 تست "
        table["cell_r5_c7"] = " مرور "
        table["cell_r6_c7"] = ""
        table["cell_r7_c7"] = ""

    elif q4_answer=="گزینه چهاردهم":
        table["cell_r1_c7"] = " ازمون"
        table["cell_r2_c7"] = ""
        table["cell_r3_c7"] = ""
        table["cell_r4_c7"] = ""
        table["cell_r5_c7"] = " ازمون "
        table["cell_r6_c7"] = "  "
        table["cell_r7_c7"] = "  "
    elif q4_answer=="گزینه پانزدهم":
        table["cell_r1_c7"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c7"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c7"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c7"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c7"] = ""
        table["cell_r6_c7"] = ""
        table["cell_r7_c7"] = ""
    elif q4_answer=="گزینه شانزدهم":
        table["cell_r1_c7"] = "ویدیو"
        table["cell_r2_c7"] = "ویدیو"
        table["cell_r3_c7"] = " ویدیو"
        table["cell_r4_c7"] = "30تست "
        table["cell_r5_c7"] = "30تست "
        table["cell_r6_c7"] = "30تست "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه هفدهتم":
        table["cell_r1_c7"] = "ویدیو"
        table["cell_r2_c7"] = "ویدیو"
        table["cell_r3_c7"] = "ویدیو"
        table["cell_r4_c7"] = " ویدیو "
        table["cell_r5_c7"] = "30 تست "
        table["cell_r6_c7"] = "30تست  "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه هیجدهم":
        table["cell_r1_c7"] = "ویدیو"
        table["cell_r2_c7"] = "ویدیو"
        table["cell_r3_c7"] = "ویدیو"
        table["cell_r4_c7"] = " ویدیو "
        table["cell_r5_c7"] = " ویدیو "
        table["cell_r6_c7"] = "30تست  "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه نوزدهم":
        table["cell_r1_c7"] = "ویدیو"
        table["cell_r2_c7"] = "ویدیو"
        table["cell_r3_c7"] = "ویدیو"
        table["cell_r4_c7"] = " ویدیو "
        table["cell_r5_c7"] = " ویدیو "
        table["cell_r6_c7"] = "ویدیو  "
        table["cell_r7_c7"] = "30تست "
    elif q4_answer=="گزینه بیستم":
        table["cell_r1_c7"] = "ویدیو"
        table["cell_r2_c7"] = "ویدیو"
        table["cell_r3_c7"] = "ویدیو"
        table["cell_r4_c7"] = " ویدیو "
        table["cell_r5_c7"] = " ویدیو "
        table["cell_r6_c7"] = "ویدیو  "
        table["cell_r7_c7"] = "ویدیو "
    if topic4:
     for key, val in table.items():
        if key.endswith("_c7") and val:
            table[key] = f"{val} - ({topic4})"


    q42_answer = answers.get("q42", "")
    topic42 = answers.get("topic_q42", "")
    if q42_answer == "گزینه اول":
        table["cell_r1_c8"] = " مطالعه +10 تشریحی"
        table["cell_r2_c8"] = " مطالعه +10 تشریحی"
        table["cell_r3_c8"] = "30 تست"
        table["cell_r4_c8"] = "30تست "
        table["cell_r5_c8"] = "30تست "
        table["cell_r6_c8"] = "30تست "
        table["cell_r7_c8"] = "30تست "
    elif q42_answer == "گزینه دوم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = "30تست "
        table["cell_r5_c8"] = "30تست "
        table["cell_r6_c8"] = "30تست "
        table["cell_r7_c8"] = "30تست "
    elif q42_answer=="گزینه سوم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = " مطالعه "
        table["cell_r5_c8"] = "30تست "
        table["cell_r6_c8"] = "30تست "
        table["cell_r7_c8"] = "30تست "

    elif q42_answer=="گزنه چهارم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = " مطالعه "
        table["cell_r5_c8"] = "مطالعه "
        table["cell_r6_c8"] = "30تست "
        table["cell_r7_c8"] = "30تست "
        
    elif q42_answer=="گزینه پنجم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = " مطالعه "
        table["cell_r5_c8"] = "مطالعه "
        table["cell_r6_c8"] = "مطالعه "
        table["cell_r7_c8"] = "30تست "
    elif q42_answer=="گزینه ششم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = " 20تمرین تشریحی "
        table["cell_r5_c8"] = "20 تمرین تشریحی "
        table["cell_r6_c8"] = "20 تمرین تشریحی "
        table["cell_r7_c8"] = "20 تمرین تشریحی "

    elif q42_answer=="گزینه هفتم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = " مطالعه "
        table["cell_r5_c8"] = "مطالعه "
        table["cell_r6_c8"] = "25 تست "
        table["cell_r7_c8"] = "25 تست "
    elif q42_answer=="گزینه هشتم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "مطالعه"
        table["cell_r4_c8"] = " 25 تست "
        table["cell_r5_c8"] = "25 تست "
        table["cell_r6_c8"] = "25 تست "
        table["cell_r7_c8"] = "25تست "
    elif q42_answer=="گزینه نهم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "مطالعه"
        table["cell_r3_c8"] = "25تست"
        table["cell_r4_c8"] = " 25تست "
        table["cell_r5_c8"] = "25تست "
        table["cell_r6_c8"] = "25تست "
        table["cell_r7_c8"] = "25تست "
    elif q42_answer=="گزینه دهم":
        table["cell_r1_c8"] = "مطالعه"
        table["cell_r2_c8"] = "25 تست"
        table["cell_r3_c8"] = "25تست"
        table["cell_r4_c8"] = " 25تست "
        table["cell_r5_c8"] = "25تست "
        table["cell_r6_c8"] = "25تست "
        table["cell_r7_c8"] = "25تست "
    elif q42_answer=="گزینه یازدهم":
        table["cell_r1_c8"] = "25 تست"
        table["cell_r2_c8"] = "25 تست"
        table["cell_r3_c8"] = "25تست"
        table["cell_r4_c8"] = " 25تست "
        table["cell_r5_c8"] = "25تست "
        table["cell_r6_c8"] = "25تست "
        table["cell_r7_c8"] = "25تست "
    elif q42_answer=="گزینه دوازدهم":
        table["cell_r1_c8"] = "50 تست"
        table["cell_r2_c8"] = "50 تست"
        table["cell_r3_c8"] = "50 تست"
        table["cell_r4_c8"] = " 50 تست "
        table["cell_r5_c8"] = "50 تست "
        table["cell_r6_c8"] = "50 تست "
        table["cell_r7_c8"] = "50 تست "

    elif q42_answer=="گزینه سیزدهم":
        table["cell_r1_c8"] = " مرور"
        table["cell_r2_c8"] = " 15 تست"
        table["cell_r3_c8"] = " مرور"
        table["cell_r4_c8"] = "  15 تست "
        table["cell_r5_c8"] = " مرور "
        table["cell_r6_c8"] = ""
        table["cell_r7_c8"] = ""

    elif q42_answer=="گزینه چهاردهم":
        table["cell_r1_c8"] = " ازمون"
        table["cell_r2_c8"] = ""
        table["cell_r3_c8"] = ""
        table["cell_r4_c8"] = ""
        table["cell_r5_c8"] = " ازمون "
        table["cell_r6_c8"] = ""
        table["cell_r7_c8"] = ""
    elif q42_answer=="گزینه پانزدهم":
        table["cell_r1_c8"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c8"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c8"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c8"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c8"] = ""
        table["cell_r6_c8"] = ""
        table["cell_r7_c8"] = ""
    elif q42_answer=="گزینه شانزدهم":
        table["cell_r1_c8"] = "ویدیو"
        table["cell_r2_c8"] = "ویدیو"
        table["cell_r3_c8"] = " ویدیو"
        table["cell_r4_c8"] = "30تست "
        table["cell_r5_c8"] = "30تست "
        table["cell_r6_c8"] = "30تست "
        table["cell_r7_c8"] = "30تست "
        
    elif q42_answer=="گزینه هفدهتم":
        table["cell_r1_c8"] = "ویدیو"
        table["cell_r2_c8"] = "ویدیو"
        table["cell_r3_c8"] = "ویدیو"
        table["cell_r4_c8"] = " ویدیو "
        table["cell_r5_c"] = "30 تست "
        table["cell_r6_c8"] = "30تست  "
        table["cell_r7_c8"] = "30تست "
    elif q42_answer=="گزینه هیجدهم":
        table["cell_r1_c8"] = "ویدیو"
        table["cell_r2_c8"] = "ویدیو"
        table["cell_r3_c8"] = "ویدیو"
        table["cell_r4_c8"] = " ویدیو "
        table["cell_r5_c8"] = " ویدیو "
        table["cell_r6_c8"] = "30تست  "
        table["cell_r7_c8"] = "30تست "
    elif q42_answer=="گزینه نوزدهم":
        table["cell_r1_c8"] = "ویدیو"
        table["cell_r2_c8"] = "ویدیو"
        table["cell_r3_c8"] = "ویدیو"
        table["cell_r4_c8"] = " ویدیو "
        table["cell_r5_c8"] = " ویدیو "
        table["cell_r6_c8"] = "ویدیو  "
        table["cell_r7_c8"] = "30تست "
    elif q42_answer=="گزینه بیستم":
        table["cell_r1_c8"] = "ویدیو"
        table["cell_r2_c8"] = "ویدیو"
        table["cell_r3_c8"] = "ویدیو"
        table["cell_r4_c8"] = " ویدیو "
        table["cell_r5_c8"] = " ویدیو "
        table["cell_r6_c8"] = "ویدیو  "
        table["cell_r7_c8"] = "ویدیو "

    if topic42:
     for key, val in table.items():
        if key.endswith("_c8") and val:
            table[key] = f"{val} - ({topic42})"


    # q42_answer = answers.get("q42", "")
    # topic42 = answers.get("topic_q42", "")
    # if q42_answer == "گزینه اول":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "30 تست"
    #     table["cell_r4_c8"] = "30تست "
    #     table["cell_r5_c8"] = "30تست "
    #     table["cell_r6_c8"] = "30تست "
    # elif q42_answer == "گزینه دوم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = "30تست "
    #     table["cell_r5_c8"] = "30تست "
    #     table["cell_r6_c8"] = "30تست "
    # elif q42_answer=="گزینه سوم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = " مطالعه "
    #     table["cell_r5_c8"] = "30تست "
    #     table["cell_r6_c8"] = "30تست "

    # elif q42_answer=="گزنه چهارم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = " مطالعه "
    #     table["cell_r5_c8"] = "مطالعه "
    #     table["cell_r6_c8"] = "30تست "
        
    # elif q42_answer=="گزینه پنجم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = " مطالعه "
    #     table["cell_r5_c8"] = "مطالعه "
    #     table["cell_r6_c8"] = "مطالعه "
    #     table["cell_r7_c8"] = "30تست "
    # elif q42_answer=="گزینه ششم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = " 20تمرین تشریحی "
    #     table["cell_r5_c8"] = "20 تمرین تشریحی "

    # elif q42_answer=="گزینه هفتم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = " مطالعه "
    #     table["cell_r5_c8"] = "مطالعه "
    #     table["cell_r6_c8"] = "25 تست "
    #     table["cell_r7_c8"] = "25 تست "
    # elif q42_answer=="گزینه هشتم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "مطالعه"
    #     table["cell_r4_c8"] = " 25 تست "
    #     table["cell_r5_c8"] = "25 تست "
    #     table["cell_r6_c8"] = "25 تست "
    #     table["cell_r7_c8"] = "25تست "
    # elif q42_answer=="گزینه نهم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "مطالعه"
    #     table["cell_r3_c8"] = "25تست"
    #     table["cell_r4_c8"] = " 25تست "
    #     table["cell_r5_c8"] = "25تست "
    #     table["cell_r6_c8"] = "25تست "
    #     table["cell_r7_c8"] = "25تست "
    # elif q42_answer=="گزینه دهم":
    #     table["cell_r1_c8"] = "مطالعه"
    #     table["cell_r2_c8"] = "25 تست"
    #     table["cell_r3_c8"] = "25تست"
    #     table["cell_r4_c8"] = " 25تست "
    #     table["cell_r5_c8"] = "25تست "
    #     table["cell_r6_c8"] = "25تست "
    #     table["cell_r7_c8"] = "25تست "
    # elif q42_answer=="گزینه یازدهم":
    #     table["cell_r1_c8"] = "25 تست"
    #     table["cell_r2_c8"] = "25 تست"
    #     table["cell_r3_c8"] = "25تست"
    #     table["cell_r4_c8"] = " 25تست "
    #     table["cell_r5_c8"] = "25تست "
    #     table["cell_r6_c8"] = "25تست "
    #     table["cell_r7_c8"] = "25تست "
    # elif q42_answer=="گزینه دوازدهم":
    #     table["cell_r1_c8"] = "50 تست"
    #     table["cell_r2_c8"] = "50 تست"
    #     table["cell_r3_c8"] = "50 تست"
    #     table["cell_r4_c8"] = " 50 تست "
    #     table["cell_r5_c8"] = "50 تست "
    #     table["cell_r6_c8"] = "50 تست "
    #     table["cell_r7_c8"] = "50 تست "

    # elif q42_answer=="گزینه سیزدهم":
    #     table["cell_r1_c8"] = " مرور"
    #     table["cell_r2_c8"] = " 15 تست"
    #     table["cell_r3_c8"] = " مرور"
    #     table["cell_r4_c8"] = "  15 تست "
    #     table["cell_r5_c8"] = " مرور "
    #     table["cell_r6_c8"] = "  "
    #     table["cell_r7_c8"] = "  "

    # elif q42_answer=="گزینه چهاردهم":
    #     table["cell_r1_c8"] = " ازمون"
    #     table["cell_r2_c8"] = "  "
    #     table["cell_r3_c8"] = " "
    #     table["cell_r4_c8"] = ""
    #     table["cell_r5_c8"] = " ازمون "
    #     table["cell_r6_c8"] = "  "
    #     table["cell_r7_c8"] = "  "
    # elif q42_answer=="گزینه پانزدهم":
    #     table["cell_r1_c8"] = " مطالعه و 20تمرین تشریحی"
    #     table["cell_r2_c8"] = " مطالعه و 20تمرین تشریحی"
    #     table["cell_r3_c8"] = " مطالعه و 20تمرین تشریحی"
    #     table["cell_r4_c8"] = " مطالعه و 20تمرین تشریحی"
    #     table["cell_r5_c8"] = ""
    #     table["cell_r6_c8"] = ""
    #     table["cell_r7_c8"] = ""
    # elif q42_answer=="گزینه شانزدهم":
    #     table["cell_r1_c8"] = "ویدیو"
    #     table["cell_r2_c8"] = "ویدیو"
    #     table["cell_r3_c8"] = " ویدیو"
    #     table["cell_r4_c8"] = "30تست "
    #     table["cell_r5_c8"] = "30تست "
    #     table["cell_r6_c8"] = "30تست "
    # elif q42_answer=="گزینه هفدهتم":
    #     table["cell_r1_c8"] = "ویدیو"
    #     table["cell_r2_c8"] = "ویدیو"
    #     table["cell_r3_c8"] = "ویدیو"
    #     table["cell_r4_c8"] = " ویدیو "
    #     table["cell_r5_c"] = "30 تست "
    #     table["cell_r6_c8"] = "30تست  "
    #     table["cell_r7_c8"] = "30تست "
    # elif q42_answer=="گزینه هیجدهم":
    #     table["cell_r1_c8"] = "ویدیو"
    #     table["cell_r2_c8"] = "ویدیو"
    #     table["cell_r3_c8"] = "ویدیو"
    #     table["cell_r4_c8"] = " ویدیو "
    #     table["cell_r5_c8"] = " ویدیو "
    #     table["cell_r6_c8"] = "30تست  "
    #     table["cell_r7_c8"] = "30تست "
    # elif q42_answer=="گزینه نوزدهم":
    #     table["cell_r1_c8"] = "ویدیو"
    #     table["cell_r2_c8"] = "ویدیو"
    #     table["cell_r3_c8"] = "ویدیو"
    #     table["cell_r4_c8"] = " ویدیو "
    #     table["cell_r5_c8"] = " ویدیو "
    #     table["cell_r6_c8"] = "ویدیو  "
    #     table["cell_r7_c8"] = "30تست "
    # elif q42_answer=="گزینه بیستم":
    #     table["cell_r1_c8"] = "ویدیو"
    #     table["cell_r2_c8"] = "ویدیو"
    #     table["cell_r3_c8"] = "ویدیو"
    #     table["cell_r4_c8"] = " ویدیو "
    #     table["cell_r5_c8"] = " ویدیو "
    #     table["cell_r6_c8"] = "ویدیو  "
    #     table["cell_r7_c8"] = "ویدیو "


    q5_answer = answers.get("q5", "")
    topic5 = answers.get("topic_q5", "")
    if q5_answer == "گزینه اول":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer == "گزینه دوم":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه سوم":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q5_answer=="گزینه چهارم":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
        
    elif q5_answer=="گزینه پنجم":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه ششم":
        table["cell_r1_c10"] = "مطالعه"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r4_c10"] = "20 تمرین تشریحی "
        table["cell_r5_c10"] = "20 تمرین تشریحی "
        table["cell_r6_c10"] = "20 تمرین تشریحی "
        


    
    elif q5_answer=="گزینه سیزدهم":
        table["cell_r1_c10"] = " مرور"
        table["cell_r2_c10"] = ""
        table["cell_r4_c10"] = " مرور"
        table["cell_r3_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q5_answer=="گزینه چهاردهم":
        table["cell_r1_c10"] = " ازمون"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه پانزدهم":
        table["cell_r1_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه شانزدهم":
        table["cell_r1_c10"] = "ویدیو"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه هفدهتم":
        table["cell_r1_c10"] = "ویدیو"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه هیجدهم":
        table["cell_r1_c10"] = "ویدیو"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " ویدیو "
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه نوزدهم":
        table["cell_r1_c10"] = "ویدیو"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " ویدیو "
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه بیست و یک":
        table["cell_r1_c10"] = "مطالعه"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " مطالعه "
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q5_answer=="گزینه بیست و دو":
        table["cell_r1_c10"] = "مطالعه"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " مطالعه "
        table["cell_r5_c10"] = " مطالعه "
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q5_answer=="گزینه بیست و سه":
        table["cell_r1_c10"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q5_answer=="گزینه بیستم":
        table["cell_r1_c10"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r5_c10"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q5_answer=="گزینه بیستم":
        table["cell_r1_c10"] = "ویدیو"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " ویدیو "
        table["cell_r5_c10"] = " ویدیو "
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q5_answer=="گزینه بیستم":
        table["cell_r1_c10"] = "ویدیو"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " ویدیو "
        table["cell_r5_c10"] = " ویدیو "
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""



    if topic5:
     for key, val in table.items():
        if key.endswith("_c10") and val:
            table[key] = f"{val} - ({topic5})"


    q6_answer = answers.get("q6", "")
    topic6 = answers.get("topic_q6", "")
    if q6_answer == "گزینه اول":
        table["cell_r1_c13"] = " مطالعه +10 تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""
    elif q6_answer == "گزینه دوم":
        table["cell_r1_c13"] = " مطالعه +10 تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = " مطالعه +10 تشریحی"
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""
    elif q6_answer=="گزینه سوم":
        table["cell_r1_c13"] = " مطالعه +10 تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = " مطالعه +10 تشریحی"
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = " مطالعه +10 تشریحی"
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""

    elif q6_answer=="گزینه چهارم":
        table["cell_r1_c13"] = " مطالعه +10 تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = " مطالعه +10 تشریحی"
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] =" مطالعه +10 تشریحی"
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""
        
    elif q6_answer=="گزینه پنجم":
        table["cell_r1_c13"] = " مطالعه +10 تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = " مطالعه +10 تشریحی"
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = " مطالعه +10 تشریحی"
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = " مطالعه +10 تشریحی"
    elif q6_answer=="گزینه ششم":
        table["cell_r1_c13"] = "مطالعه"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = "20 تمرین تشریحی "
        table["cell_r5_c13"] = ""
        table["cell_r4_c13"] = "20 تمرین تشریحی "
        table["cell_r5_c13"] = "20 تمرین تشریحی "
        table["cell_r7_c13"] = "20 تمرین تشریحی "

    
    elif q6_answer=="گزینه سیزدهم":
        table["cell_r1_c13"] = " مرور"
        table["cell_r2_c13"] = ""
        table["cell_r4_c13"] = " مرور"
        table["cell_r3_c13"] = ""
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = "مرور"

    elif q6_answer=="گزینه چهاردهم":
        table["cell_r1_c13"] = " ازمون"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = "ازمون"
    elif q6_answer=="گزینه پانزدهم":
        table["cell_r1_c13"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] =" مطالعه و 20تمرین تشریحی"
    elif q6_answer=="گزینه شانزدهم":
        table["cell_r1_c13"] = "ویدیو"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
    elif q6_answer=="گزینه هفدهتم":
        table["cell_r1_c13"] = "ویدیو"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = "ویدیو"
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""
    elif q6_answer=="گزینه هیجدهم":
        table["cell_r1_c13"] = "ویدیو"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = " ویدیو "
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = "ویدیو"
        table["cell_r7_c13"] = ""
    elif q6_answer=="گزینه نوزدهم":
        table["cell_r1_c13"] = "ویدیو"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = " ویدیو "
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = "ویدیو"
        table["cell_r7_c13"] = ""
    elif q6_answer=="گزینه بیستم":
        table["cell_r1_c13"] = "ویدیو"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = " ویدیو "
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = "ویدیو"
        table["cell_r7_c13"] = ""

    elif q6_answer=="گزینه بیست و یک":
        table["cell_r1_c13"] = "مطالعه"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = " مطالعه "
        table["cell_r5_c13"] = ""
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""
    elif q6_answer=="گزینه بیست و دو":
        table["cell_r1_c13"] = "مطالعه"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = " مطالعه "
        table["cell_r5_c13"] = " مطالعه "
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""

    elif q6_answer=="گزینه بیست و سه":
        table["cell_r1_c13"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = ""
        table["cell_r5_c13"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""

    elif q6_answer=="گزینه بیست و چهار":
        table["cell_r1_c13"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c13"] = ""
        table["cell_r3_c13"] = ""
        table["cell_r4_c13"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r5_c13"] ="طالعه و 20 تمرین تشریحی"
        table["cell_r6_c13"] = ""
        table["cell_r7_c13"] = ""



    if topic6:
     for key, val in table.items():
        if key.endswith("_c13") and val:
            table[key] = f"{val} - ({topic6})"


    q7_answer = answers.get("q7", "")
    topic7 = answers.get("topic_q7", "")
    if q7_answer == "گزینه اول":
        table["cell_r1_c9"] = " مطالعه +10 تشریحی"
        table["cell_r2_c9"] = " مطالعه +10 تشریحی"
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = ""
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""
    elif q7_answer == "گزینه دوم":
        table["cell_r1_c9"] = " مطالعه +10 تشریحی"
        table["cell_r2_c9"] = " مطالعه +10 تشریحی"
        table["cell_r3_c9"] = " مطالعه +10 تشریحی"
        table["cell_r4_c9"] = ""
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه سوم":
        table["cell_r1_c9"] = " مطالعه +10 تشریحی"
        table["cell_r2_c9"] = " مطالعه +10 تشریحی"
        table["cell_r3_c9"] = " مطالعه +10 تشریحی"
        table["cell_r4_c9"] = ""
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""

    elif q7_answer=="گزینه چهارم":
        table["cell_r1_c9"] = ""
        table["cell_r2_c9"] = " مطالعه +15 تشریحی"
        table["cell_r3_c9"] = " مطالعه +10 تشریحی"
        table["cell_r4_c9"] = " مطالعه +20 تشریحی"
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""
        
    elif q7_answer=="گزینه پنجم":
        table["cell_r1_c9"] = " مطالعه +10 تشریحی"
        table["cell_r2_c9"] = " مطالعه +15 تشریحی"
        table["cell_r3_c9"] = " مطالعه +15 تشریحی"
        table["cell_r4_c9"] = " مطالعه +20 تشریحی"
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه ششم":
        table["cell_r1_c9"] = "مطالعه"
        table["cell_r2_c9"] = "مطالعه"
        table["cell_r3_c9"] = "20 تمرین تشریحی "
        table["cell_r5_c9"] = "20 تمرین تشریحی "
        table["cell_r4_c9"] = "20 تمرین تشریحی "
        table["cell_r5_c9"] = ""
        table["cell_r7_c9"] = ""

    
    elif q7_answer=="گزینه سیزدهم":
        table["cell_r1_c9"] = "مرور"
        table["cell_r2_c9"] = ""
        table["cell_r4_c9"] = " مرور"
        table["cell_r3_c9"] = ""
        table["cell_r5_c9"] = "مرور"
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = "مرور"

    elif q7_answer=="گزینه چهاردهم":
        table["cell_r1_c9"] = " "
        table["cell_r2_c9"] = "ازمون"
        table["cell_r3_c9"] = " "
        table["cell_r4_c9"] = ""
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = "ازمون"
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه پانزدهم":
        table["cell_r1_c9"] = ""
        table["cell_r2_c9"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r7_c9"] =""
    elif q7_answer=="گزینه شانزدهم":
        table["cell_r1_c9"] = "ویدیو"
        table["cell_r2_c9"] = "ویدیو"
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = ""
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
    elif q7_answer=="گزینه هفدهتم":
        table["cell_r1_c9"] = ""
        table["cell_r2_c9"] = "ویدیو"
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = "ویدیو"
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = "ویدیو"
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه هیجدهم":
        table["cell_r1_c9"] = ""
        table["cell_r2_c9"] = "ویدیو"
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = " ویدیو "
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = "ویدیو"
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه نوزدهم":
        table["cell_r1_c9"] = ""
        table["cell_r2_c9"] = "ویدیو"
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = " ویدیو "
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = "ویدیو"
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه بیستم":
        table["cell_r1_c9"] = "ویدیو"
        table["cell_r2_c9"] = ""
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = " ویدیو "
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = "ویدیو"
        table["cell_r7_c9"] = ""

    elif q7_answer=="گزینه بیست و یک":
        table["cell_r1_c9"] =" مطالعه +10 تشریحی"
        table["cell_r2_c9"] = ""
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = " مطالعه +10 تشریحی"
        table["cell_r5_c9"] = ""
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""
    elif q7_answer=="گزینه بیست و دو":
        table["cell_r1_c9"] =" مطالعه +15 تشریحی"
        table["cell_r2_c9"] = ""
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = " مطالعه +15 تشریحی"
        table["cell_r5_c9"] = " مطالعه +15 تشریحی"
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""

    elif q7_answer=="گزینه بیست و سه":
        table["cell_r1_c9"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c9"] = ""
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = ""
        table["cell_r5_c9"] = "العه و 20 تمرین تشریحی"
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""

    elif q7_answer=="گزینه بیست و چهار":
        table["cell_r1_c9"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c9"] = ""
        table["cell_r3_c9"] = ""
        table["cell_r4_c9"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r5_c9"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r6_c9"] = ""
        table["cell_r7_c9"] = ""



    if topic7:
     for key, val in table.items():
        if key.endswith("_c9") and val:
            table[key] = f"{val} - ({topic7})"

   

    q8_answer = answers.get("q8", "")
    topic8= answers.get("topic_q8", "")
    if q8_answer == "گزینه اول":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q8_answer == "گزینه دوم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] =" مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +15 تشریحی"
        table["cell_r7_c10"] = ""
    elif q8_answer=="گزینه سوم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q8_answer=="گزینه چهارم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
        
    elif q8_answer=="گزینه پنجم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q8_answer=="گزینه ششم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = "20 تمرین تشریحی "
        table["cell_r5_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +10 تشریحی"
        table["cell_r7_c10"] = ""

    
    elif q8_answer=="گزینه سیزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مرور"
        table["cell_r4_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "مرور"

    elif q8_answer=="گزینه چهاردهم":
        table["cell_r1_c10"] = " "
        table["cell_r2_c10"] = "ازمون"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "ازمون"
    elif q8_answer=="گزینه پانزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c10"] = " مطالعه و 10تمرین تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +15 تشریحی"
        table["cell_r7_c10"] =""
    elif q8_answer=="گزینه شانزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] =" مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q8_answer=="گزینه هفدهتم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = " مطالعه +10 تشریحی"
    elif q8_answer=="گزینه هیجدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q8_answer=="گزینه نوزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q8_answer=="گزینه بیستم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] =" مطالعه +10 تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "ویدیو"

    if topic8:
     for key, val in table.items():
        if key.endswith("_c10") and val:
            table[key] = f"{val} - ({topic8})"


    q9_answer = answers.get("q9", "")
    topic9 = answers.get("topic_q9", "")
    if q9_answer == "گزینه اول":
        table["cell_r1_c12"] = " مطالعه +10 تشریحی"
        table["cell_r2_c12"] = ""
        table["cell_r3_c12"] = " مطالعه +15 تشریحی"
        table["cell_r4_c12"] = ""
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
        
    elif q9_answer == "گزینه دوم":
        table["cell_r1_c12"] = "مطالعه"
        table["cell_r2_c12"] = "مطالعه"
        table["cell_r3_c12"] = "مطالعه"
        table["cell_r4_c12"] = ""
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
    elif q9_answer=="گزینه سوم":
        table["cell_r1_c12"] = "مطالعه"
        table["cell_r2_c12"] = "مطالعه"
        table["cell_r3_c12"] = "مطالعه"
        table["cell_r4_c12"] = " مطالعه "
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
    elif q9_answer=="گزینه چهارم":
        table["cell_r1_c12"] = "مطالعه"
        table["cell_r2_c12"] = "مطالعه"
        table["cell_r3_c12"] = "مطالعه"
        table["cell_r4_c12"] = " مطالعه "
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
    elif q9_answer=="گزینه پنجم":
        table["cell_r1_c12"] = "مطالعه"
        table["cell_r2_c12"] = "مطالعه"
        table["cell_r3_c12"] = "مطالعه"
        table["cell_r4_c12"] = " مطالعه "
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
    elif q9_answer=="گزینه ششم":
        table["cell_r1_c12"] = "مطالعه"
        table["cell_r2_c12"] = "20 تمرین تشریحی "
        table["cell_r3_c12"] = "مطالعه"
        table["cell_r4_c12"] = " 20تمرین تشریحی "
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
   
    elif q9_answer=="گزینه سیزدهم":
        table["cell_r1_c12"] = " مرور"
        table["cell_r2_c12"] = " 15 تمرین تشریحی"
        table["cell_r3_c12"] = " مرور"
        table["cell_r4_c12"] = "  20 تمرین تشریحی "
        table["cell_r5_c12"] = " مرور "
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""

    elif q9_answer=="گزینه چهاردهم":
        table["cell_r1_c12"] = " ازمون"
        table["cell_r2_c12"] = ""
        table["cell_r3_c12"] = ""
        table["cell_r4_c12"] = ""
        table["cell_r5_c12"] = " ازمون "
        table["cell_r6_c12"] = "  "
        table["cell_r7_c12"] = "  "
    elif q9_answer=="گزینه پانزدهم":
        table["cell_r1_c12"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r2_c12"] = " مطالعه و 10تمرین تشریحی"
        table["cell_r3_c12"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c12"] = " مطالعه و 15تمرین تشریحی"
        table["cell_r5_c12"] = ""
        table["cell_r6_c12"] = ""
        table["cell_r7_c12"] = ""
    elif q9_answer=="گزینه شانزدهم":
        table["cell_r1_c12"] = "ویدیو"
        table["cell_r2_c12"] = "ویدیو"
        table["cell_r3_c12"] = " ویدیو"
        table["cell_r4_c12"] = "30تست "
        table["cell_r5_c12"] = "40تست "
        table["cell_r6_c12"] = "50تست "
        table["cell_r7_c12"] = "30تست "
    elif q9_answer=="گزینه هفدهتم":
        table["cell_r1_c12"] = "ویدیو"
        table["cell_r2_c12"] = "ویدیو"
        table["cell_r3_c12"] = "ویدیو"
        table["cell_r4_c12"] = " ویدیو "
        table["cell_r5_c12"] = "30 تست "
        table["cell_r6_c12"] = "35تست  "
        table["cell_r7_c12"] = "40تست "
    elif q9_answer=="گزینه هیجدهم":
        table["cell_r1_c12"] = "ویدیو"
        table["cell_r2_c12"] = "ویدیو"
        table["cell_r3_c12"] = "ویدیو"
        table["cell_r4_c12"] = " ویدیو "
        table["cell_r5_c12"] = " ویدیو "
        table["cell_r6_c12"] = "30تست  "
        table["cell_r7_c12"] = "40تست "
    elif q9_answer=="گزینه نوزدهم":
        table["cell_r1_c12"] = "ویدیو"
        table["cell_r2_c12"] = "ویدیو"
        table["cell_r3_c12"] = "ویدیو"
        table["cell_r4_c12"] = " ویدیو "
        table["cell_r5_c12"] = " ویدیو "
        table["cell_r6_c12"] = "ویدیو  "
        table["cell_r7_c12"] = "30تست "
    elif q9_answer=="گزینه بیستم":
        table["cell_r1_c12"] = "ویدیو"
        table["cell_r2_c12"] = "ویدیو"
        table["cell_r3_c12"] = "ویدیو"
        table["cell_r4_c12"] = " ویدیو "
        table["cell_r5_c12"] = " ویدیو "
        table["cell_r6_c12"] = "ویدیو  "
        table["cell_r7_c12"] = "ویدیو "
    if topic9:
     for key, val in table.items():
        if key.endswith("_c12") and val:
            table[key] = f"{val} - ({topic9})"





    rows = 7   # تعداد ردیف
    cols = 14 # تعداد ستون

    for r in range(1, rows+1):
     row_values = [table.get(f"cell_r{r}_c{c}", "") for c in range(1, cols+1)]
    random.shuffle(row_values)
    for c, val in enumerate(row_values, start=1):
        table[f"cell_r{r}_c{c}"] = val





    q10_answer = answers.get("q10", "")
    topic10= answers.get("topic_q10", "")
    if q10_answer == "گزینه اول":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +15 تشریحی"
        table["cell_r7_c10"] = ""
    elif q10_answer == "گزینه دوم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +15 تشریحی"
        table["cell_r7_c10"] = ""
    elif q10_answer=="گزینه سوم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +10 تشریحی"
        table["cell_r7_c10"] = ""

    elif q10_answer=="گزینه چهارم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
        
    elif q10_answer=="گزینه پنجم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه +10 تشریحی"
        table["cell_r3_c10"] = " مطالعه +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = " مطالعه +10 تشریحی"
    elif q10_answer=="گزینه ششم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = "20 تمرین تشریحی "
        table["cell_r5_c10"] = " مطالعه +20 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +10 تشریحی"
        table["cell_r7_c10"] = ""

    
    elif q10_answer=="گزینه سیزدهم":
        table["cell_r1_c10"] = " مرور +20 تشریحی"
        table["cell_r2_c10"] = " مرور +10 تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r3_c10"] = " مرور +15 تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "مرور"

    elif q10_answer=="گزینه چهاردهم":
        table["cell_r1_c10"] = " مرور +10 تشریحی"
        table["cell_r2_c10"] = "ازمون"
        table["cell_r3_c10"] = " "
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "ازمون"
    elif q10_answer=="گزینه پانزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +10 تشریحی"
        table["cell_r7_c10"] =""
    elif q10_answer=="گزینه شانزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = " مطالعه +10 تشریحی"
    elif q10_answer=="گزینه هفدهتم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] =" مطالعه +10 تشریحی"
        table["cell_r7_c10"] = ""
    elif q10_answer=="گزینه هیجدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +10 تشریحی"
        table["cell_r7_c10"] = ""
    elif q10_answer=="گزینه نوزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = "  "
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = " مطالعه +10 تشریحی"
    elif q10_answer=="گزینه بیستم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = " مطالعه +10 تشریحی"
        table["cell_r7_c10"] = "ویدیو"

    elif q10_answer=="گزینه بیست و یک":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q10_answer=="گزینه بیست و دو":
        table["cell_r1_c10"] = " مطالعه +10 تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = " مطالعه +10 تشریحی"
        table["cell_r5_c10"] = " مطالعه +10 تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q10_answer=="گزینه بیست و سه":
        table["cell_r1_c10"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q10_answer=="گزینه بیست و چهار":
        table["cell_r1_c10"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r2_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = "مطالعه و 20 تمرین تشریحی"
        table["cell_r5_c10"] ="مطالعه و 20 تمرین تشریحی"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""


    if topic10:
     for key, val in table.items():
        if key.endswith("_c10") and val:
            table[key] = f"{val} - ({topic10})"
    rows = 7   # تعداد ردیف
    cols = 10 # تعداد ستون

    for r in range(1, rows+1):
     row_values = [table.get(f"cell_r{r}_c{c}", "") for c in range(1, cols+1)]
    random.shuffle(row_values)
    for c, val in enumerate(row_values, start=1):
        table[f"cell_r{r}_c{c}"] = val


    q11_answer = answers.get("q11", "")
    topic11= answers.get("topic_q11", "")
    if q7_answer == "گزینه اول":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer == "گزینه دوم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = "مطالعه"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer=="گزینه سوم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = "مطالعه"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    elif q11_answer=="گزنه چهارم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = "مطالعه"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
        
    elif q11_answer=="گزینه پنجم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = "مطالعه"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = "مطالعه"
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer=="گزینه ششم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مطالعه"
        table["cell_r3_c10"] = "20 تمرین تشریحی "
        table["cell_r5_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""

    
    elif q11_answer=="گزینه سیزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "مرور"
        table["cell_r4_c10"] = ""
        table["cell_r3_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "مرور"

    elif q11_answer=="گزینه چهاردهم":
        table["cell_r1_c10"] = " "
        table["cell_r2_c10"] = "ازمون"
        table["cell_r3_c10"] = " "
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "ازمون"
    elif q11_answer=="گزینه پانزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r3_c10"] = " مطالعه و 20تمرین تشریحی"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] =""
    elif q11_answer=="گزینه شانزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = ""
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer=="گزینه هفدهتم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer=="گزینه هیجدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer=="گزینه نوزدهم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = "  "
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = ""
    elif q11_answer=="گزینه بیستم":
        table["cell_r1_c10"] = ""
        table["cell_r2_c10"] = "ویدیو"
        table["cell_r3_c10"] = "ویدیو"
        table["cell_r4_c10"] = ""
        table["cell_r5_c10"] = ""
        table["cell_r6_c10"] = ""
        table["cell_r7_c10"] = "ویدیو"

    rows = 7   # تعداد ردیف
    cols = 10 # تعداد ستون

    for r in range(1, rows+1):
     row_values = [table.get(f"cell_r{r}_c{c}", "") for c in range(1, cols+1)]
    random.shuffle(row_values)
    for c, val in enumerate(row_values, start=1):
        table[f"cell_r{r}_c{c}"] = val

    if topic11:
     for key, val in table.items():
        if key.endswith("_c10") and val:
            table[key] = f"{val} - ({topic11})"



    q91_answer = answers.get("q91", "")
    if q91_answer == "شنبه":
        table["cell_r1_c9"] = ""


    q92_answer = answers.get("q92", "")
    if q92_answer == "یکشنبه":
        table["cell_r2_c9"] = ""


    q93_answer = answers.get("q93", "")
    if q93_answer == "دوشنبه":
        table["cell_r3_c9"] = ""


    q94_answer = answers.get("q94", "")
    if q94_answer == "سه شنبه":
        table["cell_r4_c9"] = ""
        

        

    q95_answer = answers.get("q95", "")
    if q95_answer == "چهارشنبه":
        table["cell_r5_c9"] = ""

        

    q96_answer = answers.get("q96", "")
    if q96_answer == "پنجشنبه":
        table["cell_r6_c9"] = ""

        

    q97_answer = answers.get("q97", "")
    if q97_answer == "جمعه":
        table["cell_r7_c9"] = ""

        
    q101_answer = answers.get("q101", "")
    if q101_answer == "شنبه":
        table["cell_r7_c6"] = 'مبحث امتحان'

    q102_answer = answers.get("q102", "")
    if q102_answer == "یکشنبه":
        table["cell_r1_c6"] = "مبحث امتحان"


           
    q103_answer = answers.get("q103", "")
    if q103_answer == "دوشنبه":
        table["cell_r2_c6"] = "مبحث امتحان"
        
    q104_answer = answers.get("q104", "")
    if q104_answer =="سه شنبه" :
        table["cell_r3_c6"] = "مبحث امتحان"

    q105_answer = answers.get("q105", "")
    if q105_answer == "چهارشنبه":
        table["cell_r4_c6"] = "مبحث امتحان"



    q106_answer = answers.get("q106", "")
    if q106_answer == "پنجشنبه":
        table["cell_r5_c6"] = "مبحث امتحان"


    q107_answer = answers.get("q107", "")
    if q107_answer == "جمعه":
        table["cell_r6_c6"] = "مبحث امتحان"


    q121_answer = answers.get("q121", "")
    if q121_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q121_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q121_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q121_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q121_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q121_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q121_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q121_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q121_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q121_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q121_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(1, 2): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""

      
    q122_answer = answers.get("q122", "")
    if q122_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q122_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q122_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q122_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q122_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q122_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q122_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q122_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q122_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q122_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q122_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(2, 3): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""


    q123_answer = answers.get("q123", "")
    if q123_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q123_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q123_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q123_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q123_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q123_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q123_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q123_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q123_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q123_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q123_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(3, 4): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""

      
 

      
 

   



    q124_answer = answers.get("q124", "")
    if q124_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q124_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q124_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q124_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q124_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q124_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q124_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q124_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q124_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q124_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q124_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(4, 5): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""

      
 

       
    q125_answer = answers.get("q125", "")
    if q125_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q125_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q125_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q125_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q125_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q125_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q125_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q125_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q125_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q125_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q125_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(5, 6): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""

      
 

       
    q126_answer = answers.get("q126", "")
    if q126_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q126_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q126_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q126_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q126_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q126_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q126_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q126_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q126_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q126_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(6,7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q126_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(6, 7): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""

      
 

    q127_answer = answers.get("q127", "")
    if q127_answer == "گزینه اول":
        total_columns = 13
        empty_per_row = 7
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q127_answer == "گزینه دوم":
        total_columns = 13
        empty_per_row = 7
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q127_answer == "گزینه سوم":
        total_columns = 13
        empty_per_row = 6
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q127_answer == "گزینه چهارم":
        total_columns = 13
        empty_per_row = 5
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q127_answer == "گزینه پنچم":
        total_columns = 13
        empty_per_row = 5
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q127_answer == "گزینه ششم":
        total_columns = 13
        empty_per_row = 4
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  

    elif q127_answer == "گزینه هفتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q127_answer == "گزینه هشتم":
        total_columns = 13
        empty_per_row = 3
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q127_answer == "گزینه نهم":
        total_columns = 13
        empty_per_row = 3
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = "" 

    elif q127_answer == "گزینه دهم":
        total_columns = 13
        empty_per_row = 2
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""  
    
    elif q127_answer == "گزینه یازدهم":
        total_columns = 13
        empty_per_row = 1
        for row in range(7, 8): 
            empty_cols = random.sample(range(1, total_columns + 1), empty_per_row)
            for col in empty_cols:
                cell_key = f"cell_r{row}_c{col}"
                table[cell_key] = ""

      
 


    # rows = 7   # تعداد ردیف
    # cols = 10 # تعداد ستون

    # for r in range(1, rows+1):
    #  row_values = [table.get(f"cell_r{r}_c{c}", "") for c in range(1, cols+1)]
    #  random.shuffle(row_values)
    #  for c, val in enumerate(row_values, start=1):
    #     table[f"cell_r{r}_c{c}"] = val


  
    rows = 7
    cols = 13

    for r in range(1, rows+1):
    # 1. گرفتن مقادیر
     row_values = [table.get(f"cell_r{r}_c{c}", "") for c in range(1, cols+1)]

    # 2. حذف خالی‌ها
     non_empty = [v for v in row_values if v.strip()]

    # 3. پرها مرتب بشن (از ستون اول شروع کنن)
     ordered = non_empty + [""] * (cols - len(non_empty))

    # 4. فقط بخش پرها رو shuffle کن
     random.shuffle(non_empty)

    # دوباره بچین: پرهای مخلوط + خالی‌ها در انتها
     row_values = non_empty + [""] * (cols - len(non_empty))

    # 5. بازنویسی تو جدول
     for c, val in enumerate(row_values, start=1):
      table[f"cell_r{r}_c{c}"] = val


    return table





if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)