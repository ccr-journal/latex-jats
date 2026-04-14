import { Badge } from "@/components/ui/badge";
import type { ManuscriptStatus } from "@/api/types";

const config: Record<ManuscriptStatus, { label: string; className: string }> = {
  draft: { label: "Draft", className: "bg-gray-100 text-gray-600 hover:bg-gray-100" },
  uploaded: { label: "Uploaded", className: "bg-slate-100 text-slate-700 hover:bg-slate-100" },
  queued: { label: "Queued", className: "bg-amber-100 text-amber-700 hover:bg-amber-100" },
  processing: { label: "Processing", className: "bg-blue-100 text-blue-700 hover:bg-blue-100 animate-pulse" },
  ready: { label: "Ready", className: "bg-green-100 text-green-700 hover:bg-green-100" },
  failed: { label: "Failed", className: "bg-red-100 text-red-700 hover:bg-red-100" },
  published: { label: "Published", className: "bg-teal-100 text-teal-700 hover:bg-teal-100" },
};

export function StatusBadge({ status }: { status: ManuscriptStatus }) {
  const { label, className } = config[status];
  return <Badge className={className}>{label}</Badge>;
}
