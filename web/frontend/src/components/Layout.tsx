import { useEffect, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";
import { useAuth } from "@/auth/AuthContext";
import { getVersion } from "@/api/client";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isTokenScoped = !!user?.manuscript_token_scope;
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    getVersion().then((v) => setVersion(v.version)).catch(() => {});
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold text-primary">
            <span className="text-lg text-orange-600">CCR</span>
            <span className="text-sm text-muted-foreground">JATSmith</span>
          </Link>
          {version && (
            <span className="text-xs text-muted-foreground">v{version}</span>
          )}
          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="text-sm text-muted-foreground">
                {isTokenScoped ? "Viewing as author" : user.username}
              </span>
            )}
            <ThemeToggle />
            {user && !isTokenScoped && (
              <Button variant="outline" size="sm" onClick={handleLogout}>
                Sign out
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
