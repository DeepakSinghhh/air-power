import "@fontsource/barlow-condensed/latin-500.css";
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/barlow-condensed/latin-700.css";
import "@fontsource/courier-prime/latin-400.css";
import "@fontsource/courier-prime/latin-700.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-700.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/special-elite/latin-400.css";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Copilot } from "./components/Copilot";
import { Layout } from "./components/Layout";
import "./index.css";
import { ThemeProvider } from "./lib/theme";
import AircraftPage from "./pages/Aircraft";
import FlowPage from "./pages/FleetFlow";
import LossPage from "./pages/Loss";
import Overview from "./pages/Overview";
import PlannerPage from "./pages/Planner";
import ProofPage from "./pages/Proof";
import SnagsPage from "./pages/Snags";
import SustainmentPage from "./pages/Sustainment";

function App() {
  const [copilot, setCopilot] = useState(false);
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Layout onCopilot={() => setCopilot(true)}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/planner" element={<PlannerPage />} />
            <Route path="/flow" element={<FlowPage />} />
            <Route path="/aircraft" element={<AircraftPage />} />
            <Route path="/aircraft/:tail" element={<AircraftPage />} />
            <Route path="/sustainment" element={<SustainmentPage />} />
            <Route path="/loss" element={<LossPage />} />
            <Route path="/snags" element={<SnagsPage />} />
            <Route path="/proof" element={<ProofPage />} />
            <Route path="/data" element={<ProofPage />} />
            <Route path="/models" element={<ProofPage />} />
          </Routes>
        </Layout>
        <Copilot open={copilot} onClose={() => setCopilot(false)} />
      </BrowserRouter>
    </ThemeProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
