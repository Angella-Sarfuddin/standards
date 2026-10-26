const BAR_COLORS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"];

export default function SdoActivity({ breakdown }) {
  if (!breakdown?.length) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        No matched standards yet.
      </div>
    );
  }

  const maximum = Math.max(...breakdown.map((item) => item.count), 1);

  return (
    <div className="flex flex-col gap-3">
      {breakdown.map((item, index) => {
        const width = (item.count / maximum) * 100;

        return (
          <div key={item.name} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="min-w-0 truncate font-medium text-muted-foreground" title={item.name}>{item.name}</span>
              <strong className="shrink-0 tabular-nums">{item.count}</strong>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none ${BAR_COLORS[index % BAR_COLORS.length]}`}
                style={{ width: `${width}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
