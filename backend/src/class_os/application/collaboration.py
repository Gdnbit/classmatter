"""Fixed bilateral orchestration through the same authorized QG/BCG unit of work."""
from .roster import BusinessGateway, QueryGateway, CommandRejected


class CollaborationBusinessGateway(BusinessGateway):
    def identity_key(self, credentials, public_key, sealed_key):
        return self._run(credentials, 'collaboration.identity',
            lambda tx, binding, now: tx.collaboration_identity(binding, public_key, sealed_key, now))

    def add_peer(self, credentials, invitation, class_id, term_id):
        return self._run(credentials, 'collaboration.peer.add',
            lambda tx, binding, now: tx.collaboration_add_peer(binding, invitation, class_id, term_id, now),
            resource_id=invitation.workspace_id)

    def revoke_peer(self, credentials, peer_id, expected_version):
        return self._run(credentials, 'collaboration.peer.revoke',
            lambda tx, binding, now: tx.collaboration_revoke(binding, peer_id, expected_version), resource_id=peer_id)

    def receive(self, credentials, message):
        return self._run(credentials, 'collaboration.receive',
            lambda tx, binding, now: tx.collaboration_receive(binding, message, now), resource_id=message.message_id)

    def attempt(self, credentials, message_id):
        return self._run(credentials, 'collaboration.attempt',
            lambda tx, binding, now: tx.collaboration_attempt(binding, message_id, now), resource_id=message_id)

    def delivered(self, credentials, message_id, payload_hash):
        return self._run(credentials, 'collaboration.delivered',
            lambda tx, binding, now: tx.collaboration_delivered(binding, message_id, payload_hash, now), resource_id=message_id)

    def retry(self, credentials, message_id):
        return self._run(credentials,'collaboration.retry',
            lambda tx,binding,now:tx.collaboration_retry(binding,message_id,now),resource_id=message_id)


class CollaborationQueryGateway(QueryGateway):
    def read(self, credentials, *, thread_id=None, include_delivery=False):
        if self.store.database.profile != 'classroom-work-d4':
            raise CommandRejected()
        return self._run(credentials, 'collaboration.read',
            lambda tx, binding, now: tx.collaboration_read(binding, thread_id, include_delivery=include_delivery), resource_id=thread_id)

    def key(self, credentials):
        # Trusted transport composition only. This method is never given to
        # Agent tools or registered as an HTTP read endpoint.
        return self._run(credentials, 'collaboration.read', lambda tx, binding, now: tx.collaboration_key(binding))
