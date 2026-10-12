from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings):
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


def make_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(make_engine(settings), expire_on_commit=False)
