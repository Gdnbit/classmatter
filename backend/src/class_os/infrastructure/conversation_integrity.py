"""Fixed D1 relational consistency checks, not authorization or restore admission."""
from sqlalchemy import text


def validate_conversation_integrity(connection):
    # These predicates do not return message bodies or execute model content.
    # FK/unique/check constraints cover tuple integrity; these cover the
    # supported aggregate shape which cannot be expressed in a row CHECK.
    broken = connection.execute(text("""SELECT
        EXISTS(SELECT 1 FROM class_os.conversation_thread t
            LEFT JOIN class_os.conversation_control c USING(workspace_id,owner_id) WHERE c.authority_id IS NULL)
        OR EXISTS(SELECT 1 FROM class_os.conversation_turn t
            LEFT JOIN class_os.conversation_run r USING(workspace_id,thread_id,turn_id)
            LEFT JOIN class_os.conversation_message m
                ON m.workspace_id=t.workspace_id AND m.thread_id=t.thread_id AND m.turn_id=t.turn_id AND m.role='user'
            WHERE r.run_id IS NULL OR m.message_id IS NULL)
        OR EXISTS(SELECT 1 FROM class_os.conversation_run r
            LEFT JOIN class_os.conversation_message m
                ON m.workspace_id=r.workspace_id AND m.thread_id=r.thread_id AND m.turn_id=r.turn_id AND m.role='assistant'
            WHERE (r.state='completed' AND m.message_id IS NULL) OR (r.state<>'completed' AND m.message_id IS NOT NULL))
        OR EXISTS(SELECT 1 FROM class_os.conversation_thread t JOIN class_os.conversation_message m USING(workspace_id,thread_id)
            WHERE (t.status='cleared' AND (m.visibility<>'restricted' OR m.body IS NOT NULL))
               OR (t.status<>'cleared' AND m.visibility='restricted'))
        OR EXISTS(SELECT 1 FROM class_os.conversation_thread t JOIN class_os.conversation_run r USING(workspace_id,thread_id)
            WHERE t.status<>'active' AND r.state IN ('queued','running','cancel_requested'))""")).scalar_one()
    if broken is not False:
        raise ValueError("Inconsistent synthetic conversation snapshot")
