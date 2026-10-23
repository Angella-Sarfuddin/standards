import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
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
    <aside className="rounded-xl border bg-card">
      <ScrollArea className="h-[calc(100vh-8rem)]">
        <div className="flex flex-col gap-4 p-4">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs tracking-[0.16em] text-muted-foreground">
                QUOTATION INTELLIGENCE
              </div>
              <h2 className="text-xl font-semibold">Dashboard</h2>
            </div>
            <Badge className="bg-emerald-100 text-emerald-800">LIVE</Badge>
          </div>

          <MetricGrid dashboard={dashboard} />

          <Card>
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

          <Card>
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

          <Card>
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
      </ScrollArea>
    </aside>
  );
}
