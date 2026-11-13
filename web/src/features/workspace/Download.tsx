import { ChevronDown, Download as DownloadIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { ExportFormat } from "@/api/types";
import { Shimmer } from "@/components/ui/busy";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { toast } from "@/components/ui/toaster";
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

/** Download one revision. The server makes the files once per shape, so the first ask may answer
 * pending: it is asked again every POLL_MS until the file is ready, then saved. The stage keys it by
 * the revision, so showing another one starts from a clean button. */
export function Download(props: { variantId: string; briefId: string }) {
  const { variantId, briefId } = props;
  const { api } = useServices();
  const [preparing, setPreparing] = useState(false);
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
    setPreparing(true);
    try {
      for (;;) {
        const read = await api.exportOf(variantId, briefId, format);
        if (stale()) return;
        if (read.kind === "ready") {
          save(read.url, read.filename);
          setPreparing(false);
          return;
        }
        if (read.kind === "failed") {
          setPreparing(false);
          toast.error(read.reason);
          return;
        }
        await sleep(POLL_MS, own.signal);
        if (stale()) return;
      }
    } catch (error) {
      if (!stale()) {
        setPreparing(false);
        toast.error(said(error));
      }
    }
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={preparing}
        aria-busy={preparing}
        data-download
        className="flex items-center gap-1.5 rounded-full border border-rule bg-panel-2 px-3 py-1.5 text-[14px] text-ink shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
      >
        <DownloadIcon aria-hidden className="size-4" />
        {preparing ? <Shimmer>Preparing…</Shimmer> : "Download"}
        <ChevronDown aria-hidden className="size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {FORMATS.map((one) => (
          <DropdownMenuItem
            key={one.format}
            onClick={() => {
              void start(one.format);
            }}
          >
            <b className="text-[14px] font-semibold">{one.label}</b>
            <span className="text-[13px] leading-snug text-ink-2">{one.hint}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
