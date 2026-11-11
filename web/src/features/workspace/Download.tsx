import { ChevronDown, Download as DownloadIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { ExportFormat } from "@/api/types";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { sleep } from "@/lib/sleep";
import { said } from "@/state/resource";

const FORMATS: readonly { format: ExportFormat; label: string; hint: string }[] = [
  { format: "step", label: "STEP", hint: "For CAD software" },
  { format: "stl", label: "STL", hint: "For slicers and printers" },
  { format: "3mf", label: "3MF", hint: "For slicers, with its unit" },
];

const POLL_MS = 500;

/** The server's file name decides what the browser saves it as, so this only hands the browser the link. */
function save(url: string, filename: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
}

type Saving = { status: "idle" } | { status: "preparing" } | { status: "failed"; reason: string };

/** Download one revision. The server makes the files once per shape, so the first ask may answer
 * pending: it is asked again every POLL_MS until the file is ready, then saved. The stage keys it by
 * the revision, so showing another one starts from a clean button. */
export function Download(props: { variantId: string; briefId: string }) {
  const { variantId, briefId } = props;
  const { api } = useServices();
  const [saving, setSaving] = useState<Saving>({ status: "idle" });
  const running = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      running.current?.abort();
    },
    [],
  );
  const start = async (format: ExportFormat) => {
    running.current?.abort();
    const own = new AbortController();
    running.current = own;
    const stale = () => own.signal.aborted;
    setSaving({ status: "preparing" });
    try {
      for (;;) {
        const read = await api.exportOf(variantId, briefId, format);
        if (stale()) return;
        if (read.kind === "ready") {
          save(read.url, read.filename);
          setSaving({ status: "idle" });
          return;
        }
        if (read.kind === "failed") {
          setSaving({ status: "failed", reason: read.reason });
          return;
        }
        await sleep(POLL_MS, own.signal);
        if (stale()) return;
      }
    } catch (error) {
      if (!stale()) setSaving({ status: "failed", reason: said(error) });
    }
  };
  const preparing = saving.status === "preparing";
  return (
    <div className="relative">
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={preparing}
          data-download
          className="flex items-center gap-1.5 rounded-full border border-rule bg-panel-2 px-3 py-1.5 text-[14px] text-ink shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
        >
          <DownloadIcon aria-hidden className="size-4" />
          {preparing ? "Preparing…" : "Download"}
          <ChevronDown aria-hidden className="size-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {FORMATS.map((one) => (
            <DropdownMenuItem
              key={one.format}
              onSelect={() => {
                void start(one.format);
              }}
            >
              <b className="text-[14px] font-semibold">{one.label}</b>
              <span className="text-[13px] leading-snug text-ink-2">{one.hint}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {saving.status === "failed" ? (
        <p role="alert" className="absolute right-0 top-full z-40 mt-1 w-64 rounded-md border border-rule bg-panel px-2.5 py-1.5 text-[13px] text-fail shadow-sm">
          {saving.reason}
        </p>
      ) : null}
    </div>
  );
}
