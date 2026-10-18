"""Programmatic connection only; no implicit URL, globals or runtime DDL."""
from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use the explicit synthetic migration entry")
context.configure(connection=connection, version_table_schema="class_os", transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
