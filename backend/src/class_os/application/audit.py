"""Receipt checking only; owning boundaries retain transactions and writers."""
import logging
from uuid import UUID


class AuditUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Durable audit unavailable: missing receipt")


def require_audit(writer, *args):
    try:
        receipt = writer(*args)
        if type(receipt) is not UUID:
            raise AuditUnavailable()
    except Exception:
        # Never retain exception text, payload, identity or scope in the signal.
        # The owning boundary must let this exception roll back its transaction.
        logging.getLogger("class_os.security").error("audit_unavailable kind=audit-unavailable")
        raise AuditUnavailable() from None
    return receipt
