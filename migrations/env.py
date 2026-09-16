from alembic import context

from app.config import get_settings
from app.db import Base, build_engine
from app.models import Patient  # noqa: F401 — register tables for autogeneration
from app.voice.models import ToolReceipt, VoiceSession  # noqa: F401

target_metadata = Base.metadata
database_url = get_settings().database_url.get_secret_value()

if context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
