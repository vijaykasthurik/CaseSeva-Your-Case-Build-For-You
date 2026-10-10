import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { getMe, getToken } from "./api";
import AppHeader from "./components/AppHeader";
import DashboardPage from "./pages/DashboardPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";
import SignupPage from "./pages/SignupPage";
import CaseCreatePage from "./pages/CommonInputPage";
import CaseDetailPage from "./pages/EngineCasePage";
import AdvocateDirectoryPage from "./pages/AdvocateDirectoryPage";
import AdvocateInboxPage from "./pages/AdvocateInboxPage";
import AdvocateReviewPage from "./pages/AdvocateWorkspacePage";
import AdminAdvocatesPage from "./pages/VerificationAdminPage";
import DocumentsPage from "./pages/CaseOutputsPage";
import AdvocateDashboardPage from "./pages/AdvocateDashboardPage";

function useCurrentUser() {
  const [user, setUser] = useState(null);
  const location = useLocation();

  useEffect(() => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    getMe()
      .then((res) => setUser(res.user))
      .catch(() => setUser(null));
  }, [location.pathname]);

  return getToken() ? user : null;
}

function ProtectedRoute() {
  const token = getToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppHeader>
      <Outlet />
    </AppHeader>
  );
}

function ClientRoute() {
  const user = useCurrentUser();
  if (user?.role === "advocate") {
    return <Navigate to="/advocate/dashboard" replace />;
  }
  return <Outlet />;
}

function AdvocateRoute() {
  const user = useCurrentUser();
  if (user?.role === "client") {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}

function PublicRoute() {
  return <Outlet />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />

      {/* Public routes (Login, Signup) */}
      <Route element={<PublicRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
      </Route>

      {/* Protected routes */}
      <Route element={<ProtectedRoute />}>
        {/* Client-only workspace */}
        <Route element={<ClientRoute />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/cases/new" element={<CaseCreatePage />} />
          <Route path="/cases/:caseId/edit" element={<CaseCreatePage />} />
          <Route path="/advocates" element={<AdvocateDirectoryPage />} />
        </Route>

        {/* Advocate-only workspace */}
        <Route element={<AdvocateRoute />}>
          <Route path="/advocate/dashboard" element={<AdvocateDashboardPage />} />
          <Route path="/advocate/cases/new" element={<CaseCreatePage />} />
          <Route path="/advocate/intake/:caseId" element={<CaseCreatePage />} />
          <Route path="/advocate/cases/:caseId" element={<AdvocateReviewPage />} />
          <Route path="/advocate/inbox" element={<AdvocateInboxPage />} />
          <Route path="/advocate/review/:caseId" element={<AdvocateReviewPage />} />
        </Route>

        {/* Shared / Case detail routes */}
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
        <Route path="/cases/:caseId/preview1" element={<CaseDetailPage />} />
        <Route path="/cases/:caseId/preview2" element={<CaseDetailPage />} />
        <Route path="/cases/:caseId/documents" element={<DocumentsPage />} />
        <Route path="/admin/advocates" element={<AdminAdvocatesPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
