"""Deterministic validators shared by the existing Business Command Gateway."""
from class_os.domain.activity import CreateRecord, ReviseRecord, CreateTask, ChangeTask, OPEN_STATES, LEAVE_PREDECESSORS
from class_os.domain.roster import ChangeClass, ChangeTerm, ChangeStudentName, DeactivateStudent, UpdateIdentifier
from class_os.domain.risk import Assessment, Command, DataClass, evaluate


def validate_activity(tx, binding, command, now):
    if type(command) not in (ChangeClass, ChangeTerm, ChangeStudentName, DeactivateStudent, UpdateIdentifier,
                             CreateRecord, ReviseRecord, CreateTask, ChangeTask):
        return False
    workspace = binding["workspace_id"]
    context = tx.class_context(workspace, command.class_id, command.term_id)
    if not context or context["status"] != "active" or context["term_status"] != "active":
        return False
    if type(command) is ChangeClass:
        return context["version"] == command.expected_version
    if type(command) is ChangeTerm:
        current = tx.term_metadata(workspace, command.class_id, command.term_id)
        return bool(current and current.version == command.expected_version
                    and current.name == command.previous_name and current.start_date == command.previous_start_date
                    and current.end_date == command.previous_end_date)
    if type(command) in (ChangeStudentName, DeactivateStudent, UpdateIdentifier):
        student = tx.active_student(workspace, command.class_id, command.term_id, command.student_id, now)
        if not student or student["version"] != command.expected_version:
            return False
        if type(command) is ChangeStudentName:
            return student["name"] == command.previous_name
        if type(command) is UpdateIdentifier:
            if command.supersedes_identifier_id:
                previous = tx.identifier(workspace, command.supersedes_identifier_id)
                if (not previous or previous["student_id"] != command.student_id
                        or previous["authority"] != command.authority or previous["identifier_type"] != command.identifier_type
                        or previous["valid_to"] is not None or previous["valid_from"] >= command.valid_from
                        or command.valid_from > now or previous["value"] == command.value):
                    return False
            return not tx.identifier_overlap(workspace, command)
        return now > student["valid_from"]
    if type(command) is CreateRecord:
        if (command.occurred_at > now or not tx.active_student(workspace, command.class_id, command.term_id, command.student_id, now)
                or tx.latest_record(workspace, command.class_id, command.term_id, command.record_id)):
            return False
        if command.related_record_id:
            previous = tx.latest_record(workspace, command.class_id, command.term_id, command.related_record_id)
            if not previous or previous["student_id"] != command.student_id:
                return False
            if command.kind in LEAVE_PREDECESSORS and (previous["kind"] != LEAVE_PREDECESSORS[command.kind] or previous["occurred_at"] > command.occurred_at):
                return False
        return True
    if type(command) is ReviseRecord:
        previous = tx.latest_record(workspace, command.class_id, command.term_id, command.record_id)
        if not previous or previous["version"] != command.expected_version:
            return False
        if previous["kind"] == "teacher_observation":
            return not command.fact_text and bool(command.observation_text.strip())
        return bool(command.fact_text.strip())
    if type(command) is CreateTask:
        if tx.task(workspace, command.class_id, command.term_id, command.task_id):
            return False
        if command.student_id and not tx.active_student(workspace, command.class_id, command.term_id, command.student_id, now):
            return False
        if command.source_record_id:
            record = tx.latest_record(workspace, command.class_id, command.term_id, command.source_record_id)
            if not record or (command.student_id is not None and record["student_id"] != command.student_id):
                return False
        return True
    if type(command) is ChangeTask:
        previous = tx.task(workspace, command.class_id, command.term_id, command.task_id)
        return bool(previous and previous["version"] == command.expected_version and previous["status"] in OPEN_STATES
                    and (previous["status"] != command.status
                         or command.title is not None and previous["title"] != command.title
                         or command.change_due_date and previous["due_at"] != command.due_at))
    return False


def decision(tx, binding, command):
    kind = command.kind if type(command) is CreateRecord else None
    if type(command) is ReviseRecord:
        record = tx.latest_record(binding["workspace_id"], command.class_id, command.term_id, command.record_id)
        kind = record["kind"] if record else None
    category = "discipline" if kind == "discipline_fact" else "conversation" if kind == "conversation_fact" else "ordinary" if kind else None
    sensitive = kind in ("discipline_fact", "conversation_fact")
    source = command.source_record_id if type(command) is CreateTask else None
    if type(command) is ChangeTask:
        task = tx.task(binding["workspace_id"], command.class_id, command.term_id, command.task_id)
        source = task["source_record_id"] if task else None
    if source:
        record = tx.latest_record(binding["workspace_id"], command.class_id, command.term_id, source)
        sensitive = bool(record and record["kind"] in ("discipline_fact", "conversation_fact"))
    return evaluate(Assessment(Command(command.canonical()["command"]), data_class=DataClass.D3 if sensitive else DataClass.D2, record_kind=category))
