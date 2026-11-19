import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

// Every session query key starts with the session id, so one invalidation refreshes the whole page.
export const keys = {
  session: (sid: string) => [sid, 'session'] as const,
  warnings: (sid: string) => [sid, 'warnings'] as const,
  heatmap: (sid: string) => [sid, 'heatmap'] as const,
  diagnosis: (sid: string, narrative: boolean) => [sid, 'diagnosis', narrative] as const,
  rows: (sid: string, q: object) => [sid, 'rows', q] as const,
  validation: (sid: string) => [sid, 'validation'] as const,
  checkpoints: (sid: string) => [sid, 'checkpoints'] as const,
}

export function useSession(sid: string | undefined) {
  return useQuery({ queryKey: keys.session(sid ?? ''), queryFn: () => api.session(sid!), enabled: !!sid })
}

export function useLlmStatus() {
  return useQuery({ queryKey: ['llm'], queryFn: api.llmStatus, refetchInterval: 60_000, retry: false })
}

const scanned = (stage?: string) => !!stage && stage !== 'loaded'

export function useWarnings(sid: string, stage?: string) {
  return useQuery({ queryKey: keys.warnings(sid), queryFn: () => api.warnings(sid), enabled: scanned(stage) })
}

export function useHeatmap(sid: string, stage?: string) {
  return useQuery({ queryKey: keys.heatmap(sid), queryFn: () => api.heatmap(sid, 40), enabled: scanned(stage) })
}

export function useDiagnosis(sid: string, stage?: string, narrative = false) {
  return useQuery({
    queryKey: keys.diagnosis(sid, narrative), queryFn: () => api.diagnosis(sid, narrative),
    enabled: scanned(stage), staleTime: Infinity,
  })
}

export function useRows(sid: string, q: Record<string, string | number | undefined>, enabled = true) {
  return useQuery({ queryKey: keys.rows(sid, q), queryFn: () => api.rows(sid, q), enabled, placeholderData: (p) => p })
}

export function useValidation(sid: string, enabled: boolean) {
  return useQuery({ queryKey: keys.validation(sid), queryFn: () => api.validation(sid), enabled, staleTime: 30_000 })
}

export function useCheckpoints(sid: string, enabled: boolean) {
  return useQuery({ queryKey: keys.checkpoints(sid), queryFn: () => api.checkpoints(sid), enabled })
}

/** A mutation that refreshes everything about the session afterwards. */
export function useSessionMutation<A, R>(sid: string, fn: (a: A) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: [sid] }) })
}
