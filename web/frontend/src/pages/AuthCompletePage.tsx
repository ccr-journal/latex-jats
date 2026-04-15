import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setSessionToken } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function AuthCompletePage() {
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const errParam = params.get("error");
    if (errParam) {
      navigate(`/login?error=${encodeURIComponent(errParam)}`, { replace: true });
      return;
    }
    const token = params.get("token");
    if (!token) {
      setError("No token in callback — please try signing in again.");
      return;
    }
    setSessionToken(token);
    // Clear the fragment so the token doesn't linger in the URL bar
    window.history.replaceState(null, "", window.location.pathname);
    void refresh().then(() => navigate("/", { replace: true }));
  }, [navigate, refresh]);

  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-sm">
        <p className="text-red-600">{error}</p>
        <a href="/login" className="mt-4 inline-block text-primary underline">
          Back to sign in
        </a>
      </div>
    );
  }
  return <div className="p-6 text-sm text-muted-foreground">Signing you in…</div>;
}
