import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
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
import { useAuth } from "@/auth/AuthContext";

function formatAuthors(authors: { name: string | null }[]): string {
  const names = authors.map((a) => a.name ?? "Unknown");
  if (names.length === 0) return "";
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} & ${names[1]}`;
  return `${names[0]} et al.`;
}

export function DashboardPage() {
  const [manuscripts, setManuscripts] = useState<Manuscript[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const isEditor = user?.role === "editor";

  // Token-scoped authors should never see the dashboard
  if (user?.manuscript_token_scope) {
    return <Navigate to={`/manuscripts/${user.manuscript_token_scope}`} replace />;
  }

  useEffect(() => {
    setLoading(true);
    listManuscripts(showArchived)
      .then(setManuscripts)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [showArchived]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Manuscripts</h1>
        <div className="flex items-center gap-4">
          {isEditor && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="h-4 w-4 rounded border-input accent-primary"
              />
              Show archived
            </label>
          )}
          {isEditor && (
            <CreateManuscriptDialog
              onCreated={(ms) => navigate(`/manuscripts/${ms.doi_suffix}`)}
            />
          )}
        </div>
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
                <TableHead>Authors</TableHead>
                <TableHead>Title</TableHead>
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
                  <TableCell
                    className="text-muted-foreground max-w-[12rem] truncate text-sm"
                    title={formatAuthors(ms.authors)}
                  >
                    {formatAuthors(ms.authors) || "\u2014"}
                  </TableCell>
                  <TableCell
                    className="text-muted-foreground max-w-[20rem] truncate text-sm"
                    title={ms.title ?? undefined}
                  >
                    {ms.title ?? "\u2014"}
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
