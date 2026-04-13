import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { LogViewer } from "@/components/LogViewer";
import { UploadZone } from "@/components/UploadZone";
import { getManuscript, getStatus, uploadFiles, downloadUrl, outputUrl } from "@/api/client";
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

export function ManuscriptPage() {
  const { doiSuffix } = useParams<{ doiSuffix: string }>();
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initial fetch
  useEffect(() => {
    if (!doiSuffix) return;
    getManuscript(doiSuffix)
      .then(setManuscript)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [doiSuffix]);

  // Status polling when queued or processing
  useEffect(() => {
    if (!doiSuffix || !manuscript) return;
    if (manuscript.status !== "queued" && manuscript.status !== "processing") return;

    const id = setInterval(async () => {
      try {
        const updated = await getStatus(doiSuffix);
        setManuscript(updated);
        if (updated.status !== "queued" && updated.status !== "processing") {
          clearInterval(id);
        }
      } catch {
        // Ignore transient errors during polling
      }
    }, 3000);

    return () => clearInterval(id);
  }, [doiSuffix, manuscript?.status]);

  if (loading) return <p className="text-muted-foreground">Loading...</p>;
  if (error) return <p className="text-red-600">{error}</p>;
  if (!manuscript || !doiSuffix) return <p className="text-red-600">Manuscript not found</p>;

  const canUpload = ["draft", "ready", "failed"].includes(manuscript.status);
  const isProcessing = manuscript.status === "queued" || manuscript.status === "processing";
  const isReady = manuscript.status === "ready";

  const handleUpload = async (files: File[], fix: boolean) => {
    const updated = await uploadFiles(doiSuffix, files, "editor", fix);
    setManuscript(updated);
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
          &larr; Manuscripts
        </Link>
      </div>

      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-xl">{manuscript.title}</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">{manuscript.doi_suffix}</p>
            </div>
            <StatusBadge status={manuscript.status} />
          </div>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">Created</dt>
              <dd>{formatDate(manuscript.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Updated</dt>
              <dd>{formatDate(manuscript.updated_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Uploaded</dt>
              <dd>{formatDate(manuscript.uploaded_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Uploaded by</dt>
              <dd>{manuscript.uploaded_by ?? "\u2014"}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Processing indicator */}
      {isProcessing && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Converting...</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 mb-4">
              <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-sm text-muted-foreground">
                Pipeline is {manuscript.status}
              </span>
            </div>
            <LogViewer log={manuscript.job_log} />
          </CardContent>
        </Card>
      )}

      {/* Actions when ready */}
      {isReady && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Output</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-3">
            <Button asChild>
              <a href={downloadUrl(doiSuffix)} download>
                Download ZIP
              </a>
            </Button>
            <Button variant="outline" asChild>
              <Link to={`/manuscripts/${doiSuffix}/preview`}>View HTML Proof</Link>
            </Button>
            <Button variant="outline" asChild>
              <a href={outputUrl(doiSuffix, `${doiSuffix}.pdf`)} target="_blank" rel="noopener">
                View PDF
              </a>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Upload zone */}
      {canUpload && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {manuscript.status === "draft" ? "Upload Source" : "Re-upload Source"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <UploadZone onUpload={handleUpload} />
          </CardContent>
        </Card>
      )}

      {/* Log (always visible when non-empty, unless already shown in processing) */}
      {!isProcessing && manuscript.job_log && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Conversion Log</CardTitle>
          </CardHeader>
          <CardContent>
            <LogViewer log={manuscript.job_log} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
