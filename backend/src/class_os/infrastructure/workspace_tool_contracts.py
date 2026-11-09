"""Read the reviewed, fixed workspace tool snapshot; never registers callables."""
import json
from pathlib import Path

NAMES = ("read_class_work", "prepare_class_create", "prepare_class_edit", "prepare_term_edit", "prepare_student", "prepare_task", "prepare_document", "read_task_progress")


def catalog(classroom=False):
    if type(classroom) is not bool:
        raise ValueError('Explicit tool profile required')
    path = Path(__file__).resolve().parents[4] / "contracts" / ("classroom-tools" if classroom else "workspace-tools") / "catalog.v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if (type(value) is not dict or set(value) != {"schema_version", "tools"}
            or value["schema_version"] != ("classmatter.classroom-tools.v1" if classroom else "classmatter.workspace-tools.v1")
            or tuple(item["name"] for item in value["tools"]) != NAMES + (("read_classroom_work", "prepare_exam", "prepare_score", "prepare_seat_layout", "prepare_seat_assignment", "prepare_seat_swap") if classroom else ())):
        raise ValueError("Workspace tool snapshot mismatch")
    return tuple(value["tools"])
