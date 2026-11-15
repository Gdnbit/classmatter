"""Actual Windows DPAPI/pg_dump/pg_restore of nonempty bilateral state."""
import os
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from class_os.application.collaboration import CollaborationBusinessGateway,CollaborationQueryGateway
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway
from class_os.domain.collaboration import Invitation,RequestMaterial
from class_os.infrastructure.classroom_upgrade import upgrade_classroom
from class_os.infrastructure.collaboration_transport import PeerProofs
from class_os.infrastructure.native_setup import NativeSetup
from class_os.infrastructure.operator_backup import SyntheticBackup
from class_os.infrastructure.workspace_local_runtime import open_services
from class_os.infrastructure.workspace_upgrade import upgrade_workspace_chat
from test_workbench_upgrade import owned_upgrade


@pytest.mark.db
@pytest.mark.skipif(os.name!='nt',reason='Actual Windows DPAPI owned checkpoint')
def test_full_checkpoint_restores_keys_contact_and_pending_message(owned_upgrade):
    current=upgrade_classroom(upgrade_workspace_chat(owned_upgrade.runtime))
    native=NativeSetup(current,development=True)
    try:
        cookies=native.handle({'operation':'development_access'})['cookies']
    finally:
        native.close()
    auth=cookies['session'],cookies['client'],cookies['csrf'],owned_upgrade.workspace_id
    services=open_services(current,local_development=True)
    try:
        business=CollaborationBusinessGateway(services.worker.identity,services.worker.store)
        query=CollaborationQueryGateway(services.query.identity,services.query.store)
        proofs=PeerProofs(business,query,services.restrictions.codec)
        key=proofs.prepare(auth)
        assert bytes(key['sealed_key'])!=bytes.fromhex(key['public_key'])
        c,t=owned_upgrade.classroom.class_id,owned_upgrade.classroom.term_id
        peer=Invitation(workspace_id=uuid4(),name='合成离线同事',endpoint='http://127.0.0.1:18442',
            public_key=Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex())
        business.add_peer(auth,peer,c,t)
        chats=WorkspaceChatBusinessGateway(services.worker.identity,services.worker.store)
        thread,request=uuid4(),uuid4()
        chats.send(auth,thread,request,'合成收集教学材料')
        chats.finish(auth,chats.claim(auth,thread,request),'completed','等待核对材料请求。')
        command=RequestMaterial(uuid4(),peer.workspace_id,c,t,thread,'合成教学进度','请提供本周教学进度。')
        proposal=services.worker.preview(*auth,command)
        approval=services.worker.approve(*auth,proposal.proposal_id,proposal.payload_hash)
        services.worker.commit(*auth,proposal.proposal_id,uuid4(),approval)
        before=query.read(auth)
        checkpoint=SyntheticBackup(current,profile='classroom-work-d4')
        artifact=checkpoint.create()
        packet,_=checkpoint._open(artifact)
        assert packet['head']=='0034'
        assert {table:packet['inventory'][table]['rows'] for table in
                ('collaboration_identity','collaboration_peer','collaboration_message')}=={
                    'collaboration_identity':1,'collaboration_peer':1,'collaboration_message':1}
        result=checkpoint.check_current_restrictions(artifact,services.restrictions)
        assert result['snapshot_integrity_verified'] and result['activation_allowed'] is False
        assert query.read(auth)==before,'Restore verification must not activate, resend or modify the source'
    finally:
        services.close()
