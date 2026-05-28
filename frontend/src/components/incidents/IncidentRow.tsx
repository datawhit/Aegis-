import { Link } from "react-router-dom";
import { SeverityBadge } from "./SeverityBadge";
import type { IncidentSummary } from "@/lib/incidents";

export function IncidentRow({ incident }: { incident: IncidentSummary }) {
  const confidence =
    incident.ai_confidence === null
      ? "—"
      : `${Math.round(incident.ai_confidence * 100)}%`;

  return (
    <Link
      to={`/incidents/${incident.id}`}
      className="flex items-center gap-4 border-b border-aegis-border px-4 py-3 hover:bg-aegis-bg/60"
    >
      <SeverityBadge severity={incident.severity} />
      <span className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {incident.status}
      </span>
      <span className="flex-1 truncate text-sm text-aegis-text">
        {incident.title}
      </span>
      <span className="font-mono text-xs text-aegis-muted">
        ai {confidence}
      </span>
      <span className="font-mono text-[10px] text-aegis-muted">
        {new Date(incident.created_at).toLocaleString()}
      </span>
    </Link>
  );
}
