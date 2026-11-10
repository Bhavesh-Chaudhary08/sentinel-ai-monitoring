/** Seconds → "3h 24m" / "45m" / "12s" / "—". Browser time is always reported
 *  as a duration, never as a verdict. Sub-minute spans render with seconds so
 *  a 15-second visit never looks like zero time. */
export function fmtDuration(totalSeconds: number | undefined | null): string {
  if (totalSeconds == null) return "—";
  const s = Math.round(totalSeconds);
  if (s <= 0) return "0m";
  if (s < 60) return `${s}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/** HH:MM for segment timestamps. */
export function fmtClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Percent change for trend chips — a fact, not a verdict: neutral arrow (no
 *  green/red), and "new" when there is no previous baseline (a percentage
 *  against zero would be infinite). */
export function fmtDelta(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "new";
  if (pct === 0) return "no change";
  return `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}%`;
}
