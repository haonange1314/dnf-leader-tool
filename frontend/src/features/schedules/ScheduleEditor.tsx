import { CrownOutlined, LockOutlined, UnlockOutlined } from "@ant-design/icons";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Button, Card, Col, Row, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import type {
  ScheduleOperation,
  ScheduleParticipant,
  ScheduleSlot,
  ScheduleTeam,
  ScheduleWave,
} from "../../api/client";

export function ScheduleEditorWave({
  wave,
  participantsById,
  disabled,
  onOperation,
}: {
  wave: ScheduleWave;
  participantsById: Map<string, ScheduleParticipant>;
  disabled: boolean;
  onOperation: (operation: ScheduleOperation) => void;
}) {
  return (
    <Card
      data-wave-no={wave.waveNo}
      size="small"
      title={`第 ${wave.waveNo} 波`}
      extra={
        <Space>
          <Typography.Text type="secondary">
            C {wave.damageTotal} 亿 · 奶 {wave.bufferTotal}
          </Typography.Text>
          <Button
            size="small"
            icon={wave.isLocked ? <UnlockOutlined /> : <LockOutlined />}
            disabled={disabled}
            onClick={() =>
              onOperation({ type: "LOCK_WAVE", waveId: wave.id, locked: !wave.isLocked })
            }
          >
            {wave.isLocked ? "解锁波次" : "锁定波次"}
          </Button>
        </Space>
      }
      className="schedule-panel wave-card"
    >
      <Row gutter={[12, 12]}>
        {wave.teams.map((team) => (
          <Col xs={24} xl={Math.max(6, Math.floor(24 / wave.teams.length))} key={team.id}>
            <Card
              size="small"
              title={`${team.displayNameSnapshot} · ${
                team.compositionCode === "INCOMPLETE" ? "待补" : team.compositionCode
              }`}
              extra={`C ${team.damageTotal} · 奶 ${team.bufferTotal}`}
              className="team-card"
              style={{ borderTopColor: team.displayColorSnapshot }}
            >
              <div className="team-slots">
                {team.slots.map((slot) => (
                  <EditorSlot
                    key={slot.id}
                    slot={slot}
                    team={team}
                    wave={wave}
                    participant={
                      slot.participantId ? participantsById.get(slot.participantId) : undefined
                    }
                    disabled={disabled}
                    onOperation={onOperation}
                  />
                ))}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    </Card>
  );
}

function EditorSlot({
  slot,
  team,
  wave,
  participant,
  disabled,
  onOperation,
}: {
  slot: ScheduleSlot;
  team: ScheduleTeam;
  wave: ScheduleWave;
  participant?: ScheduleParticipant;
  disabled: boolean;
  onOperation: (operation: ScheduleOperation) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `slot:${slot.id}`,
    disabled: disabled || slot.isLocked || wave.isLocked,
  });
  const core = participant
    ? wave.specialAssignments.find((assignment) => assignment.participantId === participant.id)
    : undefined;
  const moveDisabled = disabled || slot.isLocked || wave.isLocked || Boolean(participant?.isLocked);
  return (
    <div
      ref={setNodeRef}
      className={`team-slot editor-slot${isOver ? " editor-slot-over" : ""}${
        slot.isLocked ? " editor-slot-locked" : ""
      }`}
    >
      <div className="editor-slot-content">
        {participant ? (
          <ScheduleDraggableParticipant
            participant={participant}
            core={Boolean(core)}
            disabled={moveDisabled}
          />
        ) : (
          <Typography.Text type="secondary">位置 {slot.slotNo} · 待排</Typography.Text>
        )}
      </div>
      <Space
        size={2}
        className="editor-slot-actions"
        onPointerDown={(event) => event.stopPropagation()}
      >
        {participant?.isTreasureSnapshot ? (
          <Button
            type="text"
            size="small"
            title={core ? "取消本波核心" : "设为本波核心"}
            icon={<CrownOutlined />}
            disabled={disabled || wave.isLocked}
            onClick={() =>
              onOperation(
                core
                  ? { type: "CLEAR_WAVE_CORE", waveId: wave.id, ruleCode: core.ruleCode }
                  : { type: "SET_WAVE_CORE", waveId: wave.id, participantId: participant.id },
              )
            }
          />
        ) : null}
        {participant ? (
          <>
            <Button
              type="text"
              size="small"
              title={participant.isLocked ? "解锁角色" : "锁定角色"}
              icon={participant.isLocked ? <UnlockOutlined /> : <LockOutlined />}
              disabled={disabled}
              onClick={() =>
                onOperation({
                  type: "LOCK_PARTICIPANT",
                  participantId: participant.id,
                  locked: !participant.isLocked,
                })
              }
            />
            <Button
              type="text"
              size="small"
              danger
              disabled={moveDisabled}
              onClick={() =>
                onOperation({ type: "UNASSIGN_PARTICIPANT", participantId: participant.id })
              }
            >
              移出
            </Button>
          </>
        ) : null}
        <Button
          type="text"
          size="small"
          title={slot.isLocked ? "解锁位置" : "锁定位置"}
          icon={slot.isLocked ? <UnlockOutlined /> : <LockOutlined />}
          disabled={disabled || wave.isLocked}
          onClick={() =>
            onOperation({ type: "LOCK_SLOT", slotId: slot.id, locked: !slot.isLocked })
          }
        />
      </Space>
    </div>
  );
}

export function ScheduleUnassignedDropZone({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: "unassigned-pool", disabled: !active });
  return (
    <div
      ref={setNodeRef}
      className={`unassigned-pool${isOver ? " unassigned-pool-over" : ""}`}
    >
      {children}
    </div>
  );
}

export function ScheduleDraggableParticipant({
  participant,
  core = false,
  disabled,
}: {
  participant: ScheduleParticipant;
  core?: boolean;
  disabled: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `participant:${participant.id}`,
    disabled,
  });
  return (
    <div
      ref={setNodeRef}
      className={`draggable-participant${isDragging ? " dragging" : ""}`}
      style={{ transform: CSS.Translate.toString(transform) }}
      {...listeners}
      {...attributes}
    >
      <ScheduleParticipantLabel participant={participant} compact core={core} />
    </div>
  );
}

