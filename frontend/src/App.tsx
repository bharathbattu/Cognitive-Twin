import { Route, Routes } from "react-router-dom";

import AppProviders from "@/app/providers/AppProviders";
import DashboardPage from "@/pages/DashboardPage";

function App() {
  return (
    <AppProviders>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
      </Routes>
    </AppProviders>
  );
}

export default App;
