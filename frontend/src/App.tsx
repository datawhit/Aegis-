import { Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { AppShell } from "@/components/layout/AppShell";
import LoginPage from "@/pages/LoginPage";
import IncidentsListPage from "@/pages/IncidentsListPage";
import IncidentDetailPage from "@/pages/IncidentDetailPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/incidents" element={<IncidentsListPage />} />
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
        <Route index element={<Navigate to="/incidents" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/incidents" replace />} />
    </Routes>
  );
}
