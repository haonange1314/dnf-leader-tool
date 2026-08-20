import uuid
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy.orm import Session

from app.application.schedule_editor import apply_schedule_operations
from app.core.errors import AppError
from app.domain.dungeon import custom_party_4_definition
from app.models.dungeon import DungeonVersion
from app.models.schedule import Schedule, ScheduleParticipant, Team, TeamSlot, Wave
from app.schemas.schedule import ScheduleOperation


class FakeSession:
    def flush(self) -> None:
        pass


def test_move_and_swap_return_reversible_commands_and_recompute_totals() -> None:
    schedule, version, participants, slots = _editor_fixture()
    db = cast(Session, FakeSession())

    inverse = apply_schedule_operations(
        db,
        schedule,
        version,
        [
            ScheduleOperation(
                type="MOVE_PARTICIPANT",
                participant_id=participants[0].id,
                to_slot_id=slots[0].id,
            )
        ],
    )

    assert slots[0].participant_id == participants[0].id
    assert inverse[0].type == "UNASSIGN_PARTICIPANT"
    assert schedule.waves[0].damage_total == Decimal("500")

    slots[1].participant_id = participants[1].id
    inverse = apply_schedule_operations(
        db,
        schedule,
        version,
        [
            ScheduleOperation(
                type="SWAP_PARTICIPANTS",
                participant_id=participants[0].id,
                other_participant_id=participants[1].id,
            )
        ],
    )
    assert slots[0].participant_id == participants[1].id
    assert slots[1].participant_id == participants[0].id
    assert inverse[0].type == "SWAP_PARTICIPANTS"


def test_locked_slot_rejects_move() -> None:
    schedule, version, participants, slots = _editor_fixture()
    slots[0].is_locked = True

    with pytest.raises(AppError) as caught:
        apply_schedule_operations(
            cast(Session, FakeSession()),
            schedule,
            version,
            [
                ScheduleOperation(
                    type="MOVE_PARTICIPANT",
                    participant_id=participants[0].id,
                    to_slot_id=slots[0].id,
                )
            ],
        )

    assert caught.value.code == "SLOT_LOCKED"


def _editor_fixture() -> tuple[
    Schedule, DungeonVersion, list[ScheduleParticipant], list[TeamSlot]
]:
    definition = custom_party_4_definition()
    schedule_id = uuid.uuid4()
    formula_id = uuid.uuid4()
    version = DungeonVersion(
        id=uuid.uuid4(),
        dungeon_id=uuid.uuid4(),
        version_no=1,
        status="PUBLISHED",
        default_wave_count=1,
        min_wave_count=1,
        max_wave_count=12,
        formula_version_id=formula_id,
        composition_rules=definition.composition_rules.model_dump(mode="json", by_alias=True),
        special_role_rules=definition.special_role_rules.model_dump(mode="json", by_alias=True),
        strength_order_rules=definition.strength_order_rules.model_dump(mode="json", by_alias=True),
        optimization_rules=definition.optimization_rules.model_dump(mode="json", by_alias=True),
        missing_slot_policy=definition.missing_slot_policy.model_dump(mode="json", by_alias=True),
    )
    schedule = Schedule(
        id=schedule_id,
        name="编辑器测试",
        dungeon_version_id=version.id,
        formula_version_id=formula_id,
        wave_count=1,
        status="DRAFT",
        revision=1,
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
    )
    participants = [
        _participant(schedule_id, "DAMAGE", damage=Decimal("500")),
        _participant(schedule_id, "DAMAGE", damage=Decimal("400")),
        _participant(schedule_id, "DAMAGE", damage=Decimal("300")),
        _participant(schedule_id, "BUFFER", buffer=Decimal("50")),
    ]
    schedule.participants.extend(participants)
    wave = Wave(id=uuid.uuid4(), schedule_id=schedule_id, wave_no=1, is_locked=False)
    team = Team(
        id=uuid.uuid4(),
        schedule_id=schedule_id,
        wave_id=wave.id,
        team_key="PARTY",
        display_name_snapshot="队伍",
        display_color_snapshot="#3e63dd",
        display_order_snapshot=0,
        member_count_snapshot=4,
        strength_rank_snapshot=None,
    )
    slots = [
        TeamSlot(
            id=uuid.uuid4(),
            schedule_id=schedule_id,
            wave_id=wave.id,
            team_id=team.id,
            slot_no=index,
            is_locked=False,
        )
        for index in range(1, 5)
    ]
    team.slots.extend(slots)
    wave.teams.append(team)
    schedule.waves.append(wave)
    return schedule, version, participants, slots


def _participant(
    schedule_id: uuid.UUID,
    role_type: str,
    *,
    damage: Decimal | None = None,
    buffer: Decimal | None = None,
) -> ScheduleParticipant:
    participant_id = uuid.uuid4()
    return ScheduleParticipant(
        id=participant_id,
        schedule_id=schedule_id,
        character_id=uuid.uuid4(),
        player_id_snapshot=uuid.uuid4(),
        player_name_snapshot=str(participant_id),
        character_name_snapshot=str(participant_id),
        profession_snapshot="测试职业",
        role_type_snapshot=role_type,
        damage_score_snapshot=damage,
        buffer_score_snapshot=buffer,
        is_treasure_snapshot=False,
        is_selected=True,
        is_locked=False,
    )
