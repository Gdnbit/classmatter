"""Require the original trusted commit audit for four fixed recovery commands."""
from sqlalchemy import text

from class_os.application.roster import CommandRejected, fingerprint


def require_recovery_commit(connection, binding, command, receipt_id, version, not_before):
    payload = command.canonical()
    if payload["command"] not in {"conversation.transfer.seal", "conversation.import.stage",
                                   "conversation.transfer.retire", "conversation.import.admit"}:
        raise CommandRejected()
    rows = connection.execute(text("""SELECT r.committed_at FROM class_os.command_receipt r
        JOIN class_os.command_proposal p USING(proposal_id)
        WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND r.receipt_id=:receipt
          AND r.resource_id=:attempt AND r.resource_version=:version AND r.payload_hash=:hash
          AND p.workspace_id=r.workspace_id AND p.actor_id=r.actor_id AND p.state='committed'
          AND p.command_type=:command AND p.payload_hash=:hash AND p.purpose='exit-recovery'
          AND EXISTS(SELECT 1 FROM class_os.business_audit a
            WHERE a.workspace_id=r.workspace_id AND a.actor_id=r.actor_id
              AND a.action='command.commit' AND a.outcome='allowed' AND a.purpose='exit-recovery'
              AND a.proposal_id=p.proposal_id AND a.receipt_id=r.receipt_id AND a.payload_hash=:hash
              AND a.resource_id=r.resource_id AND a.resource_version=r.resource_version
              AND a.occurred_at=r.committed_at)"""),
        {**binding, "receipt": receipt_id, "attempt": command.attempt_id, "version": version,
         "hash": fingerprint(payload), "command": payload["command"]}).all()
    if len(rows) != 1 or rows[0][0] < not_before:
        raise CommandRejected()
