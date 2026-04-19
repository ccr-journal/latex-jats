import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { listOjsSubmissions, type OjsStage } from "@/api/client";
import type { OjsSubmission } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";

interface StageState {
  submissions: OjsSubmission[] | null;
  loading: boolean;
  error: string | null;
}

const EMPTY_STATE: StageState = {
  submissions: null,
  loading: false,
  error: null,
};

interface OjsContextValue {
  copyediting: StageState;
  production: StageState;
  refresh: (stage: OjsStage) => Promise<void>;
  refreshAll: () => Promise<void>;
}

const OjsCtx = createContext<OjsContextValue | undefined>(undefined);

export function OjsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [copyediting, setCopyediting] = useState<StageState>(EMPTY_STATE);
  const [production, setProduction] = useState<StageState>(EMPTY_STATE);
  const preloadedRef = useRef(false);

  const refresh = useCallback(async (stage: OjsStage) => {
    const setter = stage === "copyediting" ? setCopyediting : setProduction;
    setter((s) => ({ ...s, loading: true, error: null }));
    try {
      const submissions = await listOjsSubmissions(stage);
      setter({ submissions, loading: false, error: null });
    } catch (err) {
      setter((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : "Failed to load",
      }));
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refresh("copyediting"), refresh("production")]);
  }, [refresh]);

  useEffect(() => {
    if (user?.role !== "editor") {
      preloadedRef.current = false;
      setCopyediting(EMPTY_STATE);
      setProduction(EMPTY_STATE);
      return;
    }
    if (preloadedRef.current) return;
    preloadedRef.current = true;
    void refreshAll();
  }, [user, refreshAll]);

  return (
    <OjsCtx.Provider value={{ copyediting, production, refresh, refreshAll }}>
      {children}
    </OjsCtx.Provider>
  );
}

export function useOjs(): OjsContextValue {
  const ctx = useContext(OjsCtx);
  if (!ctx) throw new Error("useOjs must be used inside <OjsProvider>");
  return ctx;
}

export function useOjsSubmissions(stage: OjsStage): StageState {
  const ctx = useOjs();
  return stage === "copyediting" ? ctx.copyediting : ctx.production;
}
