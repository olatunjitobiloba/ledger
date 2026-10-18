"""Dedicated worker entrypoint for a separate Rumpty Cloud process."""
from __future__ import annotations

import time

from .config import AUTO_CREATE_SCHEMA, POLL_SECONDS
from .database import Base, SessionLocal, engine
from .services import process_one_job


def main() -> None:
    if AUTO_CREATE_SCHEMA:
        Base.metadata.create_all(engine)
    while True:
        db = SessionLocal()
        try:
            process_one_job(db)
        finally:
            db.close()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
