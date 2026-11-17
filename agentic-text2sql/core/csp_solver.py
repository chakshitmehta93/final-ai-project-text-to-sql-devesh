
"""
CSP Solver for Agentic Text-to-SQL.

Features:
1. Semantic requirement extraction.
2. Schema-based CSP variables and domains.
3. Unary column-existence constraints.
4. Binary foreign-key connectivity constraints.
5. Backtracking search with MRV.
6. Shortest foreign-key JOIN tree.
7. Business-rule filter extraction.
8. Aggregation and calculated-expression planning.
9. Structured plan and constraint trace.

This module produces a structural plan.
It does not generate SQL or replace SQL validation.
"""

import re
from collections import deque


# =========================================================
# 1. SEMANTIC KNOWLEDGE BASE
# =========================================================

# Each concept maps to the columns required to answer it.
# A concept can require MULTIPLE columns.

CONCEPTS = {
    "student_name": {
        "patterns": [
            r"\bstudents?\b",
            r"\bstudent names?\b",
        ],
        "columns": [
            ("students", "name")
        ],
    },

    "course_name": {
        "patterns": [
            r"\bcourses?\b",
            r"\bcourse names?\b",
        ],
        "columns": [
            ("courses", "course_name")
        ],
    },

    "department_name": {
        "patterns": [
            r"\bdepartments?\b",
        ],
        "columns": [
            ("departments", "dept_name")
        ],
    },

    "faculty_name": {
        "patterns": [
            r"\bfaculty\b",
            r"\bfaculties\b",
            r"\bprofessors?\b",
            r"\bteachers?\b",
        ],
        "columns": [
            ("faculty", "name")
        ],
    },

    "marks_score": {
        "patterns": [
            r"\bmarks?\b",
            r"\bscores?\b",
            r"\bscored\b",
            r"\btopper\b",
            r"\bperformance\b",
        ],
        "columns": [
            ("marks", "score")
        ],
    },

    "marks_grade": {
        "patterns": [
            r"\bgrades?\b",
        ],
        "columns": [
            ("marks", "grade")
        ],
    },

    "attendance_percentage": {
        "patterns": [
            r"\battendance\b",
            r"\battended\b",
            r"\battendance percentage\b",
            r"\blow attendance\b",
        ],
        "columns": [
            ("attendance", "attended"),
            ("attendance", "total_classes"),
        ],
    },

    "fee_status": {
        "patterns": [
            r"\bfee defaulters?\b",
            r"\bunpaid fees?\b",
            r"\bfees? pending\b",
            r"\bfees? due\b",
            r"\bpayment status\b",
        ],
        "columns": [
            ("fees", "status")
        ],
    },

    "fee_amount": {
        "patterns": [
            r"\bfee amount\b",
            r"\bfees amount\b",
            r"\bpayment amount\b",
            r"\bamount paid\b",
            r"\bfee details\b",
        ],
        "columns": [
            ("fees", "amount"),
            ("fees", "paid"),
        ],
    },

    "hostel_name": {
        "patterns": [
            r"\bhostels?\b",
        ],
        "columns": [
            ("hostels", "hostel_name")
        ],
    },

    "club_name": {
        "patterns": [
            r"\bclubs?\b",
        ],
        "columns": [
            ("clubs", "club_name")
        ],
    },

    "enrollment_status": {
        "patterns": [
            r"\benrollments?\b",
            r"\benrolled\b",
        ],
        "columns": [
            ("enrollments", "status")
        ],
    },
}


# =========================================================
# 2. BUSINESS RULES
# =========================================================

DEPARTMENT_CODES = {
    "cse": "CSE",
    "computer science": "CSE",
    "me": "ME",
    "mechanical": "ME",
    "ece": "ECE",
    "electronics": "ECE",
    "ce": "CE",
    "civil": "CE",
    "it": "IT",
    "information technology": "IT",
}


# =========================================================
# 3. CSP SOLVER
# =========================================================

