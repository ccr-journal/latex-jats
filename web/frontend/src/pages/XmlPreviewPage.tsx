import { useEffect, useState } from "react";
import { XmlViewer } from "@/components/XmlViewer";
import { PreviewShell } from "@/components/PreviewShell";
import { outputUrl } from "@/api/client";

export function XmlPreviewPage() {
  return (
    <PreviewShell activeTab="xml">
      {({ doiSuffix, presignToken }) => (
        <XmlContent doiSuffix={doiSuffix} presignToken={presignToken} />
      )}
    </PreviewShell>
  );
}

function XmlContent({ doiSuffix, presignToken }: { doiSuffix: string; presignToken: string }) {
  const [xmlText, setXmlText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = outputUrl(doiSuffix, `${doiSuffix}.xml`, presignToken);
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to fetch XML: ${res.statusText}`);
        return res.text();
      })
      .then(setXmlText)
      .catch((err) => setError(err.message));
  }, [doiSuffix, presignToken]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!xmlText) return <p className="text-muted-foreground">Loading XML...</p>;

  return <XmlViewer xml={xmlText} />;
}
