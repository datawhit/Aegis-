/**
 * Inline SVG trend chart — Sprint 11.
 *
 * No chart library. The Risk Analytics page renders one larger area+line
 * chart for the score timeline, and Category rows render tiny "sparkline"
 * variants of the same component. Single implementation for both.
 */

type Point = { x: number; y: number };

export function TrendChart({
  data,
  width = 600,
  height = 140,
  paddingX = 24,
  paddingY = 16,
  yMin,
  yMax,
  label,
  variant = "full",
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  paddingX?: number;
  paddingY?: number;
  yMin?: number;
  yMax?: number;
  label?: string;
  variant?: "full" | "sparkline";
  className?: string;
}) {
  if (data.length === 0) {
    return (
      <div className="font-mono text-[10px] text-aegis-muted">
        no samples in this window
      </div>
    );
  }
  const minObserved = Math.min(...data);
  const maxObserved = Math.max(...data);
  const lo = yMin ?? Math.min(0, minObserved);
  const hi = yMax ?? Math.max(maxObserved, lo + 1);

  const innerW = width - paddingX * 2;
  const innerH = height - paddingY * 2;
  const stepX = data.length > 1 ? innerW / (data.length - 1) : 0;

  const points: Point[] = data.map((v, i) => ({
    x: paddingX + i * stepX,
    y:
      paddingY +
      innerH -
      ((v - lo) / Math.max(hi - lo, 1)) * innerH,
  }));

  const lineD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");
  const areaD =
    `M ${paddingX.toFixed(1)} ${(paddingY + innerH).toFixed(1)} ` +
    points.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") +
    ` L ${(paddingX + innerW).toFixed(1)} ${(paddingY + innerH).toFixed(1)} Z`;

  const last = points[points.length - 1];
  const isSparkline = variant === "sparkline";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className ?? (isSparkline ? "h-6 w-full" : "h-36 w-full")}
      role="img"
      aria-label={label ?? "trend chart"}
    >
      {!isSparkline && (
        <>
          <line
            x1={paddingX}
            x2={width - paddingX}
            y1={paddingY + innerH}
            y2={paddingY + innerH}
            stroke="currentColor"
            strokeOpacity={0.15}
          />
          <line
            x1={paddingX}
            x2={paddingX}
            y1={paddingY}
            y2={paddingY + innerH}
            stroke="currentColor"
            strokeOpacity={0.15}
          />
        </>
      )}
      <path
        d={areaD}
        fill="currentColor"
        fillOpacity={isSparkline ? 0.15 : 0.12}
      />
      <path
        d={lineD}
        fill="none"
        stroke="currentColor"
        strokeWidth={isSparkline ? 1 : 1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {!isSparkline && last && (
        <circle cx={last.x} cy={last.y} r={3} fill="currentColor" />
      )}
    </svg>
  );
}
