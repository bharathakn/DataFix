import { Construction } from 'lucide-react'
import { EmptyState } from '../components/ui'

export default function ComingSoon({ name, phase }: { name: string; phase: string }) {
  return (
    <div className="p-6">
      <EmptyState icon={<Construction className="size-8" />} title={`${name} is coming in Phase ${phase}`}>
        The backend for this page already works; the screen is built next.
      </EmptyState>
    </div>
  )
}
