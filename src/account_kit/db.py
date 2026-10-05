from sqlalchemy import DDL, MetaData, event
from sqlalchemy.orm import DeclarativeBase

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


# ``Base.metadata.create_all`` (sync or async, with or without init_db) creates
# the ``auth`` schema first, so a brand-new empty database just works.
event.listen(
    Base.metadata,
    "before_create",
    DDL("CREATE SCHEMA IF NOT EXISTS auth").execute_if(dialect="postgresql"),
)
