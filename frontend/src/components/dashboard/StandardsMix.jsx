const COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];
const RADIUS = 43;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function getChartItems(breakdown) {
  const sorted = [...breakdown]
    .map((item) => ({ ...item, count: Number(item.count) || 0 }))
    .filter((item) => item.count > 0)
    .sort((left, right) => right.count - left.count);

  if (sorted.length <= 5) return sorted;

  const topItems = sorted.slice(0, 4);
  const otherCount = sorted.slice(4).reduce((sum, item) => sum + item.count, 0);
  return [...topItems, { name: "Other", count: otherCount }];
}

export default function StandardsMix({ dashboard }) {
  const items = getChartItems(dashboard?.sdoBreakdown || []);
  const total = Number(dashboard?.total) || 0;

  if (!items.length || total === 0) {
    return (
      <div className="grid min-h-36 place-items-center rounded-xl border border-dashed border-border/70 px-4 text-center text-sm text-muted-foreground">
        The chart will appear when standards are matched.
      </div>
    );
  }

  let offset = 0;
  const segments = items.map((item, index) => {
    const fraction = item.count / total;
    const length = fraction * CIRCUMFERENCE;
    const segment = {
      ...item,
      color: COLORS[index % COLORS.length],
      percentage: Math.round(fraction * 100),
      dashArray: `${Math.max(0, length - 2)} ${CIRCUMFERENCE - Math.max(0, length - 2)}`,
      dashOffset: -offset,
    };
    offset += length;
    return segment;
  });

  return (
    <div className="grid grid-cols-[minmax(112px,0.8fr)_minmax(0,1.2fr)] items-center gap-3 sm:gap-4">
      <div className="relative mx-auto aspect-square w-full max-w-36">
        <svg
          viewBox="0 0 100 100"
          className="size-full -rotate-90 overflow-visible"
          role="img"
          aria-label={`Standards mix for ${total} matched standards`}
        >
          <circle
            cx="50"
            cy="50"
            r={RADIUS}
            fill="none"
            stroke="var(--muted)"
            strokeWidth="12"
          />
          {segments.map((segment) => (
            <circle
              key={segment.name}
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              stroke={segment.color}
              strokeWidth="12"
              strokeDasharray={segment.dashArray}
              strokeDashoffset={segment.dashOffset}
              className="chart-segment transition-all duration-500 motion-reduce:transition-none"
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <strong className="text-2xl font-semibold tabular-nums tracking-tight text-foreground">
            {total}
          </strong>
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            matched
          </span>
        </div>
      </div>

      <ul className="flex min-w-0 flex-col gap-3" aria-label="Standards by organization">
        {segments.map((segment) => (
          <li key={segment.name} className="flex min-w-0 items-center gap-2">
            <span
              className="size-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: segment.color }}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate text-xs font-medium text-muted-foreground" title={segment.name}>
              {segment.name}
            </span>
            <span className="shrink-0 text-right text-xs font-semibold tabular-nums text-foreground">
              {segment.percentage}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
