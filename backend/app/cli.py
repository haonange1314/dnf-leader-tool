import argparse
import getpass
import json

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password, normalize_username
from app.db.seed import seed_builtin_dungeons
from app.db.session import SessionLocal
from app.domain.schedule.rules import (
    RuleContextParticipant,
    RuleContextTeam,
    RuleInterpretationContext,
    resolve_rule_output,
)
from app.integrations.deepseek_rules import RuleProviderError
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


def check_deepseek() -> None:
    """Run an opt-in, synthetic live check without exposing credentials or real roster data."""
    from app.application.schedule_rules import build_rule_provider

    settings = get_settings()
    context = RuleInterpretationContext(
        schedule_id="live-check",
        revision=1,
        wave_count=12,
        participants=(
            RuleContextParticipant(
                participant_id="character-a",
                player_id="player-a",
                player_name="测试甲",
                character_name="剑魂",
                profession="剑魂",
                role_type="DAMAGE",
            ),
            RuleContextParticipant(
                participant_id="character-b",
                player_id="player-b",
                player_name="测试乙",
                character_name="奶妈",
                profession="奶妈",
                role_type="BUFFER",
            ),
            RuleContextParticipant(
                participant_id="character-c",
                player_id="player-c",
                player_name="测试丙",
                character_name="狂战士",
                profession="狂战士",
                role_type="DAMAGE",
            ),
        ),
        teams=(
            RuleContextTeam("RED", "红队"),
            RuleContextTeam("YELLOW", "黄队"),
            RuleContextTeam("GREEN", "绿队"),
        ),
    )
    source_text = (
        "测试甲只能参加第1到第6波；测试乙不能参加第1波；"
        "测试甲和测试丙不能在同一波；测试甲的剑魂必须在第2波红队。"
    )
    provider = build_rule_provider(settings)
    try:
        result = provider.interpret(source_text, context)
    finally:
        provider.close()
    resolved = resolve_rule_output(result.output, context)
    if result.output.unsupported_items or resolved.issues or len(resolved.rules) < 5:
        raise SystemExit(
            "DeepSeek 联调失败：清晰的合成规则未被完整解析；"
            f"规则={len(resolved.rules)}，不支持项={len(result.output.unsupported_items)}，"
            f"校验问题={len(resolved.issues)}"
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "provider": result.provider,
                "model": result.model,
                "parsedRuleCount": len(result.output.rules),
                "resolvedRuleCount": len(resolved.rules),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="DNF 团长排表工具后端管理命令")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed")
    subparsers.add_parser(
        "check-deepseek",
        help="使用合成数据验证真实 DeepSeek 连接、Schema 和引用解析",
    )
    owner_parser = subparsers.add_parser("init-owner")
    owner_parser.add_argument("--username")
    owner_parser.add_argument("--password")
    args = parser.parse_args()
    if args.command == "seed":
        seed()
    elif args.command == "init-owner":
        init_owner(args.username, args.password)
    elif args.command == "check-deepseek":
        try:
            check_deepseek()
        except (ValueError, RuleProviderError) as exc:
            raise SystemExit(f"DeepSeek 联调失败：{exc}") from exc


if __name__ == "__main__":
    main()
