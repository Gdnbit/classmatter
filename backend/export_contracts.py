"""Generate or --check the versioned contract snapshots; no runtime business I/O."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from class_os.interfaces.http.contracts import ErrorResponse, LiveResponse, ReadyResponse
from class_os.interfaces.http.identity_contracts import IdentityChallenge, IdentitySession, IdentityKitSession, IdentitySignedOut
from class_os.interfaces.http.identity_contracts import IdentityLogoutBody, IdentityLogoutReceipt
from class_os.interfaces.http.identity_contracts import IdentityOperationReceipt
from class_os.interfaces.http.agent import TurnBody, ConversationResponse, QueryReceiptReference
from class_os.interfaces.http.agent import ScopedConversationBody, ScopedConversationResponse
from class_os.interfaces.http.agent import RecordNoteTurnBody, RecordNoteCandidateResponse
from class_os.application.agent_tool_contracts import catalog
from class_os.interfaces.operator.support import SupportReport
from class_os.interfaces.http.model_configuration import ModelConfigurationBody, ModelConfigurationResponse, ModelStaged, ModelStageBody, ModelStatus, ModelTestBody, ModelEnableBody
from class_os.interfaces.http.exit_package import ExitPackageResponse
from class_os.interfaces.http.roster import (ApprovalBody, ClassBody, CommitBody, ContextResponse,
                                            PreviewResponse, ReceiptResponse, RosterResponse, StudentBody, StudentNameBody, TermBody, TermMetadataResponse,
                                            ActivityResponse, HistoryResponse, IdentifierResponse, DuplicateResponse, AuditResponse, CommandStatusResponse)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "contracts/http"
    for name, model in [("health-live.v1", LiveResponse), ("health-ready.v1", ReadyResponse), ("error.v1", ErrorResponse),
                        ("identity-challenge.v1", IdentityChallenge), ("identity-session.v1", IdentitySession),
                        ("identity-kit-session.v1", IdentityKitSession), ("identity-signed-out.v1", IdentitySignedOut),
                        ("identity-logout-body.v1", IdentityLogoutBody), ("identity-logout-receipt.v1", IdentityLogoutReceipt),
                        ("identity-operation-receipt.v1", IdentityOperationReceipt),
                        ("roster-class-create.v1", ClassBody), ("roster-student-create.v1", StudentBody),
                        ("roster-student-name.v1", StudentNameBody),
                        ("roster-term-update.v1", TermBody), ("term-metadata.v1", TermMetadataResponse),
                        ("roster-approve.v1", ApprovalBody), ("roster-commit.v1", CommitBody),
                        ("roster-preview.v1", PreviewResponse), ("roster-receipt.v1", ReceiptResponse), ("command-status.v1", CommandStatusResponse),
                        ("roster-context.v1", ContextResponse), ("roster-list.v1", RosterResponse),
                        ("activity.v1", ActivityResponse), ("class-history.v1", HistoryResponse), ("business-audit.v1", AuditResponse),
                        ("identifier-list.v1", IdentifierResponse), ("duplicate-list.v1", DuplicateResponse),
                        ("agent-turn.v1", TurnBody), ("agent-conversation.v1", ConversationResponse),
                        ("agent-conversation-body.v2", ScopedConversationBody), ("agent-conversation.v2", ScopedConversationResponse),
                        ("agent-record-note-turn.v1", RecordNoteTurnBody), ("agent-record-note-candidate.v1", RecordNoteCandidateResponse),
                        ("model-configuration-body.v1", ModelConfigurationBody), ("model-configuration.v1", ModelConfigurationResponse),
                        ("model-status.v1", ModelStatus), ("model-staged.v1", ModelStaged), ("model-stage-body.v1", ModelStageBody),
                        ("model-test-body.v1", ModelTestBody), ("model-enable-body.v1", ModelEnableBody),
                        ("synthetic-core-exit.v1", ExitPackageResponse), ("agent-query-source.v1", QueryReceiptReference)]:
        target = root / f"{name}.schema.json"
        content = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Contract drift: {target.name}")
        else:
            root.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
    tools_root = root.parent / "tools"
    support_target = root.parent / "operator" / "support.v1.schema.json"
    support_content = json.dumps(SupportReport.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not support_target.exists() or support_target.read_text(encoding="utf-8") != support_content:
            raise SystemExit("Operator support contract drift")
    else:
        support_target.parent.mkdir(exist_ok=True)
        support_target.write_text(support_content, encoding="utf-8", newline="\n")
    for item in catalog():
        target = tools_root / (item["name"].replace("_", "-") + ".v1.json")
        content = json.dumps(item, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Tool contract drift: {target.name}")
        else:
            tools_root.mkdir(exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
