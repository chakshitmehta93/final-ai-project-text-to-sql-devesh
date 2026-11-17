# error analysis

> generated from manual review of evaluation failures across systems A-E.

## failure categories

| category | description | count (est.) | system most affected |
|----------|-------------|-------------|----------------------|
| wrong join | wrong table joined or join condition reversed | ~15% | A (no RAG) |
| wrong column | ambiguous column name (name, year, status) used from wrong table | ~20% | A, B |
| bad aggregation | GROUP BY missing or wrong aggregate function | ~18% | A |
| wrong filter | filter value wrong (e.g. dept_name vs dept_code) | ~22% | A, C |
| missing join | forgot to join through intermediate table | ~12% | B |
| over-complex | added unnecessary subquery or DISTINCT | ~8% | all |
| syntax error | LLM produced malformed SQL (unclosed paren etc.) | ~5% | A |

## real failure examples

### example 1 — wrong filter value
**question:** "Show all CSE students"  
**gold:** `SELECT s.name FROM students s JOIN departments d ON s.dept_id=d.dept_id WHERE d.dept_code='CSE'`  
**predicted (system A):** `SELECT name FROM students WHERE dept_id=1`  
**root cause:** without RAG, model guessed dept_id=1 instead of using dept_code='CSE'. Business rule not in context.

---

### example 2 — wrong column reference (ambiguous `name`)
**question:** "Who is the faculty advisor of the Coding Club?"  
**gold:** `SELECT f.name FROM faculty f JOIN clubs c ON f.faculty_id=c.faculty_id WHERE c.club_name='Coding Club'`  
**predicted (system B):** `SELECT name FROM clubs WHERE club_name='Coding Club'`  
**root cause:** `name` column exists in both `students` and `faculty`. Without the FK hint, model picked the wrong table.

---

### example 3 — missing intermediate join
**question:** "Show marks for students in IT department"  
**gold:** `SELECT s.name, m.score FROM students s JOIN departments d ON s.dept_id=d.dept_id JOIN marks m ON s.student_id=m.student_id WHERE d.dept_code='IT'`  
**predicted (system A):** `SELECT student_id, score FROM marks WHERE student_id IN (SELECT student_id FROM students WHERE dept_id=5)`  
**root cause:** used hardcoded dept_id=5 and subquery instead of proper join through departments table.

---

### example 4 — bad aggregation (missing GROUP BY)
**question:** "Average score per department"  
**gold:** `SELECT d.dept_name, AVG(m.score) FROM departments d JOIN students s ON d.dept_id=s.dept_id JOIN marks m ON s.student_id=m.student_id GROUP BY d.dept_id, d.dept_name`  
**predicted (system C):** `SELECT dept_name, AVG(score) FROM departments JOIN marks`  
**root cause:** model skipped the students table that connects departments to marks, producing a cross join.

---

### example 5 — wrong aggregation function
**question:** "Show the highest scorer in each department"  
**gold:** `SELECT d.dept_name, s.name, MAX(m.score) FROM ...`  
**predicted (system A):** `SELECT d.dept_name, s.name, AVG(m.score) FROM ... ORDER BY avg_score DESC LIMIT 1`  
**root cause:** model interpreted "highest scorer" as "highest average" and used LIMIT 1 globally instead of per department.

---

## recommendations
- RAG significantly reduces wrong-filter errors (rule retrieval helps with dept_code vs dept_name)
- Validation loop catches syntax errors and unknown column references reliably
- The main remaining failure mode is semantic misinterpretation of "per department" (needs GROUP BY)
- Fine-tuning on domain-specific examples (see finetune/) is the next step to address aggregation errors