class CSPSolver:

    def __init__(self, schema, foreign_keys):

        self.schema = {
            table.lower(): [
                column.lower() for column in columns
            ]
            for table, columns in schema.items()
        }

        self.foreign_keys = foreign_keys

        self.variables = {}
        self.assignment = {}
        self.trace = []

        self.graph = self._build_graph()

    # -----------------------------------------------------
    # BUILD FOREIGN-KEY GRAPH
    # -----------------------------------------------------

    def _build_graph(self):

        graph = {
            table: set()
            for table in self.schema
        }

        for fk in self.foreign_keys:

            source = fk["table"].lower()
            target = fk["ref_table"].lower()

            if source in graph and target in graph:
                graph[source].add(target)
                graph[target].add(source)

        return graph

    # -----------------------------------------------------
    # VARIABLE AND DOMAIN CREATION
    # -----------------------------------------------------

    def _extract_variables(self, question):

        q = re.sub(
            r"[^a-z0-9_ ]",
            " ",
            question.lower()
        )

        q = re.sub(r"\s+", " ", q).strip()

        variables = {}

        for concept, definition in CONCEPTS.items():

            matched = any(
                re.search(pattern, q)
                for pattern in definition["patterns"]
            )

            if not matched:
                continue

            for index, (table, column) in enumerate(
                definition["columns"]
            ):

                if (
                    table not in self.schema
                    or column not in self.schema[table]
                ):
                    continue

                # Every required column becomes its own CSP variable.
                variable = (
                    f"{concept}_{index + 1}"
                    if len(definition["columns"]) > 1
                    else concept
                )

                variables[variable] = [
                    (table, column)
                ]

        return variables

    # -----------------------------------------------------
    # CONNECTIVITY CHECK
    # -----------------------------------------------------

    def _connected(self, table_a, table_b):

        if table_a == table_b:
            return True

        visited = {table_a}
        queue = deque([table_a])

        while queue:

            current = queue.popleft()

            for neighbor in self.graph.get(current, set()):

                if neighbor == table_b:
                    return True

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False

    # -----------------------------------------------------
    # UNARY CONSTRAINT
    # -----------------------------------------------------

    def _unary_constraint(self, variable, value):

        table, column = value

        valid = (
            table in self.schema
            and column in self.schema[table]
        )

        self.trace.append({
            "constraint": "unary",
            "variable": variable,
            "value": f"{table}.{column}",
            "satisfied": valid,
        })

        return valid

    # -----------------------------------------------------
    # BINARY CONSTRAINT
    # -----------------------------------------------------

    def _binary_constraint(self, variable, value):

        table, _ = value

        for other_variable, other_value in (
            self.assignment.items()
        ):

            other_table, _ = other_value

            valid = self._connected(
                table,
                other_table
            )

            self.trace.append({
                "constraint": "binary",
                "variables": [
                    variable,
                    other_variable
                ],
                "tables": [
                    table,
                    other_table
                ],
                "satisfied": valid,
            })

            if not valid:
                return False

        return True

    # -----------------------------------------------------
    # BACKTRACKING WITH MRV
    # -----------------------------------------------------

    def _backtrack(self, remaining):

        if not remaining:
            return True

        # Minimum Remaining Values heuristic.
        variable = min(
            remaining,
            key=lambda v: len(self.variables[v])
        )

        next_remaining = [
            v for v in remaining
            if v != variable
        ]

        for value in self.variables[variable]:

            if not self._unary_constraint(
                variable, value
            ):
                continue

            if not self._binary_constraint(
                variable, value
            ):
                continue

            self.assignment[variable] = value

            self.trace.append({
                "action": "assign",
                "variable": variable,
                "value": value,
            })

            if self._backtrack(next_remaining):
                return True

            self.trace.append({
                "action": "backtrack",
                "variable": variable,
                "value": value,
            })

            del self.assignment[variable]

        return False

    # -----------------------------------------------------
    # SHORTEST FOREIGN-KEY PATH
    # -----------------------------------------------------

    def _shortest_path(self, start, end):

        if start == end:
            return [start]

        queue = deque([[start]])
        visited = {start}

        while queue:

            path = queue.popleft()
            current = path[-1]

            for neighbor in sorted(
                self.graph.get(current, set())
            ):

                if neighbor in visited:
                    continue

                new_path = path + [neighbor]

                if neighbor == end:
                    return new_path

                visited.add(neighbor)
                queue.append(new_path)

        return None

    # -----------------------------------------------------
    # JOIN TREE CONSTRUCTION
    # -----------------------------------------------------

    def _find_join_paths(self, selected_tables):

        required = list(
            dict.fromkeys(selected_tables)
        )

        if len(required) <= 1:
            return {
                "tables": required,
                "edges": []
            }

        connected = {required[0]}
        remaining = set(required[1:])

        edges = []

        while remaining:

            best_path = None

            for source in sorted(connected):

                for target in sorted(remaining):

                    path = self._shortest_path(
                        source,
                        target
                    )

                    if path and (
                        best_path is None
                        or len(path) < len(best_path)
                    ):
                        best_path = path

            if not best_path:
                return None

            for i in range(len(best_path) - 1):

                edge = (
                    best_path[i],
                    best_path[i + 1]
                )

                reverse_edge = (
                    edge[1],
                    edge[0]
                )

                if (
                    edge not in edges
                    and reverse_edge not in edges
                ):
                    edges.append(edge)

            connected.update(best_path)
            remaining = set(required) - connected

        tables = list(dict.fromkeys(
            table
            for edge in edges
            for table in edge
        ))

        return {
            "tables": tables,
            "edges": edges
        }

    # -----------------------------------------------------
    # EXTRACT ONLY SELECTED JOIN CONDITIONS
    # -----------------------------------------------------

    def _get_join_conditions(self, edges):

        conditions = []

        for table_a, table_b in edges:

            found = False

            for fk in self.foreign_keys:

                source = fk["table"].lower()
                target = fk["ref_table"].lower()

                if (
                    source == table_a
                    and target == table_b
                ):

                    conditions.append(
                        f"{source}.{fk['column']} = "
                        f"{target}.{fk['ref_column']}"
                    )

                    found = True
                    break

                if (
                    source == table_b
                    and target == table_a
                ):

                    conditions.append(
                        f"{target}.{fk['column']} = "
                        f"{source}.{fk['ref_column']}"
                    )

                    found = True
                    break

            if not found:
                raise ValueError(
                    f"No FK relationship found: "
                    f"{table_a} <-> {table_b}"
                )

        return conditions

    # -----------------------------------------------------
    # BUSINESS-RULE FILTER EXTRACTION
    # -----------------------------------------------------

    def _extract_filters(self, question):

        q = question.lower()
        filters = []

        # Fee defaulter rule.
        if re.search(
            r"\b(fee defaulter|unpaid fee|fees pending|fees due)\b",
            q
        ):
            filters.append({
                "table": "fees",
                "column": "status",
                "operator": "IN",
                "value": ["Unpaid", "Partial"],
                "rule": "Fee defaulter business rule",
            })

        # Pass/fail rules.
        if "pass" in q:
            filters.append({
                "table": "marks",
                "column": "score",
                "operator": ">=",
                "value": 40,
                "rule": "Pass means marks.score >= 40",
            })

        if "fail" in q:
            filters.append({
                "table": "marks",
                "column": "score",
                "operator": "<",
                "value": 40,
                "rule": "Fail means marks.score < 40",
            })

        # Active student rule.
        if "active student" in q or "active students" in q:
            filters.append({
                "table": "students",
                "column": "status",
                "operator": "=",
                "value": "Active",
                "rule": "Active student business rule",
            })

        # Attendance threshold.
        if "low attendance" in q:
            filters.append({
                "table": "attendance",
                "expression": (
                    "attendance.attended * 100.0 / "
                    "attendance.total_classes"
                ),
                "operator": "<",
                "value": 75,
                "rule": "Low attendance means below 75%",
            })

        # Department code.
        for keyword, code in DEPARTMENT_CODES.items():

            if re.search(
                r"\b" + re.escape(keyword) + r"\b",
                q
            ):

                filters.append({
                    "table": "departments",
                    "column": "dept_code",
                    "operator": "=",
                    "value": code,
                    "rule": "Department code business rule",
                })

                break

        # Numeric score thresholds.
        above = re.search(
            r"(?:above|greater than|more than|over)\s+(\d+(?:\.\d+)?)",
            q
        )

        below = re.search(
            r"(?:below|less than|under)\s+(\d+(?:\.\d+)?)",
            q
        )

        if above:
            filters.append({
                "table": "marks",
                "column": "score",
                "operator": ">",
                "value": float(above.group(1)),
                "rule": "User-specified score threshold",
            })

        if below:
            filters.append({
                "table": "marks",
                "column": "score",
                "operator": "<",
                "value": float(below.group(1)),
                "rule": "User-specified score threshold",
            })

        return filters

    # -----------------------------------------------------
    # AGGREGATION AND EXPRESSION PLANNING
    # -----------------------------------------------------

    def _extract_operations(self, question):

        q = question.lower()

        operations = {
            "aggregations": [],
            "expressions": [],
            "group_by": [],
            "order_by": [],
            "limit": None,
        }

        # Attendance percentage expression.
        if "attendance" in q:

            operations["expressions"].append({
                "name": "attendance_percentage",
                "expression": (
                    "attendance.attended * 100.0 / "
                    "attendance.total_classes"
                ),
            })

        # Average score.
        if (
            "average" in q
            or "avg" in q
            or "overall performance" in q
            or "topper" in q
        ):

            operations["aggregations"].append({
                "function": "AVG",
                "column": "marks.score",
                "alias": "avg_score",
            })

            if "student" in q or "topper" in q:
                operations["group_by"].extend([
                "students.student_id","students.name"])

        # Highest score.
        if "highest score" in q or "maximum score" in q:

            operations["aggregations"].append({
                "function": "MAX",
                "column": "marks.score",
                "alias": "highest_score",
            })

        # Top N.
        top_match = re.search(
            r"\b(?:top|first|limit)\s+(\d+)\b",
            q
        )

        if top_match:

            operations["limit"] = int(
                top_match.group(1)
            )

            operations["order_by"].append({
                "expression": "avg_score",
                "direction": "DESC",
            })

        return operations

    # -----------------------------------------------------
    # MAIN SOLVER
    # -----------------------------------------------------

    def solve(self, question):

        self.trace = []
        self.assignment = {}

        # 1. Extract CSP variables.
        self.variables = self._extract_variables(
            question
        )

        if not self.variables:

            return {
                "success": False,
                "message": (
                    "No supported semantic requirements "
                    "were identified."
                ),
                "variables": {},
                "trace": self.trace,
            }

        # 2. Backtracking search.
        solved = self._backtrack(
            list(self.variables)
        )

        if not solved:

            return {
                "success": False,
                "message": (
                    "No consistent CSP assignment "
                    "was found."
                ),
                "variables": self.variables,
                "trace": self.trace,
            }

        # 3. Selected columns.
        selected_fields = {
            variable: {
                "table": value[0],
                "column": value[1],
            }
            for variable, value in self.assignment.items()
        }

        selected_tables = list(dict.fromkeys(
            value["table"]
            for value in selected_fields.values()
        ))

        # Include tables required by business filters
        # and calculated expressions.
        filters = self._extract_filters(question)
        operations = self._extract_operations(question)

        for item in filters:
            if item.get("table") in self.schema:
                selected_tables.append(item["table"])

        for item in operations["expressions"]:
            table = item["expression"].split(".")[0]
            if table in self.schema:
                selected_tables.append(table)

        selected_tables = list(dict.fromkeys(selected_tables))

        # 4. Validate filter columns.
        for item in filters:

            if "column" in item:

                table = item["table"]
                column = item["column"]

                if (
                    table not in self.schema
                    or column not in self.schema[table]
                ):

                    return {
                        "success": False,
                        "message": (
                            f"Invalid business-rule field: "
                            f"{table}.{column}"
                        ),
                        "variables": self.assignment,
                        "trace": self.trace,
                    }

        # 5. Construct JOIN tree.
        join_path = self._find_join_paths(
            selected_tables
        )

        if join_path is None:

            return {
                "success": False,
                "message": (
                    "Selected tables do not have "
                    "a valid FK connection."
                ),
                "variables": self.assignment,
                "trace": self.trace,
            }

        # 6. Construct final plan.
        plan = {

            "selected_fields": selected_fields,

            "selected_tables": selected_tables,

            "join_tables": join_path["tables"],

            "join_relationships": (
                self._get_join_conditions(
                    join_path["edges"]
                )
            ),

            "filters": filters,

            "operations": operations,
        }

        return {
            "success": True,
            "message": "CSP solution found.",
            "variables": self.variables,
            "plan": plan,
            "trace": self.trace,
        }
