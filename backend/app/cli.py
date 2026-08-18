import argparse

from app.db.seed import seed_builtin_dungeons
from app.db.session import SessionLocal


def seed() -> None:
    with SessionLocal.begin() as session:
        results = seed_builtin_dungeons(session)
    for result in results:
        action = "created" if result.created else "exists"
        print(f"{result.dungeon_code}: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="DNF 团长排表工具后端管理命令")
    parser.add_argument("command", choices=("seed",))
    args = parser.parse_args()
    if args.command == "seed":
        seed()


if __name__ == "__main__":
    main()
