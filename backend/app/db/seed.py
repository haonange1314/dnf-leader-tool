from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.dungeon import builtin_raid_12_definition
from app.models import Dungeon, DungeonTeamTemplate, DungeonVersion, FormulaVersion
from app.schemas.dungeon import DungeonVersionDefinition


@dataclass(frozen=True)
class SeedResult:
    dungeon_code: str
    created: bool


def seed_builtin_dungeons(session: Session) -> tuple[SeedResult, ...]:
    definition = builtin_raid_12_definition()
    existing = session.scalar(select(Dungeon).where(Dungeon.code == definition.dungeon_code))
    if existing is not None:
        return (SeedResult(dungeon_code=definition.dungeon_code, created=False),)

    formula = _get_or_create_formula(session, definition)
    dungeon = Dungeon(
        code=definition.dungeon_code,
        name=definition.dungeon_name,
        description=definition.description,
        is_active=True,
    )
    version = DungeonVersion(
        version_no=definition.version_no,
        status="PUBLISHED",
        default_wave_count=definition.default_wave_count,
        min_wave_count=definition.min_wave_count,
        max_wave_count=definition.max_wave_count,
        formula_version=formula,
        composition_rules=definition.composition_rules.model_dump(mode="json", by_alias=True),
        special_role_rules=definition.special_role_rules.model_dump(mode="json", by_alias=True),
        strength_order_rules=definition.strength_order_rules.model_dump(mode="json", by_alias=True),
        optimization_rules=definition.optimization_rules.model_dump(mode="json", by_alias=True),
        missing_slot_policy=definition.missing_slot_policy.model_dump(mode="json", by_alias=True),
        published_at=datetime.now(UTC),
    )
    version.teams = [
        DungeonTeamTemplate(
            team_key=team.team_key,
            display_name=team.display_name,
            display_color=team.display_color,
            display_order=team.display_order,
            member_count=team.member_count,
            strength_rank=team.strength_rank,
        )
        for team in definition.teams
    ]
    dungeon.versions = [version]
    session.add(dungeon)
    session.flush()
    return (SeedResult(dungeon_code=definition.dungeon_code, created=True),)


def _get_or_create_formula(
    session: Session, definition: DungeonVersionDefinition
) -> FormulaVersion:
    formula_definition = definition.formula
    formula = session.scalar(
        select(FormulaVersion).where(
            FormulaVersion.code == formula_definition.code,
            FormulaVersion.version == formula_definition.version,
        )
    )
    if formula is None:
        formula = FormulaVersion(
            code=formula_definition.code,
            version=formula_definition.version,
            config=formula_definition.model_dump(mode="json"),
            is_active=True,
        )
        session.add(formula)
        session.flush()
    return formula
