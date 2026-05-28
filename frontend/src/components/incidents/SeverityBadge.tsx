import clsx from "clsx";
import type { Severity } from "@/lib/incidents";

const COLORS: Record<Severity, string> = {
  info: "bg-aegis-border text-aegis-muted",
  low: "bg-aegis-border text-aegis-text",
  medium: "bg-aegis-warn/20 text-aegis-warn",
  high: "bg-aegis-danger/20 text-aegis-danger",
  critical: "bg-aegis-danger text-aegis-bg",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest",
        COLORS[severity],
      )}
    >
      {severity}
    </span>
  );
}
