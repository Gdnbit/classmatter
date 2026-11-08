"""Generate/check only fixed read/candidate tool definitions; no model or DB I/O."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from pydantic_ai import Tool
from class_os.infrastructure.workspace_actions import WorkspaceActionCapture

tools = []
for function in WorkspaceActionCapture(()).tools(None, None, None, None):
    definition = Tool(function).tool_def
    tools.append({key: getattr(definition, key) for key in ("name", "description", "parameters_json_schema", "kind", "strict")})
content = json.dumps({"schema_version": "classmatter.workspace-tools.v1", "tools": tools}, ensure_ascii=False, indent=2) + "\n"
target = Path(__file__).resolve().parents[1] / "contracts/workspace-tools/catalog.v1.json"
if sys.argv[1:] == ["--check"]:
    if not target.exists() or target.read_text(encoding="utf-8") != content:
        raise SystemExit("Workspace tool contract drift")
elif not sys.argv[1:]:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
else:
    raise SystemExit("Only generation or --check is supported")
