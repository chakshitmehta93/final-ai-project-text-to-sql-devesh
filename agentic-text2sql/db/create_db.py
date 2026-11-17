"""
Create and seed the college database.
run: python db/create_db.py
Works for both SQLite (default) and PostgreSQL (set DATABASE_URL env var).
random.seed(42) keeps the data deterministic so eval results are reproducible.
"""
import os, sys, random

random.seed(42)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import (
    create_engine, text, MetaData, Table, Column,
    Integer, String, Float, ForeignKey, UniqueConstraint
)

import config

engine = create_engine(config.DATABASE_URL)
meta = MetaData()

# ── table definitions ─────────────────────────────────────────────────────────

departments = Table("departments", meta,
    Column("dept_id", Integer, primary_key=True),
    Column("dept_name", String),
    Column("dept_code", String),   # CSE, ME, ECE, CE, IT, BT, CH, MA, PH, MG
    Column("hod_name", String),
    Column("established_year", Integer),
)

faculty = Table("faculty", meta,
    Column("faculty_id", Integer, primary_key=True),
    Column("name", String),        # ambiguous: also in students
    Column("dept_id", Integer, ForeignKey("departments.dept_id")),
    Column("designation", String), # Professor, Asst. Prof, Lecturer
    Column("email", String),
    Column("status", String),      # Active / On-Leave  (ambiguous across tables)
)

students = Table("students", meta,
    Column("student_id", Integer, primary_key=True),
    Column("name", String),
    Column("dept_id", Integer, ForeignKey("departments.dept_id")),
    Column("year", Integer),       # 1-4  (ambiguous: also in courses as credit_year)
    Column("gender", String),
    Column("email", String),
    Column("status", String),      # Active / Dropped / Graduated
)

courses = Table("courses", meta,
    Column("course_id", Integer, primary_key=True),
    Column("course_name", String),
    Column("course_code", String),
    Column("credits", Integer),
    Column("dept_id", Integer, ForeignKey("departments.dept_id")),
    Column("course_type", String), # Core / Elective / Lab
    Column("year", Integer),       # which year this course is offered (ambiguous)
)

enrollments = Table("enrollments", meta,
    Column("enroll_id", Integer, primary_key=True),
    Column("student_id", Integer, ForeignKey("students.student_id")),
    Column("course_id", Integer, ForeignKey("courses.course_id")),
    Column("semester", Integer),
    Column("status", String),      # Enrolled / Dropped / Completed  (ambiguous)
    UniqueConstraint("student_id", "course_id", "semester"),
)

marks = Table("marks", meta,
    Column("mark_id", Integer, primary_key=True),
    Column("enroll_id", Integer, ForeignKey("enrollments.enroll_id")),
    Column("student_id", Integer, ForeignKey("students.student_id")),
    Column("course_id", Integer, ForeignKey("courses.course_id")),
    Column("score", Float),
    Column("grade", String),
    Column("semester", Integer),
)

attendance = Table("attendance", meta,
    Column("att_id", Integer, primary_key=True),
    Column("student_id", Integer, ForeignKey("students.student_id")),
    Column("course_id", Integer, ForeignKey("courses.course_id")),
    Column("semester", Integer),
    Column("total_classes", Integer),
    Column("attended", Integer),
)

fees = Table("fees", meta,
    Column("fee_id", Integer, primary_key=True),
    Column("student_id", Integer, ForeignKey("students.student_id")),
    Column("semester", Integer),
    Column("amount", Float),
    Column("paid", Float),
    Column("status", String),      # Paid / Partial / Unpaid  (ambiguous)
)

hostels = Table("hostels", meta,
    Column("hostel_id", Integer, primary_key=True),
    Column("hostel_name", String),
    Column("gender", String),
    Column("capacity", Integer),
)

hostel_allotments = Table("hostel_allotments", meta,
    Column("allot_id", Integer, primary_key=True),
    Column("student_id", Integer, ForeignKey("students.student_id")),
    Column("hostel_id", Integer, ForeignKey("hostels.hostel_id")),
    Column("room_no", String),
    Column("year", Integer),       # academic year  (ambiguous)
)

clubs = Table("clubs", meta,
    Column("club_id", Integer, primary_key=True),
    Column("club_name", String),
    Column("faculty_id", Integer, ForeignKey("faculty.faculty_id")),
    Column("status", String),      # Active / Inactive  (ambiguous)
)

club_members = Table("club_members", meta,
    Column("cm_id", Integer, primary_key=True),
    Column("club_id", Integer, ForeignKey("clubs.club_id")),
    Column("student_id", Integer, ForeignKey("students.student_id")),
    Column("role", String),
    Column("year", Integer),       # year joined  (ambiguous)
)


def grade(score):
    if score >= 90: return "O"
    if score >= 80: return "A+"
    if score >= 70: return "A"
    if score >= 60: return "B+"
    if score >= 50: return "B"
    if score >= 40: return "C"
    return "F"


