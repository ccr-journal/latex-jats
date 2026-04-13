import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { DashboardPage } from "@/pages/DashboardPage";
import { ManuscriptPage } from "@/pages/ManuscriptPage";
import { PreviewPage } from "@/pages/PreviewPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/manuscripts/:doiSuffix" element={<ManuscriptPage />} />
          <Route path="/manuscripts/:doiSuffix/preview" element={<PreviewPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
