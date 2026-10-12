from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.composition import Container
from app.models import MaintenanceLock, Membership
from app.settings import get_settings


def bootstrap_curator(container: Container, auth_user_id: str, email: str) -> None:
    with container.sessions.begin() as session:
        current = session.scalar(select(Membership).where(Membership.auth_user_id == auth_user_id))
        if current:
            raise SystemExit(
                "That user already has a membership; use a controlled database change to alter a role."
            )
        session.add(Membership(auth_user_id=auth_user_id, email=email, role="curator", active=True))


async def create_candidate(container: Container) -> None:
    """Create an inactive profile. Reindexing retained canonical text is intentional operator work."""
    active = await container.knowledge.ensure_active_profile()
    print(f"Current active profile: {active.id} ({active.fingerprint})")
    print(
        "Configure the desired embedding/chunking profile, restart, then run `reindex` with a reviewed plan."
    )


def set_lock(container: Container, locked: bool, message: str | None = None) -> None:
    with container.sessions.begin() as session:
        lock = session.get(MaintenanceLock, "reindex") or MaintenanceLock(name="reindex")
        lock.locked, lock.message = locked, message
        session.add(lock)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Engineering Knowledge Assistant operator commands"
    )
    subs = parser.add_subparsers(dest="command", required=True)
    boot = subs.add_parser("bootstrap-curator")
    boot.add_argument("--auth-user-id", required=True)
    boot.add_argument("--email", required=True)
    subs.add_parser("validate-candidate")
    lock = subs.add_parser("maintenance-lock")
    lock.add_argument("--message", default="Knowledge-base maintenance is in progress.")
    subs.add_parser("maintenance-unlock")
    args = parser.parse_args()
    container = Container(get_settings())
    if args.command == "bootstrap-curator":
        bootstrap_curator(container, args.auth_user_id, args.email)
    elif args.command == "validate-candidate":
        asyncio.run(create_candidate(container))
    elif args.command == "maintenance-lock":
        set_lock(container, True, args.message)
    else:
        set_lock(container, False)


if __name__ == "__main__":
    main()
