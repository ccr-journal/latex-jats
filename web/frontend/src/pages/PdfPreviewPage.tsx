import { PreviewShell } from "@/components/PreviewShell";
import { outputUrl } from "@/api/client";

export function PdfPreviewPage() {
  return (
    <PreviewShell activeTab="pdf">
      {({ doiSuffix, presignToken }) => {
        const pdfUrl = outputUrl(doiSuffix, `${doiSuffix}.pdf`, presignToken);
        return (
          <iframe
            src={pdfUrl}
            title="PDF Preview"
            className="w-full rounded-md border"
            style={{ height: "80vh" }}
          />
        );
      }}
    </PreviewShell>
  );
}
