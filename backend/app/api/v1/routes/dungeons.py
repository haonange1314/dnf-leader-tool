import uuid

from fastapi import APIRouter
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.security import utc_now
from app.models.dungeon import Dungeon, DungeonTeamTemplate, DungeonVersion, FormulaVersion
from app.schemas.dungeon import DungeonVersionDefinition, FormulaDefinition, TeamDefinition
from app.schemas.dungeon_api import (
    DungeonCreate,
    DungeonList,
    DungeonSummary,
    DungeonUpdate,
    DungeonVersionInput,
    DungeonVersionView,
    TeamView,
    ValidationResult,
)

router = APIRouter()


def _load_dungeon(db: DbSession, dungeon_id: uuid.UUID) -> Dungeon:
    dungeon = db.scalar(
        select(Dungeon)
        .where(Dungeon.id == dungeon_id)
        .options(
            selectinload(Dungeon.versions).selectinload(DungeonVersion.teams),
            selectinload(Dungeon.versions).selectinload(DungeonVersion.formula_version),
        )
    )
    if dungeon is None:
        raise AppError(404, "DUNGEON_NOT_FOUND", "副本不存在")
    return dungeon


def _version_view(version: DungeonVersion) -> DungeonVersionView:
    config = version.formula_version.config
    formula = FormulaDefinition(
        code=version.formula_version.code,
        version=version.formula_version.version,
        **config,
    )
    return DungeonVersionView(
        id=version.id,
        dungeon_id=version.dungeon_id,
        version_no=version.version_no,
        status=version.status,
        default_wave_count=version.default_wave_count,
        min_wave_count=version.min_wave_count,
        max_wave_count=version.max_wave_count,
        formula=formula,
        teams=[TeamView.model_validate(team) for team in version.teams],
        composition_rules=version.composition_rules,
        special_role_rules=version.special_role_rules,
        strength_order_rules=version.strength_order_rules,
        optimization_rules=version.optimization_rules,
        missing_slot_policy=version.missing_slot_policy,
        created_at=version.created_at,
        published_at=version.published_at,
    )


def _dungeon_view(dungeon: Dungeon) -> DungeonSummary:
    versions = sorted(dungeon.versions, key=lambda item: item.version_no, reverse=True)
    return DungeonSummary(
        id=dungeon.id,
        code=dungeon.code,
        name=dungeon.name,
        description=dungeon.description,
        is_active=dungeon.is_active,
        versions=[_version_view(version) for version in versions],
    )


@router.get("/dungeons", response_model=DungeonList)
def list_dungeons(db: DbSession, current_user: CurrentUser) -> DungeonList:
    del current_user
    dungeons = list(
        db.scalars(
            select(Dungeon)
            .options(
                selectinload(Dungeon.versions).selectinload(DungeonVersion.teams),
                selectinload(Dungeon.versions).selectinload(DungeonVersion.formula_version),
            )
            .order_by(Dungeon.code)
        ).unique()
    )
    db.commit()
    return DungeonList(items=[_dungeon_view(item) for item in dungeons], total=len(dungeons))


@router.post("/dungeons", response_model=DungeonSummary, status_code=201)
def create_dungeon(
    payload: DungeonCreate, db: DbSession, current_user: CurrentUser
) -> DungeonSummary:
    del current_user
    dungeon = Dungeon(
        code=payload.code,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        is_active=payload.is_active,
    )
    db.add(dungeon)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "DUNGEON_CODE_DUPLICATE", "副本编码已存在") from exc
    return _dungeon_view(_load_dungeon(db, dungeon.id))


