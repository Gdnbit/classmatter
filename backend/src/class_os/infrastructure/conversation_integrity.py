"""Fixed D1 relational consistency checks, not authorization or restore admission."""
from sqlalchemy import text

from .conversation_restrictions import RestrictionHead, RestrictionSnapshot


def restriction_head(connection, workspace_id):
    rows = connection.execute(text("""SELECT workspace_id,authority_id,epoch,head_hash
        FROM class_os.conversation_control ORDER BY workspace_id LIMIT 2""")).mappings().all()
    if len(rows) != 1 or rows[0]["workspace_id"] != workspace_id:
        raise ValueError("Invalid restriction anchor")
    row = rows[0]
    return RestrictionHead(row["authority_id"], row["workspace_id"], row["epoch"], row["head_hash"])


def validate_restriction_snapshot(connection, snapshot):
    """Fixed metadata-only relation check; never a freshness/activation grant."""
    if type(snapshot) is not RestrictionSnapshot or restriction_head(connection, snapshot.head.workspace_id) != snapshot.head:
        raise ValueError("Restriction evidence mismatch")
    rows = connection.execute(text("""SELECT workspace_id,thread_id,title,status,version,cleared_at,updated_at
        FROM class_os.conversation_thread ORDER BY thread_id LIMIT 10001""")).mappings().all()
    if len(rows) > 10000:
        raise ValueError("Restriction snapshot too large")
    markers = {marker.thread_id: marker for marker in snapshot.markers}
    seen = set()
    for row in rows:
        marker = markers.get(row["thread_id"])
        if row["workspace_id"] != snapshot.head.workspace_id:
            raise ValueError("Restriction scope mismatch")
        if row["status"] == "cleared":
            if (marker is None or row["version"] != marker.version_after or row["cleared_at"] != marker.restricted_at
                    or row["updated_at"] < marker.restricted_at or row["title"] != "已清除的会话"):
                raise ValueError("Restriction row mismatch")
        elif marker is not None or row["cleared_at"] is not None:
            raise ValueError("Restriction row mismatch")
        seen.add(row["thread_id"])
    if not markers.keys() <= seen:
        raise ValueError("Orphan restriction marker")
    validate_conversation_integrity(connection)


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
    result_broken = connection.execute(text("""SELECT
        EXISTS(SELECT 1 FROM class_os.conversation_query_source s
            JOIN class_os.conversation_message m USING(workspace_id,thread_id,turn_id,message_id)
            JOIN class_os.conversation_turn t USING(workspace_id,thread_id,turn_id)
            JOIN class_os.conversation_run r USING(workspace_id,thread_id,turn_id)
            WHERE m.role<>'assistant' OR t.mode<>'read' OR r.state<>'completed'
                OR s.created_at<>m.created_at OR s.created_at<>r.ended_at
                OR s.as_of<r.started_at OR s.as_of>r.ended_at)
        OR EXISTS(SELECT 1 FROM class_os.conversation_task_draft d
            JOIN class_os.conversation_message m USING(workspace_id,thread_id,turn_id,message_id)
            JOIN class_os.conversation_turn t USING(workspace_id,thread_id,turn_id)
            JOIN class_os.conversation_run r USING(workspace_id,thread_id,turn_id)
            JOIN class_os.conversation_thread c USING(workspace_id,thread_id)
            WHERE m.role<>'assistant' OR t.mode<>'draft' OR t.draft_kind<>'task' OR c.student_id IS NOT NULL
                OR r.state<>'completed' OR d.created_at<>m.created_at OR d.created_at<>r.ended_at OR d.visibility<>m.visibility)
        OR EXISTS(SELECT 1 FROM class_os.conversation_query_source
            GROUP BY workspace_id,thread_id,turn_id,message_id HAVING min(ordinal)<>1 OR max(ordinal)<>count(*))""")).scalar_one()
    if result_broken is not False:
        raise ValueError("Inconsistent fixed historical result relations")
