"""Scoped SQL for one request, one material and one confirmed summary per root."""
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.collaboration import (MaterialMessage, Invitation, RequestMaterial, ShareMaterial,
    SaveCollectedSummary, COMMAND_TYPES, source_citation)
from class_os.domain.documents import CreateDocument, ReviseDocument
from class_os.domain.roster import Receipt
from .builtin_summary_store import BuiltinSummaryTransaction
from .workspace_chat import WorkspaceChatTransaction


class CollaborationTransaction(BuiltinSummaryTransaction):
    def authorize_boundary(self, binding, action, proposal_id):
        return super().authorize_boundary(binding, 'class.context' if action.startswith('collaboration.') else action, proposal_id)

    def audit(self, binding, action, outcome, now, metadata):
        if not action.startswith('collaboration.'):
            return super().audit(binding, action, outcome, now, metadata)
        event = uuid4()
        self._mutate(text('''INSERT INTO class_os.collaboration_audit
            (workspace_id,event_id,owner_id,action,outcome,resource_id,occurred_at)
            VALUES(:workspace_id,:event,:actor_id,:action,:outcome,:resource,:now)'''),
            {**binding, 'event': event, 'action': action, 'outcome': outcome, 'resource': metadata['resource_id'], 'now': now})
        return event

    def collaboration_key(self, binding):
        row = self._connection.execute(text('''SELECT public_key,sealed_key FROM class_os.collaboration_identity
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id'''), binding).mappings().one_or_none()
        return dict(row) if row else None

    def collaboration_identity(self, binding, public_key, sealed_key, now):
        current = self.collaboration_key(binding)
        if current:
            return current
        if (type(public_key) is not str or len(public_key) != 64 or any(c not in '0123456789abcdef' for c in public_key)
                or type(sealed_key) is not bytes or not 32 <= len(sealed_key) <= 16384):
            raise CommandRejected()
        self._mutate(text('''INSERT INTO class_os.collaboration_identity(workspace_id,owner_id,public_key,sealed_key,created_at)
            VALUES(:workspace_id,:actor_id,:public,:sealed,:now)'''), {**binding, 'public':public_key, 'sealed':sealed_key, 'now':now})
        return self.collaboration_key(binding)

    def _peer(self, binding, peer_id, *, active=True):
        row = self._connection.execute(text('''SELECT * FROM class_os.collaboration_peer
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND peer_id=:peer'''),
            {**binding, 'peer':peer_id}).mappings().one_or_none()
        if row is None or active and row['status'] != 'active':
            raise CommandRejected()
        return dict(row)

    def collaboration_add_peer(self, binding, invitation, class_id, term_id, now):
        if type(invitation) is not Invitation or invitation.workspace_id == binding['workspace_id']:
            raise CommandRejected()
        self._classroom_context(binding, class_id, term_id, write=True)
        rows = self._connection.execute(text('''SELECT * FROM class_os.collaboration_peer
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND peer_id=:peer'''),
            {**binding, 'peer':invitation.workspace_id}).mappings().one_or_none()
        values = {'peer_id':invitation.workspace_id, 'name':invitation.name, 'endpoint':invitation.endpoint,
                  'public_key':invitation.public_key, 'class_id':class_id, 'term_id':term_id}
        if rows:
            if rows['status'] != 'active' or any(rows[k] != v for k,v in values.items()):
                raise CommandRejected()  # A different key/name never replaces a pinned contact.
            return self._public_peer(rows)
        count = self._connection.execute(text('SELECT count(*) FROM class_os.collaboration_peer WHERE workspace_id=:workspace_id'), binding).scalar_one()
        if count >= 20:
            raise CommandRejected()
        self._mutate(text('''INSERT INTO class_os.collaboration_peer
            (workspace_id,owner_id,peer_id,name,endpoint,public_key,class_id,term_id,status,version,created_at)
            VALUES(:workspace_id,:actor_id,:peer_id,:name,:endpoint,:public_key,:class_id,:term_id,'active',1,:now)'''),
            {**binding, **values, 'now':now})
        return self._public_peer(self._peer(binding, invitation.workspace_id))

    def collaboration_revoke(self, binding, peer_id, expected_version):
        peer = self._peer(binding, peer_id)
        if type(expected_version) is not int or peer['version'] != expected_version:
            raise CommandRejected()
        self._mutate(text('''UPDATE class_os.collaboration_peer SET status='revoked',version=version+1
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND peer_id=:peer AND version=:version'''),
            {**binding, 'peer':peer_id, 'version':expected_version})
        return self._public_peer(self._peer(binding, peer_id, active=False))

    @staticmethod
    def _public_peer(row):
        return {k:row[k] for k in ('peer_id','name','endpoint','public_key','class_id','term_id','status','version')}

    def _collaboration_rows(self, binding, *, thread_id=None):
        rows = self._connection.execute(text('''SELECT m.*,t.status AS thread_status,p.status AS peer_status
            FROM class_os.collaboration_message m
            JOIN class_os.workspace_chat_thread t ON t.workspace_id=m.workspace_id AND t.thread_id=m.thread_id
            JOIN class_os.collaboration_peer p ON p.workspace_id=m.workspace_id AND p.peer_id=m.peer_id
            WHERE m.workspace_id=:workspace_id AND m.owner_id=:actor_id
              AND (CAST(:thread AS uuid) IS NULL OR m.thread_id=:thread)
            ORDER BY m.created_at,m.message_id LIMIT 101'''), {**binding,'thread':thread_id}).mappings().all()
        if len(rows) > 100:
            raise CommandRejected()
        for row in rows:
            if self._message(row).digest() != row['payload_hash']:
                raise CommandRejected()
        return [dict(row) for row in rows]

    @staticmethod
    def _message(row):
        return MaterialMessage(message_id=row['message_id'], request_id=row['request_id'],
            sender=row['workspace_id'] if row['direction']=='outgoing' else row['peer_id'],
            receiver=row['peer_id'] if row['direction']=='outgoing' else row['workspace_id'],
            operation=row['operation'],title=row['title'],body=row['body'],
            source_document_id=row['source_document_id'],source_version=row['source_version'])

    def collaboration_read(self, binding, thread_id=None, *, include_delivery=False):
        cleared=False
        if thread_id is not None:
            cleared=self.chat_header(binding, thread_id)['status']=='cleared'
        peers = [self._public_peer(row) for row in self._connection.execute(text('''SELECT * FROM class_os.collaboration_peer
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id ORDER BY name,peer_id LIMIT 21'''), binding).mappings()]
        rows = [] if cleared else self._collaboration_rows(binding, thread_id=thread_id)
        summaries = {r['request_id']:dict(r) for r in self._connection.execute(text('''SELECT request_id,document_id,document_version
            FROM class_os.collaboration_summary WHERE workspace_id=:workspace_id AND owner_id=:actor_id'''), binding).mappings()}
        items = []
        for row in rows:
            peer = next((p for p in peers if p['peer_id'] == row['peer_id']), None)
            status = ('saved' if row['request_id'] in summaries else
                'stopped' if row['peer_status']!='active' or row['thread_status']!='active' else
                'material-received' if any(r['request_id']==row['request_id'] and r['operation']=='material' and r['direction']=='incoming' for r in rows) else
                'material-sent' if any(r['request_id']==row['request_id'] and r['operation']=='material' and r['delivered_at'] for r in rows) else
                'received' if row['direction']=='incoming' else 'delivered' if row['delivered_at'] else
                'retry-needed' if row['attempts']>=12 else 'queued')
            items.append({k:row[k] for k in ('message_id','request_id','peer_id','direction','operation','title','body',
                'source_document_id','source_version','class_id','term_id','thread_id','created_at','delivered_at')}
                | {'peer_name':peer['name'] if peer else '', 'status':status, 'saved':summaries.get(row['request_id'])})
        return {'peers':peers, 'items':items}

    def validate_collaboration(self, binding, command, now):
        if type(command) not in COMMAND_TYPES:
            raise CommandRejected()
        self._classroom_context(binding, command.class_id, command.term_id, write=True)
        rows = self._collaboration_rows(binding)
        if type(command) in (RequestMaterial,ShareMaterial) and len(rows)>=100:
            raise CommandRejected()
        if type(command) is RequestMaterial:
            peer = self._peer(binding, command.peer_id)
            self.chat_header(binding, command.thread_id, active=True)
            if ((peer['class_id'],peer['term_id']) != (command.class_id,command.term_id)
                    or any(row['message_id']==command.request_id for row in rows)):
                raise CommandRejected()
            return None
        root = next((r for r in rows if r['message_id']==command.request_id and r['operation']=='request'), None)
        if root is None or (root['class_id'],root['term_id']) != (command.class_id,command.term_id):
            raise CommandRejected()
        peer = self._peer(binding, root['peer_id'])
        self.chat_header(binding, root['thread_id'], active=True)
        if type(command) is ShareMaterial:
            if (root['direction']!='incoming' or command.peer_id!=root['peer_id'] or command.thread_id!=root['thread_id']
                    or any(row['request_id']==command.request_id and row['operation']=='material' for row in rows)):
                raise CommandRejected()
            document = self.read_documents(binding, command.class_id, command.term_id, command.document_id, False)
            if (document['status']!='draft' or document['version']!=command.expected_version
                    or document['title']!=command.title or document['body']!=command.body):
                raise CommandRejected()
            return None
        material = next((r for r in rows if r['message_id']==command.source_message_id and r['request_id']==command.request_id
                         and r['operation']=='material' and r['direction']=='incoming'), None)
        if root['direction']!='outgoing' or material is None or material['peer_id']!=root['peer_id']:
            raise CommandRejected()
        citation = source_citation(peer['name'], self._message(material))
        if not command.body.endswith(citation) or self._connection.execute(text('''SELECT EXISTS(
            SELECT 1 FROM class_os.collaboration_summary WHERE workspace_id=:workspace_id AND request_id=:request)'''),
            {**binding,'request':command.request_id}).scalar_one():
            raise CommandRejected()
        document = (ReviseDocument(command.document_id, command.class_id, command.term_id, command.expected_version,
                    command.title,command.body,command.format) if command.expected_version else
                    CreateDocument(command.document_id,command.class_id,command.term_id,command.title,command.body,command.format))
        self.validate_document(binding, document, now)
        return document

    def _insert_message(self, binding, message, direction, peer, thread_id, now):
        values = {**binding, **message.model_dump(), 'peer':peer['peer_id'], 'direction':direction,
            'class':peer['class_id'],'term':peer['term_id'],'thread':thread_id,'hash':message.digest(),'now':now,
            'delivered':now if direction=='incoming' else None}
        self._mutate(text('''INSERT INTO class_os.collaboration_message
            (workspace_id,owner_id,message_id,request_id,peer_id,direction,operation,title,body,source_document_id,source_version,
             class_id,term_id,thread_id,payload_hash,next_attempt_at,delivered_at,created_at)
            VALUES(:workspace_id,:actor_id,:message_id,:request_id,:peer,:direction,:operation,:title,:body,:source_document_id,
              :source_version,:class,:term,:thread,:hash,:now,:delivered,:now)'''), values)

    def apply(self, binding, command, now):
        if type(command) not in COMMAND_TYPES:
            return super().apply(binding, command, now)
        prepared = self.validate_collaboration(binding, command, now)
        if type(command) is SaveCollectedSummary:
            receipt = super().apply(binding, prepared, now)
            self._mutate(text('''INSERT INTO class_os.collaboration_summary
                (workspace_id,owner_id,request_id,source_message_id,document_id,document_version,body_hash,created_at)
                VALUES(:workspace_id,:actor_id,:request,:source,:document,:version,:hash,:now)'''),
                {**binding,'request':command.request_id,'source':command.source_message_id,'document':command.document_id,
                 'version':receipt.version,'hash':sha256(command.body.encode()).hexdigest(),'now':now})
            return receipt
        peer = self._peer(binding, command.peer_id)
        message = MaterialMessage(message_id=command.request_id if type(command) is RequestMaterial else command.message_id,
            request_id=command.request_id,sender=binding['workspace_id'],receiver=peer['peer_id'],
            operation='request' if type(command) is RequestMaterial else 'material',title=command.title,body=command.body,
            source_document_id=command.document_id if type(command) is ShareMaterial else None,
            source_version=command.expected_version if type(command) is ShareMaterial else None)
        self._insert_message(binding,message,'outgoing',peer,command.thread_id,now)
        return Receipt(uuid4(),message.message_id,1)

    def collaboration_receive(self, binding, message, now):
        if type(message) is not MaterialMessage or message.receiver!=binding['workspace_id']:
            raise CommandRejected()
        peer = self._peer(binding,message.sender)
        self._classroom_context(binding,peer['class_id'],peer['term_id'],write=True)
        rows = self._collaboration_rows(binding)
        existing = next((r for r in rows if r['message_id']==message.message_id),None)
        if existing:
            if existing['direction']!='incoming' or existing['payload_hash']!=message.digest():
                raise CommandRejected()
            return {'message_id':message.message_id,'payload_hash':message.digest()}
        if len(rows)>=100:
            raise CommandRejected()
        root = next((r for r in rows if r['message_id']==message.request_id and r['direction']=='outgoing'
                     and r['operation']=='request' and r['peer_id']==peer['peer_id']),None)
        if message.operation=='material' and (root is None or any(r['request_id']==message.request_id and r['operation']=='material' for r in rows)):
            raise CommandRejected()
        thread = root['thread_id'] if root else uuid5(message.request_id, str(binding['workspace_id']))
        # Reject an archived/cleared existing thread; never resurrect it.
        if root:
            self.chat_header(binding,thread,active=True)
        elif self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_thread
            WHERE workspace_id=:workspace_id AND thread_id=:thread)'''),{**binding,'thread':thread}).scalar_one():
            raise CommandRejected()
        prompt = ('同事提供了材料，请读取本事项并准备班级工作小结。' if root else
                  '收到同事的材料请求，请核对后提供已有工作文档。')
        self.chat_send(binding,thread,message.message_id,prompt,now)
        self._insert_message(binding,message,'incoming',peer,thread,now)
        if not root:
            self._mutate(text('''UPDATE class_os.workspace_chat_thread SET title=:title
                WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread'''),
                {**binding,'thread':thread,'title':(peer['name']+'：'+message.title)[:80]})
            ticket = self.chat_claim(binding,thread,message.message_id,now)
            # The transport receipt is not a model reply and cannot claim that
            # the human accepted work. Keep a concise attributed request.
            self.chat_finish(binding,ticket,'completed',f"{peer['name']}希望补充：{message.body}",None,now)
        return {'message_id':message.message_id,'payload_hash':message.digest()}

    def collaboration_attempt(self, binding, message_id, now):
        row = next((r for r in self._collaboration_rows(binding) if r['message_id']==message_id),None)
        if row is None or row['direction']!='outgoing' or row['delivered_at'] or row['attempts']>=12 or now<row['next_attempt_at']:
            return None
        peer = self._peer(binding,row['peer_id'])
        self.chat_header(binding,row['thread_id'],active=True)
        self._classroom_context(binding,row['class_id'],row['term_id'],write=True)
        delay = min(1800, 5 * 2**row['attempts'])
        self._mutate(text('''UPDATE class_os.collaboration_message SET attempts=attempts+1,next_attempt_at=:next,last_error='offline'
            WHERE workspace_id=:workspace_id AND message_id=:message AND attempts=:attempts AND delivered_at IS NULL'''),
            {**binding,'message':message_id,'attempts':row['attempts'],'next':now+timedelta(seconds=delay)})
        return {'message':self._message(row), 'peer':peer}

    def collaboration_delivered(self, binding, message_id, payload_hash, now):
        row = next((r for r in self._collaboration_rows(binding) if r['message_id']==message_id),None)
        if row is None or row['direction']!='outgoing' or row['payload_hash']!=payload_hash or not row['attempts']:
            raise CommandRejected()
        if row['delivered_at'] is None:
            self._mutate(text('''UPDATE class_os.collaboration_message SET delivered_at=:now,last_error=NULL
                WHERE workspace_id=:workspace_id AND message_id=:message AND delivered_at IS NULL'''),
                {**binding,'message':message_id,'now':now})

    def collaboration_retry(self,binding,message_id,now):
        row=next((r for r in self._collaboration_rows(binding) if r['message_id']==message_id),None)
        if row is None or row['direction']!='outgoing':
            raise CommandRejected()
        self._peer(binding,row['peer_id'])
        self.chat_header(binding,row['thread_id'],active=True)
        if row['delivered_at'] is not None:
            return  # A delayed click never resends an acknowledged message.
        if row['attempts']<12:
            return  # Ordinary retry remains scheduled; do not defeat backoff.
        self._mutate(text('''UPDATE class_os.collaboration_message SET attempts=0,next_attempt_at=:now,last_error=NULL
            WHERE workspace_id=:workspace_id AND message_id=:message AND attempts=12 AND delivered_at IS NULL'''),
            {**binding,'message':message_id,'now':now})

    def _collaboration_origin(self, binding, row):
        incoming = self._connection.execute(text('''SELECT operation,request_id FROM class_os.collaboration_message
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND message_id=:request
              AND direction='incoming' '''), {**binding,'thread':row['thread_id'],'request':row['request_id']}).mappings().one_or_none()
        if incoming:
            row['origin'] = 'collaboration'
        return row

    def _chat_turn(self, binding, thread_id, request_id):
        return self._collaboration_origin(binding,super()._chat_turn(binding,thread_id,request_id))

    def chat_history(self, binding, thread_id, *, before=None):
        result = super().chat_history(binding,thread_id,before=before)
        result['turns'] = [self._collaboration_origin(binding,row) for row in result['turns']]
        return result

    def chat_list(self, binding, *, offset=0):
        result = super().chat_list(binding,offset=offset)
        rows = self._collaboration_rows(binding)
        for row in result['data']:
            requests = [r for r in rows if r['thread_id']==row['thread_id'] and r['direction']=='incoming' and r['operation']=='request']
            pending = any(r['peer_status']=='active' and not any(m['request_id']==r['request_id'] and m['operation']=='material' for m in rows) for r in requests)
            material = any(r['thread_id']==row['thread_id'] and r['direction']=='incoming' and r['operation']=='material'
                and r['peer_status']=='active'
                and not self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.collaboration_summary
                    WHERE workspace_id=:workspace_id AND request_id=:root)'''),{**binding,'root':r['request_id']}).scalar_one() for r in rows)
            row['summary_attention'] = row.get('summary_attention',False) or pending or material
        return result


