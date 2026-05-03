import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Link, Navigate } from "react-router-dom";

import { getSiteConfig, getVersion } from "@/api/client";
import type { SiteConfig } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ThemeToggle } from "@/components/ThemeToggle";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const GITHUB_URL = "https://github.com/ccr-journal/jatsmith";

export function LandingPage() {
  const { user, loading } = useAuth();
  const [version, setVersion] = useState<string | null>(null);
  const [site, setSite] = useState<SiteConfig | null>(null);

  useEffect(() => {
    getVersion().then((v) => setVersion(v.version)).catch(() => { });
    getSiteConfig().then(setSite).catch(() => { });
  }, []);

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }
  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
          <span className="flex items-center gap-2 font-semibold">
            <span className="text-lg text-orange-600">
              {site?.header_branding ?? ""}
            </span>
            <span className="text-sm text-muted-foreground">JATSmith</span>
          </span>
          {version && (
            <span className="text-xs text-muted-foreground">v{version}</span>
          )}
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-12 space-y-8">
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">
            {site?.site_name ?? "JATSmith"}
          </h1>
          {site && (
            <div className="prose prose-sm max-w-none text-lg text-muted-foreground [&_a]:underline [&_a]:underline-offset-2 [&_a]:text-foreground hover:[&_a]:text-primary">
              <Markdown>{site.site_description}</Markdown>
            </div>
          )}
          <div className="flex flex-wrap gap-3 pt-2">
            <Link to="/login" className={buttonVariants()}>
              Editor sign in
            </Link>
          </div>
        </section>

        <p className="text-xs text-muted-foreground">
          Authors access manuscripts through the direct link provided by the
          production editor.
        </p>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">About JATSmith</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              JATSmith is an open-source copy-editing web service for
              academic journals. It converts LaTeX and Quarto manuscripts into
              publisher-ready JATS XML with HTML and PDF previews, and gives
              editors and authors a workflow for reviewing and approving the result.
              It is optionally integrated directly with OJS.
            </p>
            <p>
              Built on LaTeXML and a Python post-processing pipeline.{" "}
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener"
                className="underline underline-offset-2 hover:text-foreground"
              >
                View on GitHub
              </a>
              .
            </p>
          </CardContent>
        </Card>

      </main>
    </div>
  );
}
