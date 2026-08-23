// Router setup. (Phase 5)

import { Route, Routes } from 'react-router-dom';
import { ProtectedRoute, PublicOnlyRoute } from './auth/ProtectedRoute';
import { Layout } from './components/Layout';
import { Appointments } from './pages/Appointments';
import { BookAppointment } from './pages/BookAppointment';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { NotFound } from './pages/NotFound';
import { Pets } from './pages/Pets';
import { Profile } from './pages/Profile';
import { Register } from './pages/Register';
import { VetSchedule } from './pages/VetSchedule';
import { Role } from './types/api';

function App() {
  return (
    <Routes>
      {/* Signed out only — a logged-in user landing here goes to the dashboard. */}
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>

      {/* Everything else needs a session. Role gates are declared per route so
          a page cannot be reached by typing its URL. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/pets" element={<Pets />} />
          <Route path="/book" element={<BookAppointment />} />
          <Route path="/appointments" element={<Appointments />} />
          <Route path="/profile" element={<Profile />} />

          <Route element={<ProtectedRoute roles={[Role.VET, Role.ADMIN]} />}>
            <Route path="/schedule" element={<VetSchedule />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default App;
