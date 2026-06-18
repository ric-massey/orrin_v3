import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, createHashRouter, Navigate, RouterProvider } from "react-router-dom";
import App from "./App";
import Watch from "./pages/Watch";
import Face from "./pages/Face";
import Brain from "./pages/Brain";
import Cognition from "./pages/Cognition";
import Life from "./pages/Life";
import Memory from "./pages/Memory";
import Timeline from "./pages/Timeline";
import Learning from "./pages/Learning";
import Settings from "./pages/Settings";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./index.css";

const routes = [
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/face" replace /> },
      { path: "watch", element: <Watch /> },
      { path: "face", element: <Face /> },
      { path: "cognition", element: <Cognition /> },
      { path: "life", element: <Life /> },
      { path: "memory", element: <Memory /> },
      { path: "timeline", element: <Timeline /> },
      { path: "learning", element: <Learning /> },
      { path: "brain", element: <Brain /> },
      { path: "settings", element: <Settings /> },
      { path: "*", element: <Navigate to="/face" replace /> },
    ],
  },
];

// The native window loads from file://, where the History API doesn't work — use
// a hash router there. Browser/dev keep clean paths with the history router.
const router =
  window.location.protocol === "file:" ? createHashRouter(routes) : createBrowserRouter(routes);

// H5: a last-resort boundary around the whole app, so an error escaping a page
// (outside the per-panel boundaries) shows a reload affordance, not a blank doc.
const RootFallback = (
  <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background p-6 text-center text-foreground">
    <div className="text-base font-semibold">Something went wrong.</div>
    <div className="max-w-sm text-sm text-muted-foreground">
      The interface hit an unexpected error. Reloading usually fixes it.
    </div>
    <button
      onClick={() => window.location.reload()}
      className="rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-muted"
    >
      Reload
    </button>
  </div>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary fallback={RootFallback}>
      <RouterProvider router={router} />
    </ErrorBoundary>
  </React.StrictMode>
);
