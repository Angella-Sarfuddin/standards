import { Card, CardContent } from "@/components/ui/card";

const METRICS = [
  {
    key: "total",
    label: "Verified",
    hint: "matched standards",
    featured: true,
  },
  {
    key: "groupCount",
    label: "Related Groups",
    hint: "classification groups",
  },
  {
    key: "individualCount",
    label: "Individual",
    hint: "individual buckets",
  },
  {
    key: "updatedEditionCount",
    label: "Updated editions",
    hint: "newer catalogue year supplied",
  },
];

export default function MetricGrid({ dashboard }) {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {METRICS.map((metric) => (
        <Card
          key={metric.key}
          className={`min-w-0 border border-border/70 shadow-none ring-0 ${metric.featured ? "bg-primary/[0.045]" : "bg-background/70"}`}
        >
          <CardContent className="flex min-h-[104px] flex-col items-start gap-1.5 p-3.5 sm:p-4">
            <span className="text-xs font-medium leading-4 text-muted-foreground">{metric.label}</span>
            <strong className="text-2xl font-semibold tabular-nums tracking-tight sm:text-[1.75rem]">
              {dashboard?.[metric.key] || 0}
            </strong>
            <small className="text-[11px] leading-4 text-muted-foreground">{metric.hint}</small>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
