export default function TopBar() {
  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-sm font-semibold text-primary-foreground">
          SI
        </div>
        <div>
          <div className="text-sm font-semibold tracking-tight">
            Standards Intelligence
          </div>
          <div className="text-xs text-muted-foreground">
            Standards discovery & quotation workspace
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span className="size-2 rounded-full bg-emerald-500" />
        Database connected
      </div>
    </header>
  );
}
