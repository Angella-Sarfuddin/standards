import { Button } from "@/components/ui/button";

const FILTERS = [
  { id: "found", label: "Found", tone: "text-emerald-700" },
  { id: "not_found", label: "Not Found", tone: "text-amber-700" },
  { id: "sdo_missing", label: "SDO Missing", tone: "text-slate-600" },
  { id: "selected", label: "Selected", tone: "text-primary" },
];

export default function ResultStatStrip({
  resultViewFilter,
  matchedCount,
  notFoundCount,
  sdoNotFoundCount,
  selectedCount,
  onToggleFilter,
}) {
  const counts = {
    found: matchedCount,
    not_found: notFoundCount,
    sdo_missing: sdoNotFoundCount,
    selected: selectedCount,
  };

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {FILTERS.map((filter) => {
        const active = resultViewFilter === filter.id;

        return (
          <Button
            key={filter.id}
            type="button"
            variant={active ? "default" : "outline"}
            className="h-auto w-full min-w-0 flex-col items-start gap-1 rounded-xl border-border/70 px-3.5 py-3.5 text-left whitespace-normal shadow-none"
            onClick={() => onToggleFilter(filter.id)}
            aria-pressed={active}
          >
            <span className={active ? "text-primary-foreground/80" : filter.tone}>
              {filter.label}
            </span>
            <span className="text-xl font-semibold tabular-nums tracking-tight">{counts[filter.id]}</span>
          </Button>
        );
      })}
    </div>
  );
}
