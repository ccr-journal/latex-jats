import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { orcidLoginUrl } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function LoginPage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const error = params.get("error");

  useEffect(() => {
    if (!loading && user) navigate("/", { replace: true });
  }, [loading, user, navigate]);

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>CCR JATSmith</CardTitle>
          <CardDescription>
            Editor sign-in via ORCID. Authors access manuscripts through
            direct links provided by the production editor.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error === "not_authorized" && (
            <p className="text-sm text-red-600">
              Your ORCID isn't registered as a CCR editor. Ensure your ORCID is
              set on your CCR editor profile in OJS, or contact the editorial
              team.
            </p>
          )}
          <Button
            className="w-full"
            onClick={() => {
              window.location.href = orcidLoginUrl();
            }}
          >
            Sign in with ORCID
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
