import WeeklyDigest from "../../components/WeeklyDigest";

/**
 * Employee weekly digest (Phase 4): their week on a page — browser-time
 * totals, the focus rollup and the week's AI-usage counts, with a CSV export
 * they can keep (transparency right, same as the interactions export).
 */
export default function MyDigest() {
  return (
    <>
      <h1>Weekly digest</h1>
      <p className="page-sub">
        Your week on a page: where browser hours went, how focused they were,
        and which AI tools were used — the same numbers the dashboard shows
        everywhere else, summarized. Per-person by design: there is no team
        ranking, and this describes browser behaviour, not the quality of your
        work.
      </p>
      <WeeklyDigest />
    </>
  );
}
