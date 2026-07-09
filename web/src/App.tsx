import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Theme, Header, HeaderName, SkipToContent } from '@carbon/react';
import ProjectsPage from './pages/ProjectsPage';
import NewProjectPage from './pages/NewProjectPage';
import UploadPage from './pages/UploadPage';
import NormalizePage from './pages/NormalizePage';
import ReviewPage from './pages/ReviewPage';
import ExportPage from './pages/ExportPage';

export default function App() {
  return (
    <Theme theme="g10">
      <BrowserRouter>
        <Header aria-label="RVTool Genesis">
          <SkipToContent />
          <HeaderName href="/" prefix="IBM">RVTool Genesis</HeaderName>
        </Header>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/projects/new" element={<NewProjectPage />} />
            <Route path="/projects/:id/upload" element={<UploadPage />} />
            <Route path="/projects/:id/normalize" element={<NormalizePage />} />
            <Route path="/projects/:id/review" element={<ReviewPage />} />
            <Route path="/projects/:id/export" element={<ExportPage />} />
          </Routes>
        </main>
      </BrowserRouter>
    </Theme>
  );
}
