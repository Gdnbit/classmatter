"""Post-R1 classroom pack policy, reusing the original QG/BCG."""
from dataclasses import dataclass
from uuid import UUID
from class_os.domain.risk import Risk
from .roster import QueryGateway, CommandRejected


@dataclass(frozen=True)
class ClassroomDecision:
    level: Risk = Risk.W2
    admitted: bool = True
    requires_approval: bool = True
    policy_version: str = 'd4-classroom-work.v1'


class ClassroomQueries(QueryGateway):
    @staticmethod
    def audit_purpose(action):
        return 'manage-class' if action in ('exam.list', 'exam.read', 'seat.read') else QueryGateway.audit_purpose(action)

    def classroom_read(self, credentials, class_id, term_id, *, exam_id=None, seating=False):
        if (self.store.database.profile != 'classroom-work-d4' or type(class_id) is not UUID or type(term_id) is not UUID
                or exam_id is not None and type(exam_id) is not UUID or type(seating) is not bool):
            raise CommandRejected()
        action = 'seat.read' if seating else 'exam.read' if exam_id else 'exam.list'
        def read(tx, binding, now):
            return tx.read_seating(binding, class_id, term_id) if seating else tx.read_exams(binding, class_id, term_id, exam_id)
        return self._run(credentials, action, read, class_id=class_id, term_id=term_id, resource_id=exam_id or class_id)
