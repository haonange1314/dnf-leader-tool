export interface User {
  id: string;
  username: string;
  role: string;
  is_active: boolean;
}
export interface TeamDefinition {
  id?: string;
  teamKey: string;
  displayName: string;
  displayColor: string;
  displayOrder: number;
  memberCount: number;
  strengthRank: number | null;
}
export interface DungeonVersion {
  id: string;
  dungeonId: string;
  versionNo: number;
  status: "DRAFT" | "PUBLISHED" | "RETIRED";
  defaultWaveCount: number;
  minWaveCount: number;
  maxWaveCount: number | null;
  formula: Record<string, unknown>;
  teams: TeamDefinition[];
  compositionRules: Record<string, unknown>;
  specialRoleRules: Record<string, unknown>;
  strengthOrderRules: Record<string, unknown>;
  optimizationRules: Record<string, unknown>;
  missingSlotPolicy: Record<string, unknown>;
}
export interface Dungeon {
  id: string;
  code: string;
  name: string;
  description: string | null;
  isActive: boolean;
  versions: DungeonVersion[];
}
export interface Character {
  id: string;
  playerId: string;
  name: string;
  profession: string;
  roleType: "DAMAGE" | "BUFFER";
  damageScore: string | null;
  bufferScore: string | null;
  isTreasureDamage: boolean;
  defaultRaidParticipant: boolean;
  note: string | null;
  isActive: boolean;
}
export interface Player {
  id: string;
  displayName: string;
  isActive: boolean;
  characters: Character[];
}
export interface ImportBatch {
  id: string;
  filename: string;
  status: string;
  total_rows: number;
  summary: { create: number; update: number; ignore: number; error: number };
}
export interface ScheduleSummary {
  id: string;
  name: string;
  dungeonVersionId: string;
  waveCount: number;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  revision: number;
  validationSummary: Record<string, number> | null;
  createdAt: string;
  updatedAt: string;
}
export interface ScheduleParticipant {
  id: string;
  characterId: string;
  playerIdSnapshot: string;
  playerNameSnapshot: string;
  characterNameSnapshot: string;
  professionSnapshot: string;
  roleTypeSnapshot: "DAMAGE" | "BUFFER";
  damageScoreSnapshot: string | null;
  bufferScoreSnapshot: string | null;
  isTreasureSnapshot: boolean;
  isSelected: boolean;
  isLocked: boolean;
  unassignedReason: Record<string, unknown> | null;
}
export interface ScheduleSlot {
  id: string;
  slotNo: number;
  participantId: string | null;
  isLocked: boolean;
}
export interface ScheduleTeam {
  id: string;
  teamKey: string;
  displayNameSnapshot: string;
  displayColorSnapshot: string;
  displayOrderSnapshot: number;
  memberCountSnapshot: number;
  strengthRankSnapshot: number | null;
  damageTotal: string;
  bufferTotal: string;
  compositionCode: string;
  slots: ScheduleSlot[];
}
export interface ScheduleWave {
  id: string;
  waveNo: number;
  isLocked: boolean;
  damageTotal: string;
  bufferTotal: string;
  teams: ScheduleTeam[];
  specialAssignments: Array<{
    id: string;
    ruleCode: string;
    participantId: string;
    targetTeamKeySnapshot: string;
  }>;
}
export interface SchedulePreference {
  playerId: string;
  allowedWaves: number[] | null;
  maxWaveCount: number | null;
  preferEarly: boolean;
  preferContiguous: boolean;
}
export interface ScheduleDetail extends ScheduleSummary {
  note: string | null;
  participants: ScheduleParticipant[];
  preferences: SchedulePreference[];
  waves: ScheduleWave[];
}
export interface ValidationIssue {
  severity: "ERROR" | "WARNING" | "INFO";
  code: string;
  message_params: Record<string, unknown>;
}
export interface ValidationReport {
  revision: number;
  issues: ValidationIssue[];
  summary: { error: number; warning: number; info: number };
}
export interface ScheduleSyncPreview {
  revision: number;
  sourceFingerprint: string;
  changes: Array<{
    action: "ADD" | "UPDATE" | "DESELECT";
    characterId: string;
    playerName: string;
    characterName: string;
    changedFields: string[];
  }>;
  summary: { ADD: number; UPDATE: number; DESELECT: number };
}
export interface ScheduleCopyPreview {
  revision: number;
  sourceDungeonVersionId: string;
  targetDungeonVersionId: string;
  waveCount: number;
  migrationRequired: boolean;
  migrationFingerprint: string;
  changes: Array<{
    code: string;
    description: string;
    before: unknown;
    after: unknown;
  }>;
}
export interface GenerationRun {
  id: string;
  scheduleId: string;
  inputRevision: number;
  resultRevision: number | null;
  status: "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "STALE";
  inputHash: string;
  solverVersion: string;
  formulaVersionId: string;
  randomSeed: number;
  timeLimitSeconds: number;
  durationMs: number | null;
  objectiveSummary: {
    assignedCount: number;
    participantCount: number;
    completeWaveCount: number;
    completeTeamCount: number;
    preferredCompositionCount: number;
    specialRuleSatisfiedCount: number;
    damageSpread: number;
    bufferSpread: number;
    strengthOrderViolationCount: number;
  } | null;
  diagnostics: {
    solverStatus?: string;
    unassigned?: Array<{
      participantId: string;
      code: string;
      messageParams: Record<string, unknown>;
    }>;
    issues?: Array<{
      severity: string;
      code: string;
      messageParams: Record<string, unknown>;
    }>;
  } | null;
  createdAt: string;
  finishedAt: string | null;
}
export interface GenerationResponse {
  run: GenerationRun;
  schedule: ScheduleDetail;
}
export interface ScheduleOperation {
  type:
    | "MOVE_PARTICIPANT"
    | "SWAP_PARTICIPANTS"
    | "UNASSIGN_PARTICIPANT"
    | "SET_WAVE_CORE"
    | "CLEAR_WAVE_CORE"
    | "LOCK_PARTICIPANT"
    | "LOCK_SLOT"
    | "LOCK_WAVE";
  participantId?: string | null;
  otherParticipantId?: string | null;
  toSlotId?: string | null;
  slotId?: string | null;
  waveId?: string | null;
  ruleCode?: string | null;
  locked?: boolean | null;
}
export interface ScheduleCommandResponse {
  operationId: string;
  revision: number;
  schedule: ScheduleDetail;
  inverseOperations: ScheduleOperation[];
}
export interface ScheduleVersionSummary {
  id: string;
  scheduleId: string;
  versionNo: number;
  sourceRevision: number;
  snapshotSchemaVersion: number;
  snapshotHash: string;
  formulaVersionId: string;
  publishedAt: string;
}
export interface ScheduleVersionView extends ScheduleVersionSummary {
  snapshot: ScheduleDetail;
}
export interface SchedulePublishResponse {
  version: ScheduleVersionView;
  schedule: ScheduleDetail;
  issues: ValidationIssue[];
}
export interface SchedulePublicationCheck {
  revision: number;
  publishable: boolean;
  issues: ValidationIssue[];
  summary: { error: number; warning: number; info: number };
}
export interface ShareLinkCreated {
  id: string;
  scheduleVersionId: string;
  token: string;
  expiresAt: string | null;
}
export interface ShareLinkView {
  id: string;
  scheduleVersionId: string;
  expiresAt: string | null;
  revokedAt: string | null;
  createdAt: string;
  status: "ACTIVE" | "EXPIRED" | "REVOKED";
}
export interface PublicScheduleVersion {
  versionId: string;
  versionNo: number;
  publishedAt: string;
  snapshot: ScheduleDetail;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "include",
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: {
        code?: string;
        message?: string;
        details?: Record<string, unknown>;
      };
    };
    throw new ApiError(
      payload.error?.message || `请求失败（${response.status}）`,
      response.status,
      payload.error?.code || "HTTP_ERROR",
      payload.error?.details || {},
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
