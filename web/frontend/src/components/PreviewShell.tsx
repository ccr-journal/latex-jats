import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button, buttonVariants } from "@/components/ui/button";
import { getManuscript, downloadUrl, presign } from "@/api/client";
import type { Manuscript } from "@/api/types";

type PreviewTab = "preview" | "pdf" | "xml";

interface PreviewShellProps {
  activeTab: PreviewTab;
  children: (args: { doiSuffix: string; presignToken: string }) => React.ReactNode;
}

const TABS: { key: PreviewTab; label: string }[] = [
  { key: "preview", label: "HTML" },
  { key: "pdf", label: "PDF" },
  { key: "xml", label: "XML" },
];

export function PreviewShell({ activeTab, children }: PreviewShellProps) {
  const { doiSuffix } = useParams<{ doiSuffix: string }>();
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [presignToken, setPresignToken] = useState<string | null>(null);

  useEffect(() => {
    if (!doiSuffix) return;
    getManuscript(doiSuffix)
      .then(setManuscript)
      .catch((err) => setError(err.message));
  }, [doiSuffix]);

  useEffect(() => {
    if (!doiSuffix || !manuscript || (manuscript.status !== "ready" && manuscript.status !== "approved")) return;
    presign(doiSuffix)
      .then(setPresignToken)
      .catch((err) => setError(err.message));
  }, [doiSuffix, manuscript?.status]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!manuscript || !doiSuffix) return <p className="text-muted-foreground">Loading...</p>;

  if (manuscript.status !== "ready" && manuscript.status !== "approved") {
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
          {TABS.map((tab) => (
            <Link
              key={tab.key}
              to={`/manuscripts/${doiSuffix}/${tab.key}`}
              className={buttonVariants({
                variant: tab.key === activeTab ? "default" : "outline",
                size: "sm",
              })}
            >
              {tab.label}
            </Link>
          ))}
          <Button
            variant="outline"
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

      {children({ doiSuffix, presignToken })}
    </div>
  );
}
