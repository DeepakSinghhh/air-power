import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Copilot } from "./components/Copilot";
import { Layout } from "./components/Layout";
import "./index.css";
import { ThemeProvider } from "./lib/theme";
import AircraftPage from "./pages/Aircraft";
import DataPage from "./pages/DataFabric";
import FlowPage from "./pages/FleetFlow";
import LossPage from "./pages/Loss";
import ModelsPage from "./pages/Models";
import Overview from "./pages/Overview";
import PlannerPage from "./pages/Planner";
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
            <Route path="/data" element={<DataPage />} />
            <Route path="/models" element={<ModelsPage />} />
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
