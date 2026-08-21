import argparse
import getpass

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password, normalize_username
from app.db.seed import seed_builtin_dungeons
from app.db.session import SessionLocal
from app.models.identity import User


def seed() -> None:
    with SessionLocal.begin() as session:
        results = seed_builtin_dungeons(session)
    for result in results:
        action = "created" if result.created else "exists"
        print(f"{result.dungeon_code}: {action}")


def init_owner(username: str | None, password: str | None) -> None:
    settings = get_settings()
    resolved_username = normalize_username(username or settings.bootstrap_owner_username or "")
    resolved_password = password or settings.bootstrap_owner_password
    if not resolved_username:
        resolved_username = normalize_username(input("Owner 用户名: "))
    if not resolved_password:
        resolved_password = getpass.getpass("Owner 密码: ")
    if not resolved_username:
        raise SystemExit("Owner 用户名不能为空")

    with SessionLocal.begin() as session:
        existing = session.scalar(select(User).where(User.username == resolved_username))
        if existing is not None:
            print(f"OWNER {resolved_username}: exists")
            return
        session.add(
            User(
                username=resolved_username,
                password_hash=hash_password(resolved_password),
                role="OWNER",
                is_active=True,
            )
        )
    print(f"OWNER {resolved_username}: created")


def main() -> None:
    parser = argparse.ArgumentParser(description="DNF 团长排表工具后端管理命令")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed")
    owner_parser = subparsers.add_parser("init-owner")
    owner_parser.add_argument("--username")
    owner_parser.add_argument("--password")
    args = parser.parse_args()
    if args.command == "seed":
        seed()
    elif args.command == "init-owner":
        init_owner(args.username, args.password)


if __name__ == "__main__":
    main()
