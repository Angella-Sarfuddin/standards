const DOTS = [
  "bg-chart-1",
  "bg-chart-2",
  "bg-chart-3",
  "bg-chart-4",
  "bg-chart-5",
];

export default function StandardsMix({ dashboard }) {
  const total = dashboard?.total || 0;
  const items = (dashboard?.sdoBreakdown || []).slice(0, 5);

  return (
    <div className="flex items-center gap-4">
      <div
        className="relative grid size-28 shrink-0 place-items-center rounded-full"
        style={{
          background:
            "conic-gradient(#7257ff 0deg, #8e78ff 110deg, #4187f5 190deg, #21a66b 255deg, #e7952f 320deg, #7257ff 360deg)",
        }}
      >
        <div className="absolute inset-3 rounded-full bg-card" />
        <div className="relative z-10 flex flex-col items-center">
          <strong className="text-xl tracking-tight">{total}</strong>
          <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            standards
          </span>
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {items.map((item, index) => {
          const percentage = Math.round((item.count / (total || 1)) * 100);

          return (
            <div
              key={item.name}
              className="grid grid-cols-[8px_1fr_auto] items-center gap-2 text-xs"
            >
              <span className={`size-2 rounded-full ${DOTS[index] || DOTS[0]}`} />
              <span className="truncate">{item.name}</span>
              <strong>{percentage}%</strong>
            </div>
          );
        })}
        {!items.length && (
          <p className="text-sm text-muted-foreground">No matched standards yet.</p>
        )}
      </div>
    </div>
  );
}
