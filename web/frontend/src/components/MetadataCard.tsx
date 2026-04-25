import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getMetadataComparison, syncOjsField } from "@/api/client";
import type { MetadataComparison } from "@/api/types";
import { InfoButton } from "@/components/InfoButton";

export function MetadataDiscrepanciesInfo() {
  return (
    <InfoButton title="Metadata Discrepancies">
      <p>
        Each manuscript has metadata in two places: the LaTeX source you
        uploaded (<code>{"\\title"}</code>, <code>{"\\subtitle"}</code>,
        <code>{"\\abstract"}</code>, <code>{"\\keywords"}</code>, authors, DOI,
        volume, issue, year, first page) and the journal management system
        (OJS), where the editor accepted your submission. The published article
        needs both to agree &mdash; the PDF and JATS XML are built from your
        source, while OJS provides the canonical metadata for the journal
        website and citation indices. This card lists fields where the two
        disagree.
      </p>
      <p>What to do per field:</p>
      <ul className="list-disc pl-5 space-y-1">
        <li>
          <strong>Title, subtitle, abstract, keywords</strong> &mdash; if your
          source is the version you want, click <em>Push to OJS</em> to copy it
          over. Otherwise, edit your source to match OJS and re-upload.
        </li>
        <li>
          <strong>DOI, volume, issue, year, first page</strong> &mdash; the
          editor controls these in OJS. Either remove them from your source
          (the OJS values are then injected automatically) or update your
          source to match what OJS shows.
        </li>
        <li>
          <strong>Authors</strong> &mdash; ask the editor to update the author
          list in OJS, or adjust your source if your list is wrong.
        </li>
      </ul>
      <p>
        If you make changes, re-run the conversion to refresh this comparison.
      </p>
    </InfoButton>
  );
}

const UPDATABLE_FIELDS = new Set(["title", "subtitle", "abstract", "keywords"]);

// Fields whose canonical value lives in OJS — the author should fix the
// value in the source file (or remove it so OJS metadata is injected).
const SOURCE_FIX_FIELDS = new Set(["doi", "volume", "issue", "year", "firstpage"]);

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  subtitle: "Subtitle",
  abstract: "Abstract",
  keywords: "Keywords",
  authors: "Authors",
  doi: "DOI",
  volume: "Volume",
  issue: "Issue",
  year: "Year",
  firstpage: "First page",
};

function formatValue(value: string | string[]): string {
  if (Array.isArray(value)) return value.join(", ");
  return value;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\u2026";
}

interface MetadataCardProps {
  doiSuffix: string;
  readOnly?: boolean;
  refreshKey?: number;
  onSync?: () => void;
}

export function MetadataCard({ doiSuffix, readOnly, refreshKey, onSync }: MetadataCardProps) {
  const [comparisons, setComparisons] = useState<MetadataComparison[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncingField, setSyncingField] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getMetadataComparison(doiSuffix)
      .then(setComparisons)
      .catch(() => setComparisons(null))
      .finally(() => setLoading(false));
  }, [doiSuffix, refreshKey]);

  if (loading || comparisons === null) return null;

  const mismatches = comparisons.filter((c) => c.status === "mismatch");

  const handleSync = async (field: string) => {
    setSyncingField(field);
    setError(null);
    try {
      const updated = await syncOjsField(doiSuffix, field);
      setComparisons(updated);
      onSync?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update OJS");
    } finally {
      setSyncingField(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          Metadata Discrepancies
          <MetadataDiscrepanciesInfo />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {mismatches.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            All metadata matches between source and OJS.
          </p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead>Source (LaTeX)</TableHead>
                  <TableHead>OJS</TableHead>
                  {!readOnly && <TableHead className="w-30">Action</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {mismatches.map((c) => (
                  <TableRow key={c.field}>
                    <TableCell className="font-medium">
                      {FIELD_LABELS[c.field] ?? c.field}
                    </TableCell>
                    <TableCell
                      className="max-w-[300px] whitespace-normal break-words text-sm"
                      title={formatValue(c.latex)}
                    >
                      {truncate(formatValue(c.latex), 120)}
                    </TableCell>
                    <TableCell
                      className="max-w-[300px] whitespace-normal break-words text-sm"
                      title={formatValue(c.ojs)}
                    >
                      {truncate(formatValue(c.ojs), 120)}
                    </TableCell>
                    {!readOnly && (
                      <TableCell>
                        {UPDATABLE_FIELDS.has(c.field) ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={syncingField !== null}
                            onClick={() => handleSync(c.field)}
                          >
                            {syncingField === c.field ? "Updating\u2026" : "Push to OJS"}
                          </Button>
                        ) : SOURCE_FIX_FIELDS.has(c.field) ? (
                          <span className="text-xs text-muted-foreground">
                            Fix in source or remove
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">Fix in OJS</span>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {error && (
              <p className="mt-2 text-sm text-red-600">{error}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
