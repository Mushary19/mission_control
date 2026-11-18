import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import "@fontsource-variable/inter";
import "./index.css";
import { Layout } from "@/components/Layout";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ReviewerProvider } from "@/lib/reviewer";
import Overview from "@/pages/Overview";
import ProcessPage from "@/pages/ProcessPage";
import Cases from "@/pages/Cases";
import CaseDetail from "@/pages/CaseDetail";
import Insights from "@/pages/Insights";
import Questions from "@/pages/Questions";
import FeedbackPage from "@/pages/FeedbackPage";
import HowItWorks from "@/pages/HowItWorks";
import { Empty } from "@/components/common";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <ReviewerProvider>
        <TooltipProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<Overview />} />
                <Route path="processes/:process" element={<ProcessPage />} />
                <Route path="cases" element={<Cases />} />
                <Route path="cases/:caseId" element={<CaseDetail />} />
                <Route path="insights" element={<Insights />} />
                <Route path="questions" element={<Questions />} />
                <Route path="feedback" element={<FeedbackPage />} />
                <Route path="how-it-works" element={<HowItWorks />} />
                <Route path="*" element={<Empty>Page not found. Use the menu on the left.</Empty>} />
              </Route>
            </Routes>
          </BrowserRouter>
          <Toaster position="bottom-right" toastOptions={{ className: "!rounded-lg !border !border-zinc-200 !text-sm" }} />
        </TooltipProvider>
      </ReviewerProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
