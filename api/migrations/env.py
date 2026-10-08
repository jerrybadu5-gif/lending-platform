"""Alembic environment for McLender's own database. Run by app.store.migrate() at API start-up,
which passes an open connection; `alembic` on the command line is not needed."""

from alembic import context

from app.store import metadata

connection = context.config.attributes.get("connection")
if connection is None:  # pragma: no cover - only when someone runs alembic by hand without a connection
    raise SystemExit("Run migrations through the API (app.store.migrate), which supplies the connection.")

context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
