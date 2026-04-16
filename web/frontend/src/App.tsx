import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { AuthProvider } from "@/auth/AuthContext";
import { RequireAuth } from "@/auth/RequireAuth";
import { DashboardPage } from "@/pages/DashboardPage";
import { ManuscriptPage } from "@/pages/ManuscriptPage";
import { PreviewPage } from "@/pages/PreviewPage";
import { PdfPreviewPage } from "@/pages/PdfPreviewPage";
import { XmlPreviewPage } from "@/pages/XmlPreviewPage";
import { LoginPage } from "@/pages/LoginPage";
import { AuthCompletePage } from "@/pages/AuthCompletePage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/auth/complete" element={<AuthCompletePage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/manuscripts/:doiSuffix" element={<ManuscriptPage />} />
            <Route
              path="/manuscripts/:doiSuffix/preview"
              element={<PreviewPage />}
            />
            <Route
              path="/manuscripts/:doiSuffix/pdf"
              element={<PdfPreviewPage />}
            />
            <Route
              path="/manuscripts/:doiSuffix/xml"
              element={<XmlPreviewPage />}
            />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
