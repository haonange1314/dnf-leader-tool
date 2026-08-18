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
      error?: { message?: string };
    };
    throw new Error(payload.error?.message || `请求失败（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
