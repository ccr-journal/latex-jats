import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button, buttonVariants } from "@/components/ui/button";
import { LogViewer } from "@/components/LogViewer";
import { getManuscript, downloadUrl, outputUrl, presign } from "@/api/client";
import type { Manuscript } from "@/api/types";

export function PreviewPage() {
  const { doiSuffix } = useParams<{ doiSuffix: string }>();
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [showLog, setShowLog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [presignToken, setPresignToken] = useState<string | null>(null);

  useEffect(() => {
    if (!doiSuffix) return;
    getManuscript(doiSuffix)
      .then(setManuscript)
      .catch((err) => setError(err.message));
  }, [doiSuffix]);

  // Fetch a presign token once the manuscript is ready (needed for iframe src)
  useEffect(() => {
    if (!doiSuffix || !manuscript || manuscript.status !== "ready") return;
    presign(doiSuffix)
      .then(setPresignToken)
      .catch((err) => setError(err.message));
  }, [doiSuffix, manuscript?.status]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!manuscript || !doiSuffix) return <p className="text-muted-foreground">Loading...</p>;

  if (manuscript.status !== "ready") {
    return (
      <div className="space-y-4">
        <Link to={`/manuscripts/${doiSuffix}`} className="text-sm text-muted-foreground hover:text-foreground">
          &larr; Back
        </Link>
        <p className="text-muted-foreground">Preview is not available yet. Manuscript status: {manuscript.status}</p>
      </div>
    );
  }

  if (!presignToken) return <p className="text-muted-foreground">Loading preview...</p>;

  // The HTML file is named after the article ID extracted from the DOI suffix.
  // For "CCR2025.1.2.YAO", the article ID is the full doi_suffix.
  // The worker generates {article_id}.html in the convert output dir.
  const htmlUrl = outputUrl(doiSuffix, `${doiSuffix}.html`, presignToken);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Link
          to={`/manuscripts/${doiSuffix}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back
        </Link>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowLog(!showLog)}>
            {showLog ? "Hide Log" : "Show Log"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              const token = await presign(doiSuffix);
              window.open(outputUrl(doiSuffix, `${doiSuffix}.pdf`, token), "_blank");
            }}
          >
            View PDF
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              const token = await presign(doiSuffix);
              const a = document.createElement("a");
              a.href = downloadUrl(doiSuffix, token);
              a.download = "";
              a.click();
            }}
          >
            Download ZIP
          </Button>
        </div>
      </div>

      {showLog && manuscript.job_log && <LogViewer log={manuscript.job_log} />}

      <iframe
        src={htmlUrl}
        title="HTML Proof Preview"
        className="w-full rounded-md border bg-white"
        style={{ height: "80vh" }}
      />
    </div>
  );
}
