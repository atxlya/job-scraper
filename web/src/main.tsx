import "@fontsource-variable/inter";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes, useNavigate } from "react-router";
import { ApiError, setNavigate } from "./api";
import { useTheme } from "./theme";
import { Applications } from "./pages/Applications";
import { Dashboard } from "./pages/Dashboard";
import { JobPage } from "./pages/JobPage";
import { Login } from "./pages/Login";
import { Sources } from "./pages/Sources";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Don't retry answers the server meant (4xx); retry network blips twice.
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
});

function RouterBridge() {
  const navigate = useNavigate();
  useEffect(() => setNavigate((to) => navigate(to)), [navigate]);
  useTheme(); // keeps every page in step with the system theme (or the saved choice)
  return null;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <RouterBridge />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/jobs/:id" element={<JobPage />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
