import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import MetricGrid from "./MetricGrid.jsx";
import RelatedGroups from "./RelatedGroups.jsx";
import SdoActivity from "./SdoActivity.jsx";
import StandardsMix from "./StandardsMix.jsx";

export default function DashboardPanel({
  dashboard,
  openGroupIndex,
  onToggleGroup,
}) {
  return (
    <aside className="min-w-0 rounded-2xl border border-border/70 bg-card shadow-sm xl:sticky xl:top-20 xl:max-h-[calc(100svh_-_6rem)] xl:overflow-y-auto xl:overscroll-contain">
      <div className="flex min-w-0 flex-col gap-4 p-4 sm:p-5">
        <div className="-mx-4 -mt-4 flex items-start justify-between bg-card px-4 pb-3 pt-4 sm:-mx-5 sm:-mt-5 sm:px-5 sm:pt-5 xl:sticky xl:top-0 xl:z-10 xl:bg-card/95 xl:backdrop-blur">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.14em] text-primary">
              QUOTATION INTELLIGENCE
            </div>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">Dashboard</h2>
          </div>
        </div>

        <MetricGrid dashboard={dashboard} />

        <Card className="gap-3 border border-border/70 bg-background/70 shadow-none ring-0">
          <CardHeader>
            <CardTitle>Standards Mix</CardTitle>
            <p className="text-sm text-muted-foreground">
              Distribution across SDOs
            </p>
          </CardHeader>
          <CardContent>
            <StandardsMix dashboard={dashboard} />
          </CardContent>
        </Card>

        <Card className="gap-3 border border-border/70 bg-background/70 shadow-none ring-0">
          <CardHeader>
            <CardTitle>SDO Activity</CardTitle>
            <p className="text-sm text-muted-foreground">
              Verified standards by organization
            </p>
          </CardHeader>
          <CardContent>
            <SdoActivity breakdown={dashboard?.sdoBreakdown} />
          </CardContent>
        </Card>

        <Card className="gap-3 border border-border/70 bg-background/70 shadow-none ring-0">
          <CardHeader>
            <CardTitle>Related Standards</CardTitle>
            <p className="text-sm text-muted-foreground">
              Same classification code
            </p>
            <CardAction>
              <Badge variant="secondary">{dashboard?.groupCount || 0}</Badge>
            </CardAction>
          </CardHeader>
          <CardContent>
            <RelatedGroups
              dashboard={dashboard}
              openGroupIndex={openGroupIndex}
              onToggleGroup={onToggleGroup}
            />
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground">
          Related groups are built from shared classifications across your
          verified standards.
        </p>
      </div>
    </aside>
  );
}
