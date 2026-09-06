export type DetailFocus = "input" | "chain" | "output";

function rounded(value: number): string {
  const normalized = Math.round((value + Number.EPSILON) * 100) / 100;
  return Number.isInteger(normalized) ? String(normalized) : normalized.toFixed(2);
}

export function formatSignedDelta(before: number, after: number): string {
  const delta = Math.round((after - before + Number.EPSILON) * 100) / 100;
  if (delta === 0) return "0";
  return `${delta > 0 ? "+" : ""}${rounded(delta)}`;
}

export function creationAgeError(ageYears: string, speciesId = "dog"): string | null {
  const age = Number(ageYears);
  const max = speciesId === "fox" ? 15 : 20;
  return Number.isInteger(age) && age >= 1 && age <= max ? null : `年龄必须是 1 到 ${max} 岁之间的整数`;
}

export function createSubmissionGate(): {
  readonly enter: () => boolean;
  readonly leave: () => void;
} {
  let pending = false;
  return {
    enter() {
      if (pending) return false;
      pending = true;
      return true;
    },
    leave() {
      pending = false;
    },
  };
}

export function selectElfieIdAfterLoad(
  requestedId: string | null | undefined,
  currentId: string | undefined,
  firstId: string | undefined,
): string | undefined {
  if (requestedId === null) return firstId;
  return requestedId ?? currentId ?? firstId;
}

export function selectReadyFoodAfterLoad(
  currentKey: string,
  foods: readonly Readonly<{
    readonly key: string;
    readonly ready_for_attempt: boolean;
  }>[],
): string {
  const current = foods.find((item) => item.key === currentKey);
  if (current?.ready_for_attempt) return current.key;
  return foods.find((item) => item.ready_for_attempt)?.key ?? foods[0]?.key ?? "";
}

export function detailTitle(focus: DetailFocus, tab: string): string {
  if (tab === "链路" || focus === "chain") return "完整处理链路";
  if (focus === "input") return "输入与感知";
  return "决策与执行";
}
