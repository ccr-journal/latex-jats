import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getSiteConfig, updateSiteConfig } from "@/api/client";
import type { SiteConfig, SiteConfigUpdate } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type FieldDef = {
  key: keyof SiteConfigUpdate;
  label: string;
  placeholder?: string;
  description?: string;
  multiline?: boolean;
  // When true, the field spans the full row in a 2-column section.
  fullWidth?: boolean;
};

const SECTIONS: { title: string; fields: FieldDef[] }[] = [
  {
    title: "Journal",
    fields: [
      { key: "journal_id", label: "Journal ID (publisher-id)" },
      { key: "journal_title", label: "Journal title" },
      { key: "issn_epub", label: "ISSN (electronic)" },
      { key: "issn_ppub", label: "ISSN (print)" },
    ],
  },
  {
    title: "Publisher",
    fields: [
      { key: "publisher_name", label: "Publisher name" },
      { key: "publisher_loc", label: "Publisher location" },
    ],
  },
  {
    title: "License",
    fields: [
      { key: "copyright_holder", label: "Copyright holder" },
      { key: "copyright_statement", label: "Copyright statement" },
      { key: "license_type", label: "License type" },
      { key: "license_url", label: "License URL" },
      { key: "license_text", label: "License text" },
    ],
  },
  {
    title: "DOI",
    fields: [
      {
        key: "doi_prefix",
        label: "DOI prefix",
        description:
          "Used only to derive document IDs from OJS-returned DOIs (e.g. \"10.5117/\" stripped from \"10.5117/CCR2025.1.2.YAO\" → \"CCR2025.1.2.YAO\"). Not written to JATS output.",
      },
    ],
  },
  {
    title: "Branding",
    fields: [
      {
        key: "site_name",
        label: "Site name",
        description: "Shown as the heading on the public landing page.",
      },
      {
        key: "header_branding",
        label: "Header branding",
        description:
          "The journal-specific text in the top-left of every page (the \"JATSmith vX.Y.Z\" suffix is appended automatically).",
      },
      {
        key: "site_description",
        label: "Site description",
        description:
          "Lead paragraph on the public landing page. Markdown supported (e.g. *italic*, [link text](https://example.com)).",
        multiline: true,
        fullWidth: true,
      },
    ],
  },
];

export function SiteConfigPage() {
  const navigate = useNavigate();
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    getSiteConfig()
      .then(setConfig)
      .catch((err) => setLoadError(err instanceof Error ? err.message : String(err)));
  }, []);

  if (loadError) {
    return <p className="text-sm text-destructive">{loadError}</p>;
  }
  if (config === null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const update = (key: keyof SiteConfig, value: string) => {
    setConfig({ ...config, [key]: value });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      const payload: SiteConfigUpdate = {};
      for (const section of SECTIONS) {
        for (const f of section.fields) {
          payload[f.key] = config[f.key as keyof SiteConfig] as string;
        }
      }
      const saved = await updateSiteConfig(payload);
      setConfig(saved);
      navigate("/dashboard");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const isFirstRun = config.configured_at === null;

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Site config</h1>
        <p className="text-sm text-muted-foreground">
          {isFirstRun
            ? "Confirm your journal settings to get started. These values are baked into the JATS XML for every conversion."
            : "Edit journal-identity values used in JATS output and OJS calls."}
        </p>
      </header>

      {SECTIONS.map((section) => (
        <Card key={section.title}>
          <CardHeader>
            <CardTitle>{section.title}</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {section.fields.map((f) => (
              <div
                key={f.key as string}
                className={`flex flex-col gap-1.5 ${
                  f.fullWidth ? "md:col-span-2" : ""
                }`}
              >
                <Label htmlFor={f.key as string}>{f.label}</Label>
                {f.multiline ? (
                  <Textarea
                    id={f.key as string}
                    rows={4}
                    value={(config[f.key as keyof SiteConfig] as string) ?? ""}
                    placeholder={f.placeholder}
                    onChange={(e) =>
                      update(f.key as keyof SiteConfig, e.target.value)
                    }
                  />
                ) : (
                  <Input
                    id={f.key as string}
                    value={(config[f.key as keyof SiteConfig] as string) ?? ""}
                    placeholder={f.placeholder}
                    onChange={(e) =>
                      update(f.key as keyof SiteConfig, e.target.value)
                    }
                  />
                )}
                {f.description && (
                  <p className="text-xs text-muted-foreground">{f.description}</p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}

      {saveError && <p className="text-sm text-destructive">{saveError}</p>}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : isFirstRun ? "Confirm settings" : "Save changes"}
        </Button>
        {!isFirstRun && (
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/dashboard")}
          >
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
