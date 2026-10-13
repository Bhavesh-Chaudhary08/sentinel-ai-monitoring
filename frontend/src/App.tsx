import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import MyActivity from "./pages/employee/MyActivity";
import Interactions from "./pages/admin/Interactions";
import Alerts from "./pages/admin/Alerts";
import Analytics from "./pages/admin/Analytics";
import Policies from "./pages/admin/Policies";
import ShadowAI from "./pages/admin/ShadowAI";
import Users from "./pages/admin/Users";
import Audit from "./pages/admin/Audit";

function Spinner() {
  return (
    <div className="center-screen">
      <div className="spinner" />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== "admin") return <Navigate to="/me" replace />;
  return <>{children}</>;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={user?.role === "admin" ? "/analytics" : "/me"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/" element={<Home />} />
            <Route path="/me" element={<MyActivity />} />
            <Route
              path="/analytics"
              element={<RequireAdmin><Analytics /></RequireAdmin>}
            />
            <Route
              path="/interactions"
              element={<RequireAdmin><Interactions /></RequireAdmin>}
            />
            <Route path="/alerts" element={<RequireAdmin><Alerts /></RequireAdmin>} />
            <Route path="/shadow" element={<RequireAdmin><ShadowAI /></RequireAdmin>} />
            <Route path="/policies" element={<RequireAdmin><Policies /></RequireAdmin>} />
            <Route path="/users" element={<RequireAdmin><Users /></RequireAdmin>} />
            <Route path="/audit" element={<RequireAdmin><Audit /></RequireAdmin>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
