import { Outlet, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import ComingSoon from './pages/ComingSoon'
import Diagnosis from './pages/Diagnosis'
import History from './pages/History'
import Overview from './pages/Overview'
import RepairStudio from './pages/RepairStudio'
import Setup from './pages/Setup'
import Upload from './pages/Upload'
import Validation from './pages/Validation'

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
        <Route path="repair" element={<RepairStudio />} />
        <Route path="history" element={<History />} />
        <Route path="diagnosis" element={<Diagnosis />} />
        <Route path="validation" element={<Validation />} />
        <Route path="privacy" element={<ComingSoon name="Privacy" phase="6B" />} />
        <Route path="export" element={<ComingSoon name="Export" phase="6B" />} />
      </Route>
      <Route path="*" element={<Upload />} />
    </Routes>
  )
}
