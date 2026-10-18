"""Fixed SQL transaction methods consumed only by the BCG/QG adapter."""
from uuid import uuid4

from sqlalchemy import text

from class_os.domain.activity import CreateRecord, ReviseRecord, CreateTask, ChangeTask
from class_os.domain.roster import ChangeClass, ChangeTerm, ChangeStudentName, DeactivateStudent, UpdateIdentifier, Receipt


class ActivityTransaction:
    def active_student(self, workspace, class_id, term_id, student_id, now):
        return self._connection.execute(text("""SELECT s.student_id,s.name,s.version,e.valid_from FROM class_os.student s JOIN class_os.enrollment e
            ON e.workspace_id=s.workspace_id AND e.student_id=s.student_id WHERE s.workspace_id=:w AND s.student_id=:s
            AND e.class_id=:c AND e.term_id=:t AND s.status='active' AND e.status='active'
            AND e.valid_from<=:now AND (e.valid_to IS NULL OR :now<e.valid_to)"""),
            {"w": workspace, "c": class_id, "t": term_id, "s": student_id, "now": now}).mappings().one_or_none()

    def identifier_overlap(self, workspace, command):
        return self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.student_identifier
            WHERE workspace_id=:w AND (CAST(:replaced AS uuid) IS NULL OR identifier_id<>:replaced)
            AND (identifier_id=:id OR (student_id=:s AND authority=:a AND identifier_type=:type
            AND (valid_to IS NULL OR :start<valid_to) AND (CAST(:end AS timestamptz) IS NULL OR valid_from<:end))))"""),
            {"w": workspace, "id": command.identifier_id, "s": command.student_id, "a": command.authority,
             "type": command.identifier_type, "start": command.valid_from, "end": command.valid_to,
             "replaced": command.supersedes_identifier_id}).scalar_one()

    def identifier(self, workspace, identifier_id):
        return self._connection.execute(text("""SELECT identifier_id,student_id,authority,identifier_type,value,valid_from,valid_to
            FROM class_os.student_identifier WHERE workspace_id=:w AND identifier_id=:id"""),
            {"w": workspace, "id": identifier_id}).mappings().one_or_none()

    def latest_record(self, workspace, class_id, term_id, record_id):
        return self._connection.execute(text("""SELECT * FROM class_os.record_revision WHERE workspace_id=:w
            AND class_id=:c AND term_id=:t AND record_id=:id ORDER BY version DESC LIMIT 1"""),
            {"w": workspace, "c": class_id, "t": term_id, "id": record_id}).mappings().one_or_none()

    def task(self, workspace, class_id, term_id, task_id):
        return self._connection.execute(text("""SELECT * FROM class_os.manual_task WHERE workspace_id=:w
            AND class_id=:c AND term_id=:t AND task_id=:id"""),
            {"w": workspace, "c": class_id, "t": term_id, "id": task_id}).mappings().one_or_none()

    def apply_activity(self, binding, command, now):
        values = {**binding, **command.canonical(), "now": now}
        # The canonical union is closed by domain decoding; identifiers/times
        # are rebound as typed parameters, never interpolated into SQL.
        for field in ("class_id", "term_id", "student_id", "record_id", "task_id", "identifier_id", "related_record_id", "source_record_id", "occurred_at", "due_at", "valid_from", "valid_to"):
            if hasattr(command, field):
                values[field] = getattr(command, field)
        if type(command) is ChangeClass:
            self._mutate(text("""UPDATE class_os.school_class SET name=:name,status=:status,version=version+1,
                updated_by=:actor_id,updated_at=:now WHERE workspace_id=:workspace_id AND class_id=:class_id"""),
                {**values, "status": "archived" if command.command == "class.archive" else "active"})
            if command.command == "class.archive":
                self._mutate(text("""UPDATE class_os.academic_term SET status='archived',version=version+1,
                    updated_by=:actor_id,updated_at=:now WHERE workspace_id=:workspace_id AND term_id=:term_id"""), values)
            return Receipt(uuid4(), command.class_id, command.expected_version + 1)
        if type(command) is ChangeTerm:
            # The BCG already owns the business lock and revalidated both
            # aggregates. SQL still binds scope, active parent and the full CAS.
            values.update(start_date=command.start_date, end_date=command.end_date,
                          previous_start_date=command.previous_start_date, previous_end_date=command.previous_end_date)
            self._mutate(text("""UPDATE class_os.academic_term SET name=:name,start_date=:start_date,end_date=:end_date,
                version=version+1,updated_by=:actor_id,updated_at=:now
                WHERE workspace_id=:workspace_id AND term_id=:term_id AND status='active'
                AND version=:expected_version AND name=:previous_name
                AND start_date=:previous_start_date AND end_date=:previous_end_date
                AND EXISTS(SELECT 1 FROM class_os.school_class c WHERE c.workspace_id=:workspace_id
                    AND c.class_id=:class_id AND c.term_id=:term_id AND c.status='active')
                RETURNING term_id"""), values).scalar_one()
            return Receipt(uuid4(), command.term_id, command.expected_version + 1)
        if type(command) is ChangeStudentName:
            self._mutate(text("""UPDATE class_os.student SET name=:name,version=version+1,updated_by=:actor_id,
                updated_at=:now WHERE workspace_id=:workspace_id AND student_id=:student_id
                AND version=:expected_version AND name=:previous_name AND status='active'
                RETURNING student_id"""), values).scalar_one()
            return Receipt(uuid4(), command.student_id, command.expected_version + 1)
        if type(command) is DeactivateStudent:
            self._mutate(text("""UPDATE class_os.student SET status='inactive',version=version+1,updated_by=:actor_id,
                updated_at=:now WHERE workspace_id=:workspace_id AND student_id=:student_id"""), values)
            self._mutate(text("""UPDATE class_os.enrollment SET status='inactive',valid_to=:now,version=version+1,
                updated_by=:actor_id,updated_at=:now WHERE workspace_id=:workspace_id AND student_id=:student_id
                AND status='active' AND valid_to IS NULL"""), values)
            return Receipt(uuid4(), command.student_id, command.expected_version + 1)
        if type(command) is UpdateIdentifier:
            if command.supersedes_identifier_id:
                self._mutate(text("""UPDATE class_os.student_identifier SET valid_to=:valid_from
                    WHERE workspace_id=:workspace_id AND identifier_id=:previous AND valid_to IS NULL
                    RETURNING identifier_id"""), {**values, "previous": command.supersedes_identifier_id}).scalar_one()
            self._mutate(text("""INSERT INTO class_os.student_identifier
                (workspace_id,identifier_id,student_id,authority,identifier_type,value,valid_from,valid_to,created_by,created_at)
                VALUES(:workspace_id,:identifier_id,:student_id,:authority,:identifier_type,:value,:valid_from,:valid_to,:actor_id,:now)"""), values)
            self._mutate(text("""UPDATE class_os.student SET version=version+1,updated_by=:actor_id,updated_at=:now
                WHERE workspace_id=:workspace_id AND student_id=:student_id"""), values)
            return Receipt(uuid4(), command.student_id, command.expected_version + 1)
        if type(command) in (CreateRecord, ReviseRecord):
            if type(command) is CreateRecord:
                values.update(version=1, revision_kind="create", revision_reason="")
            else:
                previous = self.latest_record(binding["workspace_id"], command.class_id, command.term_id, command.record_id)
                values.update(student_id=previous["student_id"], kind=previous["kind"], occurred_at=previous["occurred_at"],
                              related_record_id=previous["related_record_id"], version=command.expected_version + 1,
                              revision_kind=command.command.split(".")[1], revision_reason=command.reason)
            self._mutate(text("""INSERT INTO class_os.record_revision
                (workspace_id,record_id,version,class_id,term_id,student_id,kind,occurred_at,recorded_at,recorded_by,
                 fact_text,observation_text,source,related_record_id,revision_kind,revision_reason)
                VALUES(:workspace_id,:record_id,:version,:class_id,:term_id,:student_id,:kind,:occurred_at,:now,:actor_id,
                       :fact_text,:observation_text,'trusted-ui-synthetic',:related_record_id,:revision_kind,:revision_reason)"""), values)
            return Receipt(uuid4(), command.record_id, values["version"])
        if type(command) is CreateTask:
            self._mutate(text("""INSERT INTO class_os.manual_task
                (workspace_id,task_id,class_id,term_id,title,student_id,source_record_id,due_at,status,evidence,version,
                 created_by,updated_by,created_at,updated_at)
                VALUES(:workspace_id,:task_id,:class_id,:term_id,:title,:student_id,:source_record_id,:due_at,'not-started','',1,
                       :actor_id,:actor_id,:now,:now)"""), values)
            return Receipt(uuid4(), command.task_id, 1)
        if type(command) is ChangeTask:
            values.update(new_title=command.title, due_at=command.due_at, change_due=command.change_due_date)
            self._mutate(text("""UPDATE class_os.manual_task SET status=:status,evidence=:evidence,version=version+1,
                title=COALESCE(:new_title,title),due_at=CASE WHEN :change_due THEN :due_at ELSE due_at END,
                updated_by=:actor_id,updated_at=:now WHERE workspace_id=:workspace_id AND task_id=:task_id"""), values)
            return Receipt(uuid4(), command.task_id, command.expected_version + 1)
        raise ValueError("Unregistered activity mutation")

    def class_history(self, workspace):
        return tuple(dict(row) for row in self._connection.execute(text("""SELECT c.class_id,c.term_id,c.name,t.name AS term_name,c.version,c.status
            FROM class_os.school_class c JOIN class_os.academic_term t ON c.workspace_id=t.workspace_id AND c.term_id=t.term_id
            WHERE c.workspace_id=:w ORDER BY c.created_at DESC,c.class_id"""), {"w": workspace}).mappings())

    def identifier_list(self, workspace, class_id, term_id):
        return tuple(dict(row) for row in self._connection.execute(text("""SELECT i.identifier_id,i.student_id,i.authority,i.identifier_type,
            i.value,i.valid_from,i.valid_to FROM class_os.student_identifier i WHERE i.workspace_id=:w
            AND EXISTS(SELECT 1 FROM class_os.enrollment e WHERE e.workspace_id=i.workspace_id AND e.student_id=i.student_id
            AND e.class_id=:c AND e.term_id=:t) ORDER BY i.student_id,i.authority,i.identifier_id"""),
            {"w": workspace, "c": class_id, "t": term_id}).mappings())

    def duplicate_list(self, workspace, class_id, term_id, now):
        return tuple(dict(row) for row in self._connection.execute(text("""SELECT DISTINCT a.student_id AS left_student_id,
            b.student_id AS right_student_id,'identifier_conflict' AS reason FROM class_os.student_identifier a
            JOIN class_os.student_identifier b ON a.workspace_id=b.workspace_id AND a.authority=b.authority
            AND a.identifier_type=b.identifier_type AND a.value=b.value AND a.student_id<b.student_id
            JOIN class_os.enrollment ea ON ea.workspace_id=a.workspace_id AND ea.student_id=a.student_id
            JOIN class_os.enrollment eb ON eb.workspace_id=b.workspace_id AND eb.student_id=b.student_id
            WHERE a.workspace_id=:w AND ea.class_id=:c AND ea.term_id=:t AND eb.class_id=:c AND eb.term_id=:t
            AND a.valid_from<=:now AND b.valid_from<=:now AND (a.valid_to IS NULL OR :now<a.valid_to)
            AND (b.valid_to IS NULL OR :now<b.valid_to) ORDER BY left_student_id,right_student_id"""),
            {"w": workspace, "c": class_id, "t": term_id, "now": now}).mappings())

    def activity(self, workspace, class_id, term_id, now, *, student_id=None):
        values = {"w": workspace, "c": class_id, "t": term_id, "now": now, "s": student_id}
        records = tuple(dict(row) for row in self._connection.execute(text("""SELECT record_id,version,student_id,kind,
            occurred_at,recorded_at,fact_text,observation_text,source,related_record_id,revision_kind,revision_reason
            FROM class_os.record_revision WHERE workspace_id=:w AND class_id=:c AND term_id=:t
            AND (CAST(:s AS uuid) IS NULL OR student_id=:s) ORDER BY occurred_at DESC,record_id,version DESC"""), values).mappings())
        tasks = tuple(dict(row) for row in self._connection.execute(text("""SELECT task_id,title,student_id,source_record_id,due_at,status,evidence,version,
            (status NOT IN ('done','cancelled') AND due_at<:now) IS TRUE AS overdue
            FROM class_os.manual_task WHERE workspace_id=:w AND class_id=:c AND term_id=:t
            AND (CAST(:s AS uuid) IS NULL OR student_id=:s) ORDER BY due_at NULLS LAST,created_at,task_id"""), values).mappings())
        return {"as_of": now, "records": records, "tasks": tasks}
