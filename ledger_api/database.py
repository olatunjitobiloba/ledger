from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, DB_SSLMODE, DB_SSLROOTCERT


class Base(DeclarativeBase):
    pass


if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}
    if DB_SSLMODE:
        connect_args["sslmode"] = DB_SSLMODE
    if DB_SSLROOTCERT:
        connect_args["sslrootcert"] = DB_SSLROOTCERT
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
