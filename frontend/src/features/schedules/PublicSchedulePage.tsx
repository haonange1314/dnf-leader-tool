import { Card, Col, Empty, Row, Skeleton, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, type PublicScheduleVersion } from "../../api/client";
import { ScheduleParticipantLabel } from "./ScheduleEditor";

export function PublicSchedulePage({ token }: { token: string }) {
  const [version, setVersion] = useState<PublicScheduleVersion | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<PublicScheduleVersion>(`/share/${token}`)
      .then(setVersion)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "分享链接加载失败"),
      );
  }, [token]);

  if (error) {
    return <Empty className="public-empty" description={error} />;
  }
  if (!version) {
    return <Skeleton active className="public-loading" />;
  }
  const schedule = version.snapshot;
  const participantById = new Map(
    schedule.participants.map((participant) => [participant.id, participant]),
  );
  return (
    <main className="public-schedule">
      <header className="public-schedule-header">
        <div>
          <Typography.Title>{schedule.name}</Typography.Title>
          <Typography.Text type="secondary">
            发布版本第 {version.versionNo} 版 · {new Date(version.publishedAt).toLocaleString()}
          </Typography.Text>
        </div>
        <Tag color="green">只读发布版</Tag>
      </header>
      <div className="wave-list">
        {schedule.waves.map((wave) => (
          <Card
            key={wave.id}
            title={`第 ${wave.waveNo} 波`}
            extra={`C ${wave.damageTotal} 亿 · 奶 ${wave.bufferTotal}`}
            className="schedule-panel wave-card"
          >
            <Row gutter={[12, 12]}>
              {wave.teams.map((team) => (
                <Col xs={24} xl={Math.max(6, Math.floor(24 / wave.teams.length))} key={team.id}>
                  <Card
                    size="small"
                    title={`${team.displayNameSnapshot} · ${team.compositionCode}`}
                    extra={`C ${team.damageTotal} · 奶 ${team.bufferTotal}`}
                    className="team-card"
                    style={{ borderTopColor: team.displayColorSnapshot }}
                  >
                    {team.slots.map((slot) => {
                      const participant = slot.participantId
                        ? participantById.get(slot.participantId)
                        : undefined;
                      const core = participant
                        ? wave.specialAssignments.some(
                            (assignment) => assignment.participantId === participant.id,
                          )
                        : false;
                      return (
                        <div className="team-slot" key={slot.id}>
                          {participant ? (
                            <ScheduleParticipantLabel participant={participant} core={core} />
                          ) : (
                            <Typography.Text type="secondary">位置 {slot.slotNo} · 待补</Typography.Text>
                          )}
                        </div>
                      );
                    })}
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        ))}
      </div>
    </main>
  );
}
