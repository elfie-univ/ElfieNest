export function compact(value) {
  const text = JSON.stringify(value, null, 2);
  return text.length > 1800 ? `${text.slice(0, 1800)}\n…` : text;
}

export function signed(before, after) {
  const value = Number(after) - Number(before);
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

export function formatTime(value) {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).format(new Date(value));
  } catch {
    return "—";
  }
}
