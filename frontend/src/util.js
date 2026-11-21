import { useCallback, useEffect, useRef, useState } from 'react'

const dateFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const timeFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export const fmtDate = (v) => (v ? dateFmt.format(new Date(String(v).slice(0, 10) + 'T00:00:00')) : 'not recorded')
export const fmtDateTime = (v) => (v ? timeFmt.format(new Date(v)) : '')
export const num = (v) => (v === null || v === undefined ? '0' : Number(v).toLocaleString('en-GB', { maximumFractionDigits: 2 }))

// Deadline status -> label and colour tone. Colours are only ever used for status.
export const STATUS = {
  OVERDUE: { label: 'Past deadline', tone: 'danger' },
  EXPIRES_TODAY: { label: 'Due today', tone: 'danger' },
  EXPIRES_SOON: { label: 'Due soon', tone: 'caution' },
  OK: { label: 'In date', tone: 'ok' },
  CHECK_SOURCE: { label: 'Check source', tone: '' },
}

export const KIND = {
  CATEGORY: 'MEL category',
  STATED_DAYS: 'Days stated in the record',
  DAYS_OR_FLIGHT: 'Days or flight limit',
  FLIGHT_ONLY: 'Flight cycles or hours',
  REPEAT_INTERVAL: 'Repeat inspection',
  NEXT_CHECK: 'Next maintenance check',
  CATEGORY_A: 'Category A',
  UNKNOWN: 'No limit written',
}

export const CALIBRATION = {
  UNVERIFIED: 'Unverified',
  NO_EXPIRY: 'No expiry recorded',
  EXPIRED: 'Expired',
  EXPIRES_SOON: 'Expires soon',
  IN_DATE: 'In date',
}

// Small data-loading hook: { data, error, loading, reload }.
export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const seq = useRef(0)
  const run = useCallback(() => {
    const id = ++seq.current
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then(
      (data) => id === seq.current && setState({ data, error: null, loading: false }),
      (error) => id === seq.current && setState({ data: null, error, loading: false }),
    )
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(run, [run])
  return { ...state, reload: run }
}

// Tiny hash router: "#/brief", "#/aircraft/A6-ATA".
export function useHash() {
  const read = () => window.location.hash.replace(/^#\/?/, '') || 'brief'
  const [hash, setHash] = useState(read)
  useEffect(() => {
    const on = () => setHash(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash
}

// One short line about a deadline, used in lists: no repeated words.
export function deadlineLine(d) {
  if (!d.expires_on) return 'No deadline date could be worked out.'
  if (d.status === 'OVERDUE') return `${d.status_text} (${fmtDate(d.expires_on)}).`
  return `Deadline ${fmtDate(d.expires_on)}, ${d.status_text.toLowerCase()}.`
}