export function ScheduleParticipantLabel({
  participant,
  compact = false,
  core = false,
}: {
  participant: ScheduleParticipant;
  compact?: boolean;
  core?: boolean;
}) {
  return (
    <Space size={4} wrap={!compact}>
      <Tag color={participant.roleTypeSnapshot === "DAMAGE" ? "red" : "green"}>
        {participant.roleTypeSnapshot === "DAMAGE" ? "C" : "奶"}
      </Tag>
      <span>{participant.playerNameSnapshot} · {participant.characterNameSnapshot}</span>
      <Typography.Text type="secondary" className="participant-score">
        {participant.roleTypeSnapshot === "DAMAGE"
          ? `伤害 ${Number(participant.damageScoreSnapshot ?? 0).toLocaleString("zh-CN")} 亿`
          : `奶量 ${Number(participant.bufferScoreSnapshot ?? 0).toFixed(2)} 万`}
      </Typography.Text>
      {participant.isTreasureSnapshot ? <Tag color="purple">秘宝</Tag> : null}
      {participant.isFixedLeadTeamBufferSnapshot ? <Tag color="red">固定红奶</Tag> : null}
      {participant.isGroupHuntSnapshot ? <Tag color="orange">群猎</Tag> : null}
      {core ? <Tag color="purple">本波核心</Tag> : null}
      {participant.unassignedReason ? (
        <Tag color="warning">{describeUnassignedReason(participant.unassignedReason)}</Tag>
      ) : null}
    </Space>
  );
}

function describeUnassignedReason(reason: Record<string, unknown>): string {
  if (reason.message === "角色或玩家已停用" || reason.code === "SOURCE_INACTIVE") {
    return "档案已停用，待处理";
  }
  const labels: Record<string, string> = {
    UNASSIGNED_NO_AVAILABLE_WAVE: "无可用波次",
    UNASSIGNED_PLAYER_CONFLICT: "玩家波次冲突",
    UNASSIGNED_ROLE_COMPOSITION: "角色类型无法组成合法队伍",
    UNASSIGNED_CAPACITY: "排表容量不足",
  };
  return labels[String(reason.code)] ?? "待处理";
}
