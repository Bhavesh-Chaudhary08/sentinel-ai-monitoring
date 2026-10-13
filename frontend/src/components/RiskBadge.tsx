import type { AlertSeverity, PolicyAction, RiskCategory } from "../api/client";

const TONES: Record<string, string> = {
  gray: "badge gray",
  green: "badge green",
  amber: "badge amber",
  red: "badge red",
  blue: "badge blue",
  purple: "badge purple",
};

function toneForCategory(category: RiskCategory): string {
  switch (category) {
    case "credentials":
      return TONES.red;
    case "pii":
      return TONES.purple;
    case "financial":
      return TONES.amber;
    case "confidential":
      return TONES.red;
    case "source_code":
      return TONES.blue;
    case "other":
      return TONES.gray;
    default:
      return TONES.green;
  }
}

export function CategoryBadge({ category }: { category: RiskCategory }) {
  return <span className={toneForCategory(category)}>{category.replace("_", " ")}</span>;
}

export function ActionBadge({
  action,
  status,
}: {
  action: PolicyAction | null;
  status?: "pending" | "complete" | "failed" | "skipped" | undefined;
}) {
  if (status === "skipped") return <span className="badge blue">response only</span>;
  if (status === "failed") return <span className="badge red">classify failed</span>;
  if (!action) return <span className="badge gray">classifying…</span>;
  const tone = action === "block" ? "red" : action === "warn" ? "amber" : "gray";
  return <span className={`badge ${tone}`}>{action.replace("_", " ")}</span>;
}

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const tone =
    severity === "critical" ? "red" : severity === "high" ? "red" : severity === "medium" ? "amber" : "blue";
  return <span className={`badge ${tone}`}>{severity}</span>;
}

export function ScoreBadge({ score, flagged }: { score: number; flagged: boolean }) {
  return <span className={`badge ${flagged ? "red" : "gray"}`}>{score.toFixed(2)}</span>;
}

export function RiskBadge({ risk }: { risk: "low" | "medium" | "high" | "unknown" | null }) {
  const tone =
    risk === "high" ? "red" : risk === "medium" ? "amber" : risk === "low" ? "blue" : "gray";
  return <span className={`badge ${tone}`}>{risk ?? "unknown"}</span>;
}
