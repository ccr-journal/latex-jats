import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAuth } from "@/auth/AuthContext";
import { getVersion } from "@/api/client";

const GITHUB_URL = "https://github.com/ccr-journal/jatsmith";

export function LandingPage() {
  const { user, loading } = useAuth();
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    getVersion().then((v) => setVersion(v.version)).catch(() => {});
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
            <span className="text-lg text-orange-600">CCR</span>
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
            CCR JATSmith
          </h1>
          <p className="text-lg text-muted-foreground">
            Convert{" "}
            <em>Computational Communication Research</em> journal articles from
            LaTeX to JATS XML for submission to Amsterdam University Press.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link to="/login" className={buttonVariants()}>
              Editor sign in
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener"
              className={buttonVariants({ variant: "outline" })}
            >
              View on GitHub
            </a>
          </div>
        </section>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">About this tool</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              CCR JATSmith runs LaTeXML with custom bindings for the CCR
              document class, plus a Python post-processing pipeline that
              produces publisher-ready JATS XML and an HTML proof preview.
            </p>
            <p>
              Editors and authors of the CCR journal use this web service to
              upload LaTeX source, run the conversion, and preview or download
              the resulting XML, PDF, and HTML proofs.
            </p>
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground">
          Authors access manuscripts through the direct link provided by the
          production editor.
        </p>
      </main>
    </div>
  );
}
