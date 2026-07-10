import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Theme, Header, HeaderName, HeaderNavigation, HeaderMenuItem, SkipToContent } from '@carbon/react';
import ProjectsPage from './pages/ProjectsPage';
import NewProjectPage from './pages/NewProjectPage';
import UploadPage from './pages/UploadPage';
import NormalizePage from './pages/NormalizePage';
import ReviewPage from './pages/ReviewPage';
import ExportPage from './pages/ExportPage';
import SettingsPage from './pages/SettingsPage';

function AppNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <HeaderNavigation aria-label="RVTool Genesis">
      <HeaderMenuItem
        isCurrentPage={pathname === '/' || pathname.startsWith('/projects')}
        onClick={() => navigate('/')}
      >
        Projects
      </HeaderMenuItem>
      <HeaderMenuItem
        isCurrentPage={pathname === '/settings'}
        onClick={() => navigate('/settings')}
      >
        Settings
      </HeaderMenuItem>
    </HeaderNavigation>
  );
}

export default function App() {
  return (
    <Theme theme="g10">
      <BrowserRouter>
        <Header aria-label="RVTool Genesis">
          <SkipToContent />
          <HeaderName href="/" prefix="IBM">RVTool Genesis</HeaderName>
          <AppNav />
        </Header>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/projects/new" element={<NewProjectPage />} />
            <Route path="/projects/:id/upload" element={<UploadPage />} />
            <Route path="/projects/:id/normalize" element={<NormalizePage />} />
            <Route path="/projects/:id/review" element={<ReviewPage />} />
            <Route path="/projects/:id/export" element={<ExportPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </BrowserRouter>
    </Theme>
  );
}
