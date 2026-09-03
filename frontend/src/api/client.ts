export interface User {
  id: string;
  username: string;
  role_id: string;
  role: string;
  role_name: string;
  permissions: string[];
  is_active: boolean;
}
export interface ManagedUser extends User {
  active_session_count: number;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface Permission {
  id: string;
  code: string;
  name: string;
  module: string;
  description: string | null;
}
export interface Role {
  id: string;
  code: string;
  name: string;
  description: string | null;
  isSystem: boolean;
  isActive: boolean;
  permissionCodes: string[];
  userCount: number;
  createdAt: string;
  updatedAt: string;
}
export interface AuditLog {
  id: string;
  actorUserId: string | null;
  actorUsername: string | null;
  action: string;
  outcome: "SUCCESS" | "FAILURE";
  requestId: string;
  ipAddress: string | null;
  resourceType: string | null;
  resourceId: string | null;
  details: Record<string, unknown>;
  createdAt: string;
}
export interface EditLock {
  scheduleId: string;
  held: boolean;
  holderUserId: string | null;
  holderUsername: string | null;
  ownedByCurrentUser: boolean;
  canTakeover: boolean;
  acquiredAt: string | null;
  heartbeatAt: string | null;
  expiresAt: string | null;
  heartbeatIntervalSeconds: number;
  token: string | null;
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
export type DungeonRoleType = "DAMAGE" | "BUFFER";
export interface FormulaDefinition {
  code: string;
  version: number;
  damageUnit: "YI";
  damageScale: number;
  bufferScale: number;
  teamDamageMode: "SUM";
  twoBufferMode: "SUM";
}
export interface CompositionRuleDefinition {
  code: string;
  applicableTeamKeys: string[];
  roles: Partial<Record<DungeonRoleType, number>>;
  priority: number;
}
export interface SpecialRoleRuleDefinition {
  code: string;
  characterFlag: "TREASURE_DAMAGE";
  countPerWave: number;
  targetTeamKey: string;
  requiredForCompleteWave: boolean;
  companionPolicy: {
    roleType: DungeonRoleType;
    objective: "MINIMIZE_OTHER_MEMBER_SCORE";
  } | null;
}
export interface DungeonVersionInput {
  defaultWaveCount: number;
  minWaveCount: number;
  maxWaveCount: number | null;
  formula: FormulaDefinition;
  teams: TeamDefinition[];
  compositionRules: {
    schemaVersion: 1;
    allowed: CompositionRuleDefinition[];
  };
  specialRoleRules: {
    schemaVersion: 1;
    rules: SpecialRoleRuleDefinition[];
  };
  strengthOrderRules: {
    schemaVersion: 1;
    orders: Array<{ metric: DungeonRoleType; teams: string[] }>;
  };
  optimizationRules: {
    schemaVersion: 1;
    balanceAcrossWaves: DungeonRoleType[];
    respectPlayerPreferences: boolean;
  };
  missingSlotPolicy: {
    schemaVersion: 1;
    mode: "FILL_EARLIER_WAVES" | "SPREAD_EVENLY";
  };
}
export interface DungeonVersion extends DungeonVersionInput {
  id: string;
  dungeonId: string;
  versionNo: number;
  status: "DRAFT" | "PUBLISHED" | "RETIRED";
  createdAt: string;
  publishedAt: string | null;
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
  sortOrder: number;
  profession: string;
  roleType: "DAMAGE" | "BUFFER";
  damageScore: string | null;
  bufferScore: string | null;
  isTreasureDamage: boolean;
  isFixedLeadTeamBuffer: boolean;
  isGroupHunt: boolean;
  defaultRaidParticipant: boolean;
  note: string | null;
  isActive: boolean;
}
export interface Player {
  id: string;
  displayName: string;
  isActive: boolean;
  sortOrder: number;
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
  activeRuleSetId: string | null;
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
  isFixedLeadTeamBufferSnapshot: boolean;
  isGroupHuntSnapshot: boolean;
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
  scheduleRuleSetId: string | null;
  ruleCompilerVersion: string | null;
  effectiveRules: Array<Record<string, unknown>> | null;
  ruleEvaluation: Array<{
    ruleId: string;
    type: string;
    status: "SATISFIED" | "UNSATISFIED" | "BLOCKED" | "NOT_APPLICABLE";
    explanation: string;
    reason?: string;
  }> | null;
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
    damageSpreadDisplay?: string;
    bufferSpreadDisplay?: string;
    strengthOrderViolationCount: number;
  } | null;
  diagnostics: {
    solverStatus?: string;
    objectiveStages?: Array<{
      code: string;
      value: number;
      outcome: "OPTIMAL" | "TARGET_REACHED" | "FEASIBLE";
      durationMs: number;
    }>;
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
export interface RuleResolutionIssue {
  code: string;
  candidateId: string | null;
  field: string | null;
  reference: string | null;
  matches: string[];
}
export interface ScheduleRuleSet {
  id: string;
  scheduleId: string;
  inputRevision: number;
  sourceText: string;
  sourceHash: string;
  contextHash: string;
  status: "PARSED" | "CONFIRMED" | "STALE" | "SUPERSEDED" | "FAILED";
  modelProvider: string;
  modelName: string;
  providerResponseId: string | null;
  promptVersion: string;
  schemaVersion: number;
  parsedRules: Array<{
    candidateId: string;
    type: string;
    enforcement: "HARD" | "SOFT";
    explanation: string;
    [key: string]: unknown;
  }>;
  resolvedReferences: Record<string, unknown>;
  issues: RuleResolutionIssue[];
  createdBy: string;
  confirmedBy: string | null;
  createdAt: string;
  confirmedAt: string | null;
}
export interface ScheduleRuleSetList {
  items: ScheduleRuleSet[];
  total: number;
  activeRuleSetId: string | null;
  revision: number;
  maxSourceChars: number;
  parsingEnabled: boolean;
}
export interface ScheduleRuleSetMutationResponse {
  revision: number;
  activeRuleSetId: string | null;
  ruleSet: ScheduleRuleSet | null;
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

const editLockTokens = new Map<string, string>();

export function setScheduleEditLockToken(scheduleId: string, token: string | null): void {
  const storageKey = `dnf_edit_lock:${scheduleId}`;
  if (token) {
    editLockTokens.set(scheduleId, token);
    globalThis.sessionStorage?.setItem(storageKey, token);
  } else {
    editLockTokens.delete(scheduleId);
    globalThis.sessionStorage?.removeItem(storageKey);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (init?.method && !["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase())) {
    const csrfToken = readCookie("dnf_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
    const scheduleId = path.match(/^\/schedules\/([^/]+)/)?.[1];
    const editLockToken = scheduleId
      ? (editLockTokens.get(scheduleId) ??
        globalThis.sessionStorage?.getItem(`dnf_edit_lock:${scheduleId}`))
      : null;
    if (editLockToken) headers.set("X-Edit-Lock-Token", editLockToken);
  }
  const response = await fetch(`/api/v1${path}`, {
    credentials: "include",
    ...init,
    headers,
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

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find((value) => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}
