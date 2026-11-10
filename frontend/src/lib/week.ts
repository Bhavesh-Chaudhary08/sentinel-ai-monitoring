/** ISO-week helpers (Monday-start, UTC) — the frontend mirror of the
 *  backend's week math in domain/activity/queries.py. The server is always
 *  authoritative (it echoes week/week_start/week_end in the digest payload);
 *  these only drive the week picker and its prev/next navigation. */

const MS_WEEK = 7 * 24 * 60 * 60 * 1000;

/** Monday of ISO week 1 of a calendar year (the week containing Jan 4). */
function week1Monday(year: number): Date {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() + 6) % 7));
  return monday;
}

/** The Monday of the week containing d. */
function mondayOf(d: Date): Date {
  const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7));
  return monday;
}

/** A date → its ISO week label, e.g. "2026-W43". Handles the year-boundary
 *  edges: early January can belong to the previous ISO year's last week, and
 *  late December to the next year's W01. */
export function weekLabelOf(d: Date): string {
  const monday = mondayOf(d);
  let year = monday.getUTCFullYear();
  let w1 = week1Monday(year);
  if (monday.getTime() < w1.getTime()) {
    year -= 1;
    w1 = week1Monday(year);
  } else {
    const next = week1Monday(year + 1);
    if (monday.getTime() >= next.getTime()) {
      year += 1;
      w1 = next;
    }
  }
  const week = 1 + Math.round((monday.getTime() - w1.getTime()) / MS_WEEK);
  return `${year}-W${String(week).padStart(2, "0")}`;
}

/** The current ISO week label (what the backend defaults to). */
export const currentWeekLabel = (): string => weekLabelOf(new Date());

/** "2026-W43" + (−1|+1) → the neighbouring week's label. */
export function shiftWeekLabel(label: string, deltaWeeks: number): string {
  const match = /^(\d{4})-W(\d{2})$/.exec(label);
  if (!match) return label;
  const jan4 = new Date(Date.UTC(Number(match[1]), 0, 4));
  const monday = new Date(jan4);
  monday.setUTCDate(
    jan4.getUTCDate() - ((jan4.getUTCDay() + 6) % 7) + (Number(match[2]) - 1) * 7 + deltaWeeks * 7,
  );
  return weekLabelOf(monday);
}
