import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  setSessionToken,
  getCurrentUser,
} from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function TokenLandingPage() {
  const { doiSuffix } = useParams<{ doiSuffix: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = searchParams.get("token");
    const target = `/manuscripts/${doiSuffix}`;

    // If already logged in as editor, just navigate to the manuscript
    if (user?.role === "editor") {
      navigate(target, { replace: true });
      return;
    }

    if (!token) {
      setError("No access token in URL.");
      return;
    }

    // Store the manuscript token and validate it
    setSessionToken(token);
    getCurrentUser()
      .then(() => refresh())
      .then(() => navigate(target, { replace: true }))
      .catch(() => {
        setError("This link is invalid or has been revoked.");
      });
  }, [doiSuffix, searchParams, navigate, refresh, user]);

  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-sm">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div className="p-6 text-sm text-muted-foreground">
      Opening manuscript...
    </div>
  );
}
