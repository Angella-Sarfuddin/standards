import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export default function ManualSearchDialog({
  open,
  value,
  loading,
  onChange,
  onSubmit,
  onCancel,
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onCancel();
        }
      }}
    >
      <DialogContent className="rounded-2xl border-border/80 p-5 shadow-xl sm:max-w-md sm:p-6">
        <DialogHeader>
          <div className="text-[11px] font-semibold tracking-[0.14em] text-primary">
            MANUAL SEARCH
          </div>
          <DialogTitle className="text-xl tracking-tight">Find this standard</DialogTitle>
          <DialogDescription className="leading-6">
            The automatic lookup did not resolve this row. Search manually.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium tracking-wide text-muted-foreground">
            SEARCH
          </span>
          <Input
            className="h-11 rounded-xl bg-background px-3"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onSubmit();
              }
            }}
            placeholder="Enter standard number..."
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" className="h-10 rounded-xl" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={onSubmit}
            className="h-10 rounded-xl"
            disabled={loading || !value.trim()}
          >
            {loading ? <Spinner /> : null}
            {loading ? "Searching..." : "Search Database"}
            {loading ? null : <ArrowRight />}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
