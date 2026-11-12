"""Closed read/draft tools. No BCG/store/approval handles are accepted here."""
from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Literal
from collections.abc import Callable
from types import SimpleNamespace
from uuid import uuid4

import anyio
from pydantic_ai import CallDeferred

from class_os.domain.roster import CreateClass, ChangeClass, ChangeTerm, CreateStudent, ChangeStudentName
from class_os.domain.activity import CreateTask, ChangeTask
from class_os.domain.documents import CreateDocument, ReviseDocument
from class_os.domain.workspace_chat import candidate


@dataclass
class WorkspaceActionCapture:
    user_messages: tuple[str, ...]
    progress_reader: Callable | None = None
    classroom_enabled: bool = False
    proposed: dict | None = None
    reads: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    document_reads: set = field(default_factory=set)
    completed_tools: list[str] = field(default_factory=list)
    clarification: str | None = None
    pending_commands: set[str] = field(default_factory=set)

    def mentioned(self, value):
        return bool(value) and any(value in message for message in self.user_messages)

    def explicit_date(self, value):
        dates = set()
        for message in self.user_messages:
            for year, month, day in re.findall(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", message):
                try:
                    dates.add(date(int(year), int(month), int(day)).isoformat())
                except ValueError:
                    pass
        return value in dates

    def propose(self, command):
        payload = command.canonical()
        candidate(payload)
        if self.proposed is not None:
            raise ValueError("Only one business candidate per turn")
        self.proposed = payload
        return {"status": "uncommitted-candidate", "command": payload,
                "instruction": "Explain the proposed change. It is NOT saved. The user confirms it in the conversation UI."}

    def tools(self, query, credentials, current_memory, emit):
        async def execute(tool, operation):
            current_memory(); emit("tool.started", tool=tool)
            result = await anyio.to_thread.run_sync(operation)
            self.completed_tools.append(tool)
            current_memory(); emit("tool.completed", tool=tool)
            if (self.classroom_enabled and tool.startswith('prepare_') and isinstance(result, dict)
                    and result.get('status') in ('needs-information', 'needs-class-context', 'needs-disambiguation', 'needs-correction-reason')
                    and result.get('question')):
                self.clarification = result['question']
                raise CallDeferred()
            if self.classroom_enabled and isinstance(result, dict) and result.get('status') == 'uncommitted-candidate':
                # Stop the SDK at the existing human-review boundary. There is
                # no reason to ask the model again after a valid candidate.
                raise CallDeferred()
            return result

        def context():
            rows = [SimpleNamespace(**row) for row in query.history(*credentials) if row['status'] == 'active']
            value = rows[0] if len(rows) == 1 else None
            if len(rows) > 1:
                for message in reversed(self.user_messages):
                    matches = [row for row in rows if row.name in message]
                    if matches:
                        narrowed = [row for row in matches if row.term_name in message]
                        selected = narrowed or matches
                        value = selected[0] if len(selected) == 1 else None
                        break
            if value is None:
                return None
            self.reads.append("current-class")
            return value

        missing_class = {"status": "needs-class-context", "question": "要处理哪个班级？", "instruction": "Ask which class to use or offer to prepare its creation. Do not invent a class or ask for a form."}

        async def read_task_progress() -> dict:
            """Read this conversation's recent requests and freshly verified committed or pending actions before continuing a multi-step task. Never writes or treats assistant claims as receipts."""
            def read():
                if self.progress_reader is None:
                    return {"requests": [], "actions": [], "truncated": False}
                history = self.progress_reader()
                actions = []
                self.pending_commands.clear()
                for row in history["turns"]:
                    value = row["candidate"]
                    if row["state"] != "completed" or value is None:
                        continue
                    receipt = row["action_receipt"]
                    if receipt is None:
                        self.pending_commands.add(value['command'])
                    actions.append({"command": value["command"], "name": value.get("name"), "title": value.get("title"),
                        "status": "committed" if receipt else "awaiting-confirmation",
                        "resource_id": str(receipt["resource_id"]) if receipt else None,
                        "version": receipt["version"] if receipt else None})
                requests = [row['user_text'] for row in history['turns'] if row['user_text']]
                original = next((value for value in reversed(requests) if value != '继续完成上面的任务，只处理尚未完成的步骤。'), None)
                recent = requests[-7:]
                if original is not None and original not in recent:
                    recent.insert(0, original)
                return {"requests": recent, 'active_request': original,
                    "actions": actions, "truncated": history["next_before"] is not None,
                    "instruction": "Continue only unfinished requested steps. Re-read current domain data. Pending actions are NOT completed. Stop for human confirmation before the next business change; never repeat a committed creation."}
            return await execute("read_task_progress", read)

        async def read_class_work(kind: Literal["class", "students", "tasks", "documents"] = "class", search: str = "") -> dict:
            """Only when the user's request concerns class data, read current authorized class information. Never writes."""
            def read():
                current = context()
                if current is None:
                    if kind == 'class':
                        rows = query.history(*credentials)
                        return {**missing_class, 'available_classes': [{'name': row['name'], 'term_name': row['term_name']} for row in rows if row['status'] == 'active'][:30]}
                    return missing_class
                if kind == "class":
                    return {"class_name": current.name, "term_name": current.term_name, "version": current.version}
                if kind == "students":
                    rows = query.roster(*credentials, current.class_id, current.term_id)
                    values = [{"name": row.name, "version": row.version} for row in rows if not search or search in row.name]
                elif kind == "tasks":
                    rows = query.projection(*credentials, current.class_id, current.term_id)["tasks"]
                    values = [{"title": row["title"], "status": row["status"], "version": row["version"],
                               "due_at": row["due_at"].isoformat() if row["due_at"] is not None else None,
                               "evidence": row["evidence"], "task_id": str(row["task_id"]),
                               "source_record_id": str(row["source_record_id"]) if row["source_record_id"] else None}
                              for row in rows if not search or search in row["title"]]
                else:
                    rows = query.documents(*credentials, current.class_id, current.term_id)
                    values = [{"title": row["title"], "status": row["status"], "version": row["version"]} for row in rows if not search or search in row["title"]]
                    exact = [row for row in rows if search and row["title"] == search and row["status"] == "draft"]
                    if len(exact) == 1:
                        document = query.document(*credentials, current.class_id, current.term_id, exact[0]["document_id"])
                        if len(document["body"]) <= 10000:
                            self.document_reads.add(document["document_id"])
                        return {"class_name": current.name, "items": values[:30], "current_body": document["body"][:10000], "body_truncated": len(document["body"]) > 10000}
                return {"class_name": current.name, "items": values[:30], "truncated": len(values) > 30}
            return await execute("read_class_work", read)

        async def prepare_class_create(name: str, term_name: str, start_date: str, end_date: str) -> dict:
            """Prepare one class and term creation candidate from explicit user-provided names and dates. Ask for missing information; never saves."""
            def prepare():
                if not self.mentioned(name) or not self.mentioned(term_name) or not self.explicit_date(start_date) or not self.explicit_date(end_date):
                    missing = [label for label, supplied in (('班级名称', self.mentioned(name)), ('学期名称', self.mentioned(term_name)), ('开始日期', self.explicit_date(start_date)), ('结束日期', self.explicit_date(end_date))) if not supplied]
                    return {"status": "needs-information", "question": '请补充' + '、'.join(missing) + '。', "instruction": "Ask for the class name, term name and explicit start/end dates not supplied by the user. Never guess them."}
                if context() is not None:
                    return {"status": "existing-class", "instruction": "An active class already exists; clarify whether the user wants an edit. Do not replace or archive it."}
                return self.propose(CreateClass(uuid4(), uuid4(), name, term_name, date.fromisoformat(start_date), date.fromisoformat(end_date)))
            return await execute("prepare_class_create", prepare)

        async def prepare_class_edit(name: str) -> dict:
            """Prepare renaming the current class, using its freshly read version. Never saves."""
            def prepare():
                current = context()
                if current is None:
                    return missing_class
                if not self.mentioned(name):
                    return {"status": "needs-information", "question": "班级要改成什么名称？", "instruction": "Ask for the desired class name."}
                return self.propose(ChangeClass("class.update", current.class_id, current.term_id, current.version, name))
            return await execute("prepare_class_edit", prepare)

        async def prepare_student(action: Literal["create", "rename"], name: str, new_name: str = "") -> dict:
            """Prepare adding a named student or renaming one uniquely matching current student. Never selects an ambiguous person or saves."""
            def prepare():
                current = context()
                if current is None:
                    return missing_class
                if not self.mentioned(name) or action == "rename" and not self.mentioned(new_name):
                    return {"status": "needs-information", "question": "学生的新姓名是什么？" if self.mentioned(name) else "学生姓名是什么？", "instruction": "Ask for the student's current name and, for a rename, desired new name."}
                rows = query.roster(*credentials, current.class_id, current.term_id)
                matches = [row for row in rows if row.name == name and row.status == "active"]
                if action == "create":
                    if matches:
                        return {"status": "needs-disambiguation", "question": "班里已有这个姓名，是同一位学生吗？", "instruction": "A current student has this name. Clarify whether this is the same person before adding another."}
                    return self.propose(CreateStudent(uuid4(), current.class_id, current.term_id, current.version, name))
                if len(matches) != 1:
                    return {"status": "needs-disambiguation", "question": "没有找到唯一的学生，请确认姓名。", "instruction": "No unique active student matches. Ask the user to clarify; do not guess a person."}
                row = matches[0]
                return self.propose(ChangeStudentName("student.update_name", row.student_id, current.class_id, current.term_id, row.version, row.name, new_name))
            return await execute("prepare_student", prepare)

        async def prepare_term_edit(name: str | None = None, start_date: str | None = None, end_date: str | None = None) -> dict:
            """Prepare correcting current term metadata. Reuse unchanged values; ask only for missing requested changes. Never guesses a date or saves."""
            def prepare():
                current = context()
                if current is None:
                    return missing_class
                if all(value is None for value in (name, start_date, end_date)) or name is not None and not self.mentioned(name) or any(value is not None and not self.explicit_date(value) for value in (start_date, end_date)):
                    return {"status": "needs-information", "question": "请明确要更正的学期名称或日期。", "instruction": "Ask for the requested new term name or explicit changed dates; do not ask for unchanged values."}
                old = query.term_metadata(*credentials, current.class_id, current.term_id)
                return self.propose(ChangeTerm("term.update", current.class_id, current.term_id, old.version,
                    old.name, name or old.name, old.start_date, date.fromisoformat(start_date) if start_date else old.start_date,
                    old.end_date, date.fromisoformat(end_date) if end_date else old.end_date))
            return await execute("prepare_term_edit", prepare)

        async def prepare_task(action: Literal["create", "edit"], title: str, new_title: str = "", status: Literal["not-started", "in-progress", "waiting"] | None = None) -> dict:
            """Prepare creating a task or editing one uniquely matching task title/status. No inferred deadline, student, completion or responsibility; never saves."""
            def prepare():
                current = context()
                if current is None:
                    return missing_class
                if not self.mentioned(title) or new_title and not self.mentioned(new_title):
                    return {"status": "needs-information", "question": "任务的新标题是什么？" if self.mentioned(title) else "要处理哪项任务？", "instruction": "Ask for the exact task title to create or edit."}
                if action == "create":
                    rows = query.projection(*credentials, current.class_id, current.term_id)["tasks"]
                    if any(row["title"] == title for row in rows):
                        return {"status": "existing-task", "instruction": "This task title already exists. Read and reuse it; ask before creating a duplicate."}
                    return self.propose(CreateTask("task.create", uuid4(), current.class_id, current.term_id, title))
                rows = query.projection(*credentials, current.class_id, current.term_id)["tasks"]
                matches = [row for row in rows if row["title"] == title and row["status"] not in ("done", "cancelled")]
                if len(matches) != 1:
                    return {"status": "needs-disambiguation", "question": "没有找到唯一的未完成任务，请确认标题。", "instruction": "No unique open task matches. Ask for clarification."}
                row = matches[0]
                return self.propose(ChangeTask("task.update", row["task_id"], current.class_id, current.term_id, row["version"], status or row["status"], title=new_title or row["title"]))
            return await execute("prepare_task", prepare)

        async def prepare_document(action: Literal["create", "edit"], title: str, body: str, new_title: str = "", format: Literal["plain-text", "markdown"] = "markdown", edit_mode: Literal["replace", "append"] = "replace") -> dict:
            """Prepare a working document or revise one unique title. Read its current body before replacing it, or append without losing old text. Generated prose is unverified. Never saves."""
            def prepare():
                current = context()
                if current is None:
                    return missing_class
                if not self.mentioned(title) or new_title and not self.mentioned(new_title):
                    return {"status": "needs-information", "question": "文档的新标题是什么？" if self.mentioned(title) else "要处理哪份文档？", "instruction": "Ask for the document title. Explain that generated prose needs review."}
                if action == "create":
                    if any(row["title"] == title for row in query.documents(*credentials, current.class_id, current.term_id)):
                        return {"status": "existing-document", "instruction": "This document title already exists. Read and reuse it or ask before creating a duplicate."}
                    return self.propose(CreateDocument(uuid4(), current.class_id, current.term_id, title, body, format))
                matches = [row for row in query.documents(*credentials, current.class_id, current.term_id) if row["title"] == title and row["status"] == "draft"]
                if len(matches) != 1:
                    return {"status": "needs-disambiguation", "question": "没有找到唯一的可编辑文档，请确认标题。", "instruction": "No unique editable document matches. Ask for clarification."}
                row = matches[0]
                existing = query.document(*credentials, current.class_id, current.term_id, row["document_id"])
                if edit_mode == "replace" and existing["body"] and row["document_id"] not in self.document_reads:
                    return {"status": "read-current-document", "instruction": "First call read_class_work(kind='documents', search=the exact title), then prepare the complete edited body. For an append use edit_mode='append'. Never silently lose the old text."}
                revised = existing["body"] + ("\n" if existing["body"] else "") + body if edit_mode == "append" else body
                return self.propose(ReviseDocument(row["document_id"], current.class_id, current.term_id, existing["version"], new_title or title, revised, format))
            return await execute("prepare_document", prepare)

        base = (read_class_work, prepare_class_create, prepare_class_edit, prepare_term_edit, prepare_student, prepare_task, prepare_document, read_task_progress)
        if self.classroom_enabled:
            from .classroom_actions import tools
            from .activity_actions import tools as activity_tools
            activity = activity_tools(self, query, credentials, context, execute, missing_class)
            return tuple(activity[2] if tool is prepare_task else tool for tool in base) + activity[:2] + tools(self, query, credentials, context, execute, missing_class)
        return base