def validate_collaboration_integrity(connection):
    peers=connection.execute(text('SELECT * FROM class_os.collaboration_peer')).mappings().all()
    for peer in peers:
        Invitation(workspace_id=peer['peer_id'],name=peer['name'],endpoint=peer['endpoint'],public_key=peer['public_key'])
    rows = connection.execute(text('SELECT * FROM class_os.collaboration_message ORDER BY workspace_id,message_id')).mappings()
    for row in rows:
        if CollaborationTransaction._message(row).digest()!=row['payload_hash']:
            raise ValueError('Invalid material snapshot digest')
        peer=next((p for p in peers if p['workspace_id']==row['workspace_id'] and p['peer_id']==row['peer_id']),None)
        if peer is None or (peer['owner_id'],peer['class_id'],peer['term_id'])!=(row['owner_id'],row['class_id'],row['term_id']):
            raise ValueError('Invalid local material scope')
        if row['operation']=='material':
            root=connection.execute(text('''SELECT * FROM class_os.collaboration_message
                WHERE workspace_id=:w AND message_id=:root AND operation='request' '''),
                {'w':row['workspace_id'],'root':row['request_id']}).mappings().one_or_none()
            if root is None or root['peer_id']!=row['peer_id'] or root['direction']==row['direction'] or root['thread_id']!=row['thread_id']:
                raise ValueError('Material has no matching bilateral request')
            if row['direction']=='outgoing':
                original=connection.execute(text('''SELECT title,body FROM class_os.working_document_revision
                    WHERE workspace_id=:w AND document_id=:doc AND version=:version'''),
                    {'w':row['workspace_id'],'doc':row['source_document_id'],'version':row['source_version']}).mappings().one_or_none()
                if original is None or original['title']!=row['title'] or original['body']!=row['body']:
                    raise ValueError('Shared snapshot differs from its approved source version')
    summaries = connection.execute(text('''SELECT s.body_hash,r.body FROM class_os.collaboration_summary s
        JOIN class_os.working_document_revision r ON r.workspace_id=s.workspace_id AND r.document_id=s.document_id
          AND r.version=s.document_version''')).mappings()
    for row in summaries:
        if sha256(row['body'].encode()).hexdigest()!=row['body_hash']:
            raise ValueError('Saved summary differs from its recorded version')
