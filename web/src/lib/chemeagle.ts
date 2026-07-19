export type JsonRecord = Record<string, unknown>;

export type Reaction = {
  id: string;
  reactants: JsonRecord[];
  products: JsonRecord[];
  conditions: JsonRecord[];
  smiles?: string;
  raw: JsonRecord;
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function errorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) return fallback;
  const message = payload.message ?? payload.error ?? payload.detail;
  return typeof message === "string" ? message : fallback;
}

export function getTaskId(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.task_id === "string") return payload.task_id;
  if (isRecord(payload.data) && typeof payload.data.task_id === "string") {
    return payload.data.task_id;
  }
  return null;
}

export function getStatus(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.status === "string") return payload.status;
  if (isRecord(payload.data) && typeof payload.data.status === "string") {
    return payload.data.status;
  }
  return null;
}

function resultEntries(payload: unknown): JsonRecord[] {
  if (!isRecord(payload)) return [];
  const directResults = records(payload.results);
  if (directResults.length > 0) return directResults;

  if (isRecord(payload.data)) {
    const nestedResults = records(payload.data.results);
    if (nestedResults.length > 0) return nestedResults;
    if (isRecord(payload.data.result)) return [payload.data.result];
  }

  if (isRecord(payload.result)) return [payload.result];
  return [payload];
}

export function getReactions(payload: unknown): Reaction[] {
  return resultEntries(payload).flatMap((entry, entryIndex) => {
    const source = isRecord(entry.result) ? entry.result : entry;
    const reactionRecords = records(source.reactions);

    return reactionRecords.map((reaction, reactionIndex) => ({
      id:
        String(reaction.reaction_id ?? reaction.id ?? "") ||
        `${entryIndex + 1}.${reactionIndex + 1}`,
      reactants: records(reaction.reactants),
      products: records(reaction.products),
      conditions: records(reaction.conditions),
      smiles:
        typeof reaction.smiles === "string" ? reaction.smiles : undefined,
      raw: reaction,
    }));
  });
}

export function getResultCount(payload: unknown): number {
  return resultEntries(payload).length;
}

export function displayChemical(item: JsonRecord): string {
  const label = item.label ?? item.name ?? item.text ?? item.smiles;
  return typeof label === "string" ? label : JSON.stringify(item);
}

export function displaySmiles(item: JsonRecord): string | null {
  return typeof item.smiles === "string" ? item.smiles : null;
}
