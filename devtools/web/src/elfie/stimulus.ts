const emotionNames = new Set([
  "happiness",
  "sadness",
  "anger",
  "fear",
  "surprise",
  "disgust",
]);

export function buildStateInjection(
  enabled: boolean,
  values: Readonly<Record<string, string>>,
  sleeping: boolean,
  sleepingTouched: boolean,
): Readonly<Record<string, unknown>> {
  if (!enabled) return {};
  const state: Record<string, unknown> = {};
  const emotions: Record<string, number> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === "") continue;
    if (emotionNames.has(key)) emotions[key] = Number(value);
    else state[key] = Number(value);
  }
  if (sleepingTouched) state.is_sleeping = sleeping;
  if (Object.keys(emotions).length > 0) state.emotions = emotions;
  return state;
}
