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
import { lazy, StrictMode, Suspense, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Copilot } from "./components/Copilot";
import { Layout } from "./components/Layout";
import { Login } from "./components/Login";
import "./index.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import { Loading } from "./components/ui";

// each board is its own chunk, so the first screen does not wait for every chart
const Overview = lazy(() => import("./pages/Overview"));
const PlannerPage = lazy(() => import("./pages/Planner"));
const FlowPage = lazy(() => import("./pages/FleetFlow"));
const AircraftPage = lazy(() => import("./pages/Aircraft"));
const SustainmentPage = lazy(() => import("./pages/Sustainment"));
const LossPage = lazy(() => import("./pages/Loss"));
const SnagsPage = lazy(() => import("./pages/Snags"));
const ProofPage = lazy(() => import("./pages/Proof"));

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </ThemeProvider>
  );
}

/** Nothing but the sign-in screen until the server has accepted a session. */
function Gate() {
  const { user, ready } = useAuth();
  const [copilot, setCopilot] = useState(false);
  if (!ready) return null;
  if (!user) return <Login />;
  return (
    <>
      <BrowserRouter>
        <Layout onCopilot={() => setCopilot(true)}>
          <Suspense fallback={<Loading label="LOADING BOARD" />}>
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
          </Suspense>
        </Layout>
        <Copilot open={copilot} onClose={() => setCopilot(false)} />
      </BrowserRouter>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
