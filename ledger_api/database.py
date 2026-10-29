from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, DB_SSLMODE, DB_SSLROOTCERT

logger = logging.getLogger("ledger_api")


class Base(DeclarativeBase):
    pass


def connect_args(url: str, sslmode: str = "", sslrootcert: str = "") -> dict:
    """Build driver arguments that survive a missing CA certificate file.

    A configured path that does not exist makes psycopg fail every connection,
    which surfaces as an opaque 500 on every database route. Certificates are
    excluded from Git and from the Docker build, so a deployment can easily end
    up without one. Keep TLS on in that case, drop only the file check, and say
    so in the log.
    """
    if url.startswith("sqlite"):
        return {"check_same_thread": False}

    args: dict[str, str] = {}
    mode = sslmode
    cert = sslrootcert
    if cert and not Path(cert).is_file():
        logger.warning(
            "CA certificate %s is missing; connecting with sslmode=require "
            "instead of certificate verification",
            cert,
        )
        cert = ""
        if mode in ("verify-ca", "verify-full"):
            mode = "require"
    if mode:
        args["sslmode"] = mode
    if cert:
        args["sslrootcert"] = cert
    return args


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args(DATABASE_URL, DB_SSLMODE, DB_SSLROOTCERT),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