def seed(conn):
    dept_rows = [
        (1, "Computer Science and Engineering", "CSE", "Dr. Ramesh Kumar", 1985),
        (2, "Mechanical Engineering", "ME", "Dr. Priya Nair", 1972),
        (3, "Electronics and Communication", "ECE", "Dr. Suresh Pillai", 1980),
        (4, "Civil Engineering", "CE", "Dr. Meena Singh", 1968),
        (5, "Information Technology", "IT", "Dr. Arvind Sharma", 1998),
        (6, "Biotechnology", "BT", "Dr. Lakshmi Rao", 2003),
        (7, "Chemical Engineering", "CH", "Dr. Vijay Patel", 1990),
        (8, "Mathematics", "MA", "Dr. Sonal Gupta", 1965),
        (9, "Physics", "PH", "Dr. Rajan Nath", 1963),
        (10, "Management", "MG", "Dr. Kavita Joshi", 2000),
    ]
    conn.execute(departments.insert(), [
        dict(dept_id=r[0], dept_name=r[1], dept_code=r[2], hod_name=r[3], established_year=r[4])
        for r in dept_rows
    ])

    first_names = ["Aarav","Vivaan","Diya","Isha","Rohan","Ananya","Kabir","Meera",
                   "Arjun","Sara","Neha","Karan","Riya","Dev","Tara","Yash","Pooja",
                   "Nikhil","Aditi","Sameer","Priya","Raj","Sita","Aman","Nisha",
                   "Kunal","Deepa","Rahul","Anjali","Vikram"]
    last_names = ["Sharma","Verma","Kumar","Singh","Patel","Gupta","Rao","Nair",
                  "Pillai","Reddy","Joshi","Mehta","Shah","Pandey","Chandra"]

    # 300 students
    student_rows = []
    for i in range(1, 301):
        fn = random.choice(first_names)
        ln = random.choice(last_names)
        did = random.randint(1, 10)
        yr = random.randint(1, 4)
        g = random.choice(["M","F"])
        st = random.choices(["Active","Graduated","Dropped"], weights=[70,25,5])[0]
        email = f"{fn.lower()}.{ln.lower()}{i}@college.edu"
        student_rows.append(dict(student_id=i, name=f"{fn} {ln}", dept_id=did,
                                 year=yr, gender=g, email=email, status=st))
    conn.execute(students.insert(), student_rows)

    desig = ["Professor","Associate Professor","Assistant Professor","Lecturer"]
    faculty_rows = []
    for i in range(1, 61):
        fn = random.choice(first_names)
        ln = random.choice(last_names)
        did = random.randint(1, 10)
        d = random.choice(desig)
        st = random.choices(["Active","On-Leave"], weights=[90,10])[0]
        email = f"fac.{fn.lower()}{i}@college.edu"
        faculty_rows.append(dict(faculty_id=i, name=f"Dr. {fn} {ln}", dept_id=did,
                                 designation=d, email=email, status=st))
    conn.execute(faculty.insert(), faculty_rows)

    course_data = [
        (1,"Data Structures","CS101",4,1,"Core",1),
        (2,"DBMS","CS201",4,1,"Core",2),
        (3,"Operating Systems","CS301",4,1,"Core",3),
        (4,"Computer Networks","CS401",3,1,"Core",4),
        (5,"Artificial Intelligence","CS501",3,1,"Elective",3),
        (6,"Machine Learning","CS502",3,1,"Elective",4),
        (7,"Thermodynamics","ME101",4,2,"Core",1),
        (8,"Fluid Mechanics","ME201",4,2,"Core",2),
        (9,"Digital Electronics","EC101",4,3,"Core",1),
        (10,"Signal Processing","EC201",3,3,"Core",2),
        (11,"Structural Analysis","CV101",4,4,"Core",2),
        (12,"Concrete Design","CV201",3,4,"Core",3),
        (13,"Web Technologies","IT101",3,5,"Core",2),
        (14,"Cybersecurity","IT201",3,5,"Elective",3),
        (15,"Microbiology","BT101",4,6,"Core",1),
        (16,"Chemical Reactions","CH101",4,7,"Core",1),
        (17,"Linear Algebra","MA101",4,8,"Core",1),
        (18,"Quantum Physics","PH101",3,9,"Core",2),
        (19,"Business Management","MG101",3,10,"Core",1),
        (20,"DBMS Lab","CS202",2,1,"Lab",2),
    ]
    conn.execute(courses.insert(), [
        dict(course_id=r[0],course_name=r[1],course_code=r[2],credits=r[3],
             dept_id=r[4],course_type=r[5],year=r[6])
        for r in course_data
    ])

    hostel_rows = [
        dict(hostel_id=1,hostel_name="Sunrise Hostel",gender="M",capacity=150),
        dict(hostel_id=2,hostel_name="Moonlight Hostel",gender="F",capacity=120),
        dict(hostel_id=3,hostel_name="Greenview Hostel",gender="M",capacity=200),
        dict(hostel_id=4,hostel_name="Rosedale Hostel",gender="F",capacity=100),
    ]
    conn.execute(hostels.insert(), hostel_rows)

    club_data = [
        (1,"Coding Club",1,"Active"),
        (2,"Robotics Club",5,"Active"),
        (3,"Music Club",10,"Active"),
        (4,"Sports Club",3,"Active"),
        (5,"Photography Club",7,"Inactive"),
        (6,"Debate Club",2,"Active"),
    ]
    conn.execute(clubs.insert(), [
        dict(club_id=r[0],club_name=r[1],faculty_id=r[2],status=r[3])
        for r in club_data
    ])

    # enrollments, marks, attendance, fees
    enroll_rows, mark_rows, att_rows, fee_rows = [], [], [], []
    hostel_allot_rows, club_member_rows = [], []
    eid, mid, aid, fid, allot_id, cmid = 1, 1, 1, 1, 1, 1

    for s in student_rows:
        sid = s["student_id"]
        did = s["dept_id"]
        yr  = s["year"]
        g   = s["gender"]

        # pick courses (dept courses + 1-2 open electives)
        dept_courses = [c for c in course_data if c[4] == did]
        other = [c for c in course_data if c[4] != did]
        chosen = random.sample(dept_courses, min(3, len(dept_courses)))
        chosen += random.sample(other, min(2, len(other)))

        for sem in range(1, min(yr * 2 + 1, 9)):
            sem_courses = random.sample(chosen, min(3, len(chosen)))
            for crs in sem_courses:
                cid = crs[0]
                est = "Completed" if sem < yr * 2 else "Enrolled"
                enroll_rows.append(dict(enroll_id=eid, student_id=sid, course_id=cid,
                                        semester=sem, status=est))

                score = round(random.uniform(30, 100), 1)
                mark_rows.append(dict(mark_id=mid, enroll_id=eid, student_id=sid,
                                      course_id=cid, score=score, grade=grade(score),
                                      semester=sem))

                total = random.randint(40, 60)
                att_pct = random.uniform(0.5, 1.0)
                att_rows.append(dict(att_id=aid, student_id=sid, course_id=cid,
                                     semester=sem, total_classes=total,
                                     attended=int(total * att_pct)))
                eid += 1; mid += 1; aid += 1

            # fees per semester
            amt = 50000.0
            paid = random.choices([amt, round(random.uniform(20000, 49999), 2), 0.0],
                                   weights=[70, 20, 10])[0]
            st = "Paid" if paid == amt else ("Partial" if paid > 0 else "Unpaid")
            fee_rows.append(dict(fee_id=fid, student_id=sid, semester=sem,
                                  amount=amt, paid=paid, status=st))
            fid += 1

        # hostel (40% students)
        if random.random() < 0.4:
            opts = [h for h in hostel_rows if h["gender"] == g]
            if opts:
                h = random.choice(opts)
                hostel_allot_rows.append(dict(allot_id=allot_id, student_id=sid,
                    hostel_id=h["hostel_id"], room_no=f"R{random.randint(1,50):03d}",
                    year=yr))
                allot_id += 1

        # club (30% students)
        if random.random() < 0.3:
            club = random.choice(club_data)
            role = random.choice(["Member","Secretary","Treasurer","President"])
            club_member_rows.append(dict(cm_id=cmid, club_id=club[0], student_id=sid,
                                          role=role, year=yr))
            cmid += 1

    # batch insert
    for chunk in [enroll_rows[i:i+500] for i in range(0, len(enroll_rows), 500)]:
        conn.execute(enrollments.insert(), chunk)
    for chunk in [mark_rows[i:i+500] for i in range(0, len(mark_rows), 500)]:
        conn.execute(marks.insert(), chunk)
    conn.execute(attendance.insert(), att_rows)
    conn.execute(fees.insert(), fee_rows)
    conn.execute(hostel_allotments.insert(), hostel_allot_rows)
    conn.execute(club_members.insert(), club_member_rows)

    print(f"students={len(student_rows)}, enrollments={len(enroll_rows)}, "
          f"marks={len(mark_rows)}, attendance={len(att_rows)}, fees={len(fee_rows)}, "
          f"hostel_allotments={len(hostel_allot_rows)}, club_members={len(club_member_rows)}")


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    # drop existing db if sqlite
    if "sqlite" in config.DATABASE_URL and os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
        print(f"removed old {config.DB_PATH}")

    meta.drop_all(engine)
    meta.create_all(engine)
    with engine.begin() as conn:
        seed(conn)
    print(f"database ready: {config.DATABASE_URL}")