@router.get("/dungeons/{dungeon_id}", response_model=DungeonSummary)
def get_dungeon(dungeon_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> DungeonSummary:
    del current_user
    dungeon = _load_dungeon(db, dungeon_id)
    db.commit()
    return _dungeon_view(dungeon)


@router.patch("/dungeons/{dungeon_id}", response_model=DungeonSummary)
def update_dungeon(
    dungeon_id: uuid.UUID, payload: DungeonUpdate, db: DbSession, current_user: CurrentUser
) -> DungeonSummary:
    del current_user
    dungeon = _load_dungeon(db, dungeon_id)
    dungeon.name = payload.name.strip()
    dungeon.description = payload.description.strip() if payload.description else None
    dungeon.is_active = payload.is_active
    db.commit()
    return _dungeon_view(dungeon)


@router.post("/dungeons/{dungeon_id}/versions", response_model=DungeonVersionView, status_code=201)
def create_version(
    dungeon_id: uuid.UUID, payload: DungeonVersionInput, db: DbSession, current_user: CurrentUser
) -> DungeonVersionView:
    del current_user
    dungeon = _load_dungeon(db, dungeon_id)
    next_version = (
        db.scalar(
            select(func.max(DungeonVersion.version_no)).where(
                DungeonVersion.dungeon_id == dungeon_id
            )
        )
        or 0
    ) + 1
    definition = _definition(dungeon, next_version, payload)
    formula = _resolve_formula(db, payload.formula)
    version = DungeonVersion(
        dungeon_id=dungeon.id,
        version_no=next_version,
        status="DRAFT",
        default_wave_count=definition.default_wave_count,
        min_wave_count=definition.min_wave_count,
        max_wave_count=definition.max_wave_count,
        formula_version=formula,
        composition_rules=definition.composition_rules.model_dump(mode="json", by_alias=True),
        special_role_rules=definition.special_role_rules.model_dump(mode="json", by_alias=True),
        strength_order_rules=definition.strength_order_rules.model_dump(mode="json", by_alias=True),
        optimization_rules=definition.optimization_rules.model_dump(mode="json", by_alias=True),
        missing_slot_policy=definition.missing_slot_policy.model_dump(mode="json", by_alias=True),
        teams=[_team_model(team) for team in definition.teams],
    )
    db.add(version)
    db.commit()
    return _version_view(_load_version(db, version.id))


@router.get("/dungeon-versions/{version_id}", response_model=DungeonVersionView)
def get_version(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> DungeonVersionView:
    del current_user
    version = _load_version(db, version_id)
    db.commit()
    return _version_view(version)


@router.patch("/dungeon-versions/{version_id}", response_model=DungeonVersionView)
def update_version(
    version_id: uuid.UUID, payload: DungeonVersionInput, db: DbSession, current_user: CurrentUser
) -> DungeonVersionView:
    del current_user
    version = _load_version(db, version_id)
    if version.status != "DRAFT":
        raise AppError(409, "DUNGEON_VERSION_IMMUTABLE", "只有草稿版本允许修改")
    definition = _definition(version.dungeon, version.version_no, payload)
    version.default_wave_count = definition.default_wave_count
    version.min_wave_count = definition.min_wave_count
    version.max_wave_count = definition.max_wave_count
    version.formula_version = _resolve_formula(db, payload.formula)
    version.composition_rules = definition.composition_rules.model_dump(mode="json", by_alias=True)
    version.special_role_rules = definition.special_role_rules.model_dump(
        mode="json", by_alias=True
    )
    version.strength_order_rules = definition.strength_order_rules.model_dump(
        mode="json", by_alias=True
    )
    version.optimization_rules = definition.optimization_rules.model_dump(
        mode="json", by_alias=True
    )
    version.missing_slot_policy = definition.missing_slot_policy.model_dump(
        mode="json", by_alias=True
    )
    version.teams.clear()
    version.teams.extend(_team_model(team) for team in definition.teams)
    db.commit()
    return _version_view(_load_version(db, version.id))


@router.post("/dungeon-versions/{version_id}/validate", response_model=ValidationResult)
def validate_version(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ValidationResult:
    del current_user
    version = _load_version(db, version_id)
    issues = _validation_issues(version)
    db.commit()
    return ValidationResult(valid=not issues, issues=issues)


@router.post("/dungeon-versions/{version_id}/publish", response_model=DungeonVersionView)
def publish_version(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> DungeonVersionView:
    del current_user
    version = _load_version(db, version_id)
    if version.status != "DRAFT":
        raise AppError(409, "DUNGEON_VERSION_IMMUTABLE", "只有草稿版本允许发布")
    issues = _validation_issues(version)
    if issues:
        raise AppError(
            422, "DUNGEON_VERSION_INVALID", "副本规则校验失败", details={"issues": issues}
        )
    version.status = "PUBLISHED"
    version.published_at = utc_now()
    db.commit()
    return _version_view(version)


@router.post("/dungeon-versions/{version_id}/retire", response_model=DungeonVersionView)
def retire_version(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> DungeonVersionView:
    del current_user
    version = _load_version(db, version_id)
    if version.status != "PUBLISHED":
        raise AppError(409, "DUNGEON_VERSION_NOT_PUBLISHED", "只有已发布版本可以退役")
    version.status = "RETIRED"
    db.commit()
    return _version_view(version)


def _load_version(db: DbSession, version_id: uuid.UUID) -> DungeonVersion:
    version = db.scalar(
        select(DungeonVersion)
        .where(DungeonVersion.id == version_id)
        .options(
            selectinload(DungeonVersion.teams),
            selectinload(DungeonVersion.formula_version),
            selectinload(DungeonVersion.dungeon),
        )
    )
    if version is None:
        raise AppError(404, "DUNGEON_VERSION_NOT_FOUND", "副本版本不存在")
    return version


def _definition(
    dungeon: Dungeon, version_no: int, payload: DungeonVersionInput
) -> DungeonVersionDefinition:
    try:
        return DungeonVersionDefinition(
            dungeon_code=dungeon.code,
            dungeon_name=dungeon.name,
            description=dungeon.description,
            version_no=version_no,
            **payload.model_dump(),
        )
    except ValidationError as exc:
        raise AppError(
            422,
            "DUNGEON_VERSION_INVALID",
            "副本规则校验失败",
            details={"issues": [error["msg"] for error in exc.errors()]},
        ) from exc


def _resolve_formula(db: DbSession, formula: FormulaDefinition) -> FormulaVersion:
    config = formula.model_dump(mode="json", by_alias=True, exclude={"code", "version"})
    existing = db.scalar(
        select(FormulaVersion).where(
            FormulaVersion.code == formula.code, FormulaVersion.version == formula.version
        )
    )
    if existing is not None:
        if existing.config != config:
            raise AppError(409, "FORMULA_VERSION_IMMUTABLE", "相同公式版本已存在且配置不同")
        return existing
    return FormulaVersion(code=formula.code, version=formula.version, config=config, is_active=True)


def _team_model(team: TeamDefinition) -> DungeonTeamTemplate:
    return DungeonTeamTemplate(**team.model_dump())


def _validation_issues(version: DungeonVersion) -> list[str]:
    try:
        DungeonVersionDefinition(
            dungeon_code=version.dungeon.code,
            dungeon_name=version.dungeon.name,
            description=version.dungeon.description,
            version_no=version.version_no,
            default_wave_count=version.default_wave_count,
            min_wave_count=version.min_wave_count,
            max_wave_count=version.max_wave_count,
            formula=FormulaDefinition(
                code=version.formula_version.code,
                version=version.formula_version.version,
                **version.formula_version.config,
            ),
            teams=tuple(
                TeamDefinition(
                    team_key=team.team_key,
                    display_name=team.display_name,
                    display_color=team.display_color,
                    display_order=team.display_order,
                    member_count=team.member_count,
                    strength_rank=team.strength_rank,
                )
                for team in version.teams
            ),
            composition_rules=version.composition_rules,
            special_role_rules=version.special_role_rules,
            strength_order_rules=version.strength_order_rules,
            optimization_rules=version.optimization_rules,
            missing_slot_policy=version.missing_slot_policy,
        )
    except ValidationError as exc:
        return [error["msg"] for error in exc.errors()]
    return []
