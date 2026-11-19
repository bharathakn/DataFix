import { Outlet, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import Diagnosis from './pages/Diagnosis'
import Export from './pages/Export'
import History from './pages/History'
import Overview from './pages/Overview'
import Privacy from './pages/Privacy'
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
        <Route path="privacy" element={<Privacy />} />
        <Route path="export" element={<Export />} />
      </Route>
      <Route path="*" element={<Upload />} />
    </Routes>
  )
}
