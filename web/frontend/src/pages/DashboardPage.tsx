import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { CreateManuscriptDialog } from "@/components/CreateManuscriptDialog";
import { listManuscripts } from "@/api/client";
import type { Manuscript } from "@/api/types";

function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DashboardPage() {
  const [manuscripts, setManuscripts] = useState<Manuscript[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    listManuscripts()
      .then(setManuscripts)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Manuscripts</h1>
        <CreateManuscriptDialog
          onCreated={(ms) => navigate(`/manuscripts/${ms.doi_suffix}`)}
        />
      </div>

      {loading && <p className="text-muted-foreground">Loading...</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && manuscripts.length === 0 && (
        <p className="text-muted-foreground py-8 text-center">
          No manuscripts yet. Create one to get started.
        </p>
      )}

      {manuscripts.length > 0 && (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>DOI Suffix</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {manuscripts.map((ms) => (
                <TableRow key={ms.doi_suffix}>
                  <TableCell>
                    <Link
                      to={`/manuscripts/${ms.doi_suffix}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {ms.doi_suffix}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={ms.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {formatDate(ms.uploaded_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {formatDate(ms.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
