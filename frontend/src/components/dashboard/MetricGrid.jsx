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
    <div className="grid grid-cols-2 gap-2">
      {METRICS.map((metric) => (
        <Card
          key={metric.key}
          className={metric.featured ? "border-primary/30 bg-primary/5" : ""}
        >
          <CardContent className="flex flex-col gap-1 p-3">
            <span className="text-xs text-muted-foreground">{metric.label}</span>
            <strong className="text-2xl font-semibold tracking-tight">
              {dashboard?.[metric.key] || 0}
            </strong>
            <small className="text-xs text-muted-foreground">{metric.hint}</small>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
