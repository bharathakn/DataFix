import { Outlet, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import ComingSoon from './pages/ComingSoon'
import Overview from './pages/Overview'
import Setup from './pages/Setup'
import Upload from './pages/Upload'

function Shell() {
  return <AppShell><Outlet /></AppShell>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Upload />} />
      <Route path="/s/:sid" element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="setup" element={<Setup />} />
        <Route path="repair" element={<ComingSoon name="Repair Studio" phase="5B" />} />
        <Route path="history" element={<ComingSoon name="History" phase="5B" />} />
        <Route path="diagnosis" element={<ComingSoon name="Diagnosis" phase="6A" />} />
        <Route path="validation" element={<ComingSoon name="Validation" phase="6A" />} />
        <Route path="privacy" element={<ComingSoon name="Privacy" phase="6B" />} />
        <Route path="export" element={<ComingSoon name="Export" phase="6B" />} />
      </Route>
      <Route path="*" element={<Upload />} />
    </Routes>
  )
}
