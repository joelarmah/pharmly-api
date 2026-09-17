"""Create/list/enable/disable /admin staff accounts.

There's no self-signup for admin accounts -- someone with shell access to
the deployment runs this. Passwords are entered interactively (never as a
CLI argument, so they don't end up in shell history) and hashed with the
same argon2 scheme used for customer PINs.

Usage:
    python -m scripts.manage_admin_users create <username> [--role admin]
    python -m scripts.manage_admin_users list
    python -m scripts.manage_admin_users disable <username>
    python -m scripts.manage_admin_users enable <username>
    python -m scripts.manage_admin_users set-password <username>
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.admin_user import AdminUser


def _read_new_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < 8:
            print("Password must be at least 8 characters.", file=sys.stderr)
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords didn't match, try again.", file=sys.stderr)
            continue
        return password


async def create(username: str, role: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(AdminUser).where(AdminUser.username == username))
        if existing.scalar_one_or_none() is not None:
            print(f"'{username}' already exists.", file=sys.stderr)
            raise SystemExit(1)

        password = _read_new_password()
        db.add(AdminUser(username=username, password_hash=hash_password(password), role=role))
        await db.commit()
        print(f"Created admin account '{username}' (role={role}).")


async def list_accounts() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AdminUser).order_by(AdminUser.created_at))
        accounts = result.scalars().all()
        if not accounts:
            print("No admin accounts yet.")
            return
        for account in accounts:
            status = "active" if account.is_active else "disabled"
            print(f"{account.username}\trole={account.role}\t{status}\tcreated={account.created_at}")


async def _set_active(username: str, is_active: bool) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        account = result.scalar_one_or_none()
        if account is None:
            print(f"No such account: '{username}'.", file=sys.stderr)
            raise SystemExit(1)
        account.is_active = is_active
        await db.commit()
        print(f"{'Enabled' if is_active else 'Disabled'} '{username}'.")


async def set_password(username: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        account = result.scalar_one_or_none()
        if account is None:
            print(f"No such account: '{username}'.", file=sys.stderr)
            raise SystemExit(1)
        account.password_hash = hash_password(_read_new_password())
        await db.commit()
        print(f"Password updated for '{username}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("username")
    create_parser.add_argument("--role", default="admin")

    subparsers.add_parser("list")

    disable_parser = subparsers.add_parser("disable")
    disable_parser.add_argument("username")

    enable_parser = subparsers.add_parser("enable")
    enable_parser.add_argument("username")

    set_password_parser = subparsers.add_parser("set-password")
    set_password_parser.add_argument("username")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(create(args.username, args.role))
    elif args.command == "list":
        asyncio.run(list_accounts())
    elif args.command == "disable":
        asyncio.run(_set_active(args.username, False))
    elif args.command == "enable":
        asyncio.run(_set_active(args.username, True))
    elif args.command == "set-password":
        asyncio.run(set_password(args.username))


if __name__ == "__main__":
    main()
