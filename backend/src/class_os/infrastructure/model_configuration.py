"""Fixed SQL, used only inside the existing Business/Query Gateways."""
from sqlalchemy import text

from class_os.domain.model_configuration import ConfigurationRejected
from class_os.domain.roster import Receipt
from uuid import uuid4


class ModelConfigurationTransaction:
    def model_configuration(self, workspace):
        row = self._connection.execute(text("""SELECT candidate_id,version,protocol,model,base_url,sealed
            FROM class_os.model_configuration WHERE workspace_id=:w"""), {"w": workspace}).mappings().one_or_none()
        return dict(row) if row else None

    def validate_model_configuration(self, binding, command):
        row = self.model_configuration(binding["workspace_id"])
        if (row["version"] if row else 0) != command.expected_version or self._store.model_secrets is None:
            return False
        if command.command.endswith(".save"):
            try:
                self._store.model_secrets.get(binding, command)
            except ConfigurationRejected:
                return False
        return True

    def apply_model_configuration(self, binding, command, now):
        saved = command.command.endswith(".save")
        sealed = self._store.model_secrets.get(binding, command) if saved else None
        self._mutate(text("""INSERT INTO class_os.model_configuration
            (workspace_id,candidate_id,version,protocol,model,base_url,sealed,updated_at)
            VALUES(:workspace_id,:id,:version,:protocol,:model,:url,:sealed,:now)
            ON CONFLICT(workspace_id) DO UPDATE SET candidate_id=EXCLUDED.candidate_id,version=EXCLUDED.version,
            protocol=EXCLUDED.protocol,model=EXCLUDED.model,base_url=EXCLUDED.base_url,sealed=EXCLUDED.sealed,updated_at=EXCLUDED.updated_at
            WHERE class_os.model_configuration.version=:expected"""),
            {**binding, "id": command.candidate_id, "version": command.expected_version + 1, "expected": command.expected_version,
             "protocol": command.protocol, "model": command.model, "url": command.base_url, "sealed": sealed, "now": now})
        return Receipt(uuid4(), command.candidate_id, command.expected_version + 1)
