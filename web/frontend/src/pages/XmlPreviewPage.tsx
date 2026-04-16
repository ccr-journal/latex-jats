import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { XmlViewer } from "@/components/XmlViewer";
import { getManuscript, outputUrl, presign, downloadUrl } from "@/api/client";
import type { Manuscript } from "@/api/types";

export function XmlPreviewPage() {
  const { doiSuffix } = useParams<{ doiSuffix: string }>();
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [xmlText, setXmlText] = useState<string | null>(null);
  const [presignToken, setPresignToken] = useState<string | null>(null);

  useEffect(() => {
    if (!doiSuffix) return;
    getManuscript(doiSuffix)
      .then(setManuscript)
      .catch((err) => setError(err.message));
  }, [doiSuffix]);

  // Fetch presign token + XML text once ready
  useEffect(() => {
    if (!doiSuffix || !manuscript || manuscript.status !== "ready") return;
    presign(doiSuffix)
      .then((token) => {
        setPresignToken(token);
        const url = outputUrl(doiSuffix, `${doiSuffix}.xml`, token);
        return fetch(url);
      })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to fetch XML: ${res.statusText}`);
        return res.text();
      })
      .then(setXmlText)
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
        <p className="text-muted-foreground">XML preview is not available yet. Manuscript status: {manuscript.status}</p>
      </div>
    );
  }

  if (!xmlText || !presignToken) return <p className="text-muted-foreground">Loading XML...</p>;

  const xmlUrl = outputUrl(doiSuffix, `${doiSuffix}.xml`, presignToken);

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
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(xmlUrl, "_blank")}
          >
            Open raw XML
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

      <XmlViewer xml={xmlText} />
    </div>
  );
}
