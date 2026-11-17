# business rules for the college database
# one rule per line; the RAG layer retrieves the most relevant ones for each question

"CSE" means departments.dept_code = 'CSE'. Always join students to departments on dept_id to filter by department.
"ME" means departments.dept_code = 'ME'. Mechanical Engineering department.
"ECE" means departments.dept_code = 'ECE'. Electronics and Communication department.
"CE" means departments.dept_code = 'CE'. Civil Engineering department.
"IT" means departments.dept_code = 'IT'. Information Technology department.
Scoring above X means marks.score > X. Scoring below X means marks.score < X.
A student's overall performance is AVG(marks.score) grouped by student_id.
Top N students means ORDER BY the relevant metric DESC LIMIT N.
Pass means marks.score >= 40. Fail means marks.score < 40.
Grade 'O' means score >= 90, 'A+' means score >= 80, 'A' means score >= 70, 'B+' means score >= 60, 'B' means score >= 50, 'C' means score >= 40, 'F' means score < 40.
First year means students.year = 1. Second year means students.year = 2. Third year means students.year = 3. Fourth year means students.year = 4.
Semester is stored as an integer 1 to 8 in marks.semester and enrollments.semester.
Always return student names via students.name, never student_id alone unless asked.
Attendance percentage = (attendance.attended / attendance.total_classes) * 100.
Low attendance means attendance percentage < 75.
Fee defaulter means fees.status = 'Unpaid' or fees.status = 'Partial'.
Active student means students.status = 'Active'.
Hostel student means student has a row in hostel_allotments.
Club member means student has a row in club_members.
Faculty advisor of a club is faculty.name via clubs.faculty_id = faculty.faculty_id.
Core course means courses.course_type = 'Core'. Elective means courses.course_type = 'Elective'.
To find the department of a student, join students to departments on students.dept_id = departments.dept_id.
To find marks with student name, join marks to students on marks.student_id = students.student_id.
To find marks with course name, join marks to courses on marks.course_id = courses.course_id.
To find which department a course belongs to, join courses to departments on courses.dept_id = departments.dept_id.
Enrollment status 'Completed' means the student finished that course-semester. 'Enrolled' means ongoing.
When asked for average score, use AVG(marks.score). When asked for highest score, use MAX(marks.score).
Gender M means Male students; gender F means Female students.
HOD (head of department) is in departments.hod_name column.
"Topper" means the student with the highest average score in a given group.
