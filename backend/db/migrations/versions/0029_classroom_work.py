"""Opt-in classroom work pack; frozen R1/D1/D2/D3 targets stay unchanged."""
from alembic import op
from sqlalchemy import inspect

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.class_exam (
      workspace_id uuid NOT NULL, exam_id uuid NOT NULL, owner_id uuid NOT NULL,
      class_id uuid NOT NULL, term_id uuid NOT NULL,
      title varchar(80) NOT NULL CHECK(title=btrim(title) AND title<>'' AND title !~ '[[:cntrl:]]'),
      subject varchar(80) NOT NULL CHECK(subject=btrim(subject) AND subject<>'' AND subject !~ '[[:cntrl:]]'),
      maximum_score numeric(8,2) NOT NULL CHECK(maximum_score>0 AND maximum_score<=999999.99),
      version integer NOT NULL CHECK(version>0), created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      updated_at timestamptz NOT NULL CHECK(isfinite(updated_at) AND updated_at>=created_at),
      PRIMARY KEY(workspace_id,exam_id), UNIQUE(workspace_id,exam_id,class_id,term_id),
      UNIQUE(workspace_id,class_id,term_id,title,subject),
      FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
      FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id)
    );
    CREATE TABLE class_os.exam_result_revision (
      workspace_id uuid NOT NULL, exam_id uuid NOT NULL, class_id uuid NOT NULL, term_id uuid NOT NULL,
      student_id uuid NOT NULL, enrollment_id uuid NOT NULL, version integer NOT NULL CHECK(version>0),
      status varchar(16) NOT NULL CHECK(status IN ('scored','absent','exempt','not-recorded')),
      score numeric(8,2) CHECK(score>=0 AND score<=999999.99),
      reason varchar(500) NOT NULL CHECK(reason !~ '[[:cntrl:]]' AND (version=1 OR btrim(reason)<>'')),
      created_by uuid NOT NULL, created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,exam_id,student_id,version),
      CHECK((status='scored')=(score IS NOT NULL)),
      FOREIGN KEY(workspace_id,exam_id,class_id,term_id) REFERENCES class_os.class_exam(workspace_id,exam_id,class_id,term_id),
      FOREIGN KEY(workspace_id,class_id,term_id,student_id,enrollment_id)
        REFERENCES class_os.enrollment(workspace_id,class_id,term_id,student_id,enrollment_id),
      FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE TABLE class_os.class_seating (
      workspace_id uuid NOT NULL, layout_id uuid NOT NULL, owner_id uuid NOT NULL,
      class_id uuid NOT NULL, term_id uuid NOT NULL, rows integer NOT NULL CHECK(rows BETWEEN 1 AND 20),
      columns integer NOT NULL CHECK(columns BETWEEN 1 AND 20), version integer NOT NULL CHECK(version>0),
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      updated_at timestamptz NOT NULL CHECK(isfinite(updated_at) AND updated_at>=created_at),
      PRIMARY KEY(workspace_id,layout_id), UNIQUE(workspace_id,layout_id,class_id,term_id),
      UNIQUE(workspace_id,class_id,term_id),
      FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
      FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id)
    );
    CREATE TABLE class_os.seat_revision (
      workspace_id uuid NOT NULL, layout_id uuid NOT NULL, class_id uuid NOT NULL, term_id uuid NOT NULL,
      version integer NOT NULL CHECK(version>0), row_index integer NOT NULL CHECK(row_index BETWEEN 1 AND 20),
      column_index integer NOT NULL CHECK(column_index BETWEEN 1 AND 20), student_id uuid, enrollment_id uuid,
      created_by uuid NOT NULL, created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      PRIMARY KEY(workspace_id,layout_id,version,row_index,column_index),
      UNIQUE(workspace_id,layout_id,version,student_id),
      CHECK((student_id IS NULL)=(enrollment_id IS NULL)),
      FOREIGN KEY(workspace_id,layout_id,class_id,term_id) REFERENCES class_os.class_seating(workspace_id,layout_id,class_id,term_id),
      FOREIGN KEY(workspace_id,class_id,term_id,student_id,enrollment_id)
        REFERENCES class_os.enrollment(workspace_id,class_id,term_id,student_id,enrollment_id),
      FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    REVOKE ALL ON class_os.class_exam,class_os.exam_result_revision,class_os.class_seating,class_os.seat_revision FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.class_exam,class_os.exam_result_revision,class_os.class_seating,class_os.seat_revision TO class_os_runtime;
    GRANT UPDATE(version,updated_at) ON class_os.class_exam,class_os.class_seating TO class_os_runtime;
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_command_type_check CHECK(command_type IN (
      'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
      'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
      'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
      'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire','conversation.import.admit',
      'conversation.create','conversation.rename','conversation.archive','conversation.enqueue',
      'conversation.run.claim','conversation.run.finish','conversation.run.cancel','conversation.run.reconcile','conversation.run.finish-result',
      'document.create','document.revise','document.archive','document.restore',
      'exam.create','score.record','seat.layout.create','seat.assign','seat.swap'));
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_classroom_risk_check
      CHECK(command_type NOT IN ('exam.create','score.record','seat.layout.create','seat.assign','seat.swap') OR risk='W2');
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CONSTRAINT business_audit_action_check CHECK(action IN (
      'command.preview','command.approve','command.reject','command.commit','command.status','roster.list','class.context',
      'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
      'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled','exit.summary','exit.download','audit.list',
      'model.config.read','model.test.started','model.test.completed','model.test.failed','model.enable','model.disable','model.invoke',
      'conversation.history','exit.conversation.summary','exit.conversation.download','conversation.transfer.proof',
      'document.list','document.read','document.history','exam.list','exam.read','seat.read'));
    """)
    # The original candidate check was unnamed. Resolve the exact old closed
    # command check from the trusted catalog, never from user/model identifiers.
    checks = [value for value in inspect(op.get_bind()).get_check_constraints('workspace_chat_turn', schema='class_os')
              if "'class.create'" in value['sqltext'] and "'document.revise'" in value['sqltext']]
    if len(checks) != 1:
        raise RuntimeError('Expected exact old workspace candidate guard')
    op.drop_constraint(checks[0]['name'], 'workspace_chat_turn', schema='class_os', type_='check')
    op.execute("""ALTER TABLE class_os.workspace_chat_turn ADD CONSTRAINT workspace_chat_candidate_command_check
      CHECK(candidate IS NULL OR (jsonb_typeof(candidate)='object' AND octet_length(candidate::text)<=440000
        AND candidate->>'command' IN ('class.create','class.update','term.update','student.create','student.update_name',
        'task.create','task.update','document.create','document.revise','exam.create','score.record','seat.layout.create','seat.assign','seat.swap')))
    """)


def downgrade():
    raise RuntimeError('Preserve results and seat history; restore a verified full backup or forward-fix')
