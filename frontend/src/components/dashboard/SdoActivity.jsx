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
      {breakdown.map((item) => {
        const width = (item.count / maximum) * 100;

        return (
          <div key={item.name} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-muted-foreground">{item.name}</span>
              <strong>{item.count}</strong>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${width}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
