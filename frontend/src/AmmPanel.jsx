import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorBox, Loading } from './ui'
import { num } from './util'

const byKind = (items, kind) => items.filter((i) => i.kind === kind)
const isQty = (q) => (q === 'AR' ? 'As required' : q)

function Section({ title, hint, children }) {
  return (
    <section className="amm-section">
      <h4>{title}</h4>
      {hint && <p className="muted small">{hint}</p>}
      {children}
    </section>
  )
}

function ToolRow({ tool }) {
  const stock = tool.stock
  return (
    <li className="amm-row">
      <div className="amm-main">
        <span className="amm-name">{tool.designation}</span>
        {tool.ref ? <span className="amm-pn">{tool.ref}</span> : <span className="muted small">Standard tool, no part number</span>}
      </div>
      <div className="amm-side">
        {tool.qty && <span className="muted small">{isQty(tool.qty)}{tool.qty !== 'AR' ? ' needed' : ''}</span>}
        {tool.ref && stock && (
          stock.rows > 0
            ? <a className="chip ok" href={`#/tools/${encodeURIComponent(tool.ref)}`}>In tool list: {num(stock.qty)}</a>
            : <span className="chip caution">Not in tool list</span>
        )}
      </div>
    </li>
  )
}

function TaskVariant({ task, variant }) {
  const parts = byKind(variant.items, 'part')
  const consumables = byKind(variant.items, 'consumable')
  const tools = byKind(variant.items, 'tool')
  const refs = byKind(variant.items, 'reference')
  const isFitting = ['000', '400'].includes(variant.function_code)
  const verb = variant.function_code === '000' ? 'Removed' : 'Fitted'

  return (
    <>
      {isFitting && (
        <Section title={`${verb} in this task`}>
          <ul className="amm-list">
            <li className="amm-row">
              <div className="amm-main">
                <span className="amm-name">{variant.title.replace(/^(Removal|Installation) of (the )?/i, '')}</span>
                {variant.fins?.length > 0 && <span className="amm-pn">FIN {variant.fins.join(', ')}</span>}
              </div>
              <div className="amm-side"><span className="muted small">Main component</span></div>
            </li>
          </ul>
        </Section>
      )}

      {parts.length > 0 && (
        <Section title="Parts to replace every time" hint="Single-use parts the manual lists for this task. Do not refit the old ones.">
          <ul className="amm-list">
            {parts.map((p, i) => (
              <li className="amm-row" key={i}>
                <div className="amm-main">
                  <span className="amm-name">{p.designation}</span>
                  <span className="muted small">Figure item {p.ref}{p.extra ? `, IPC ${p.extra}` : ''}</span>
                </div>
                <div className="amm-side">
                  <a className="btn small" href={`#/parts/${encodeURIComponent(p.designation)}`}>Find in stock</a>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {consumables.length > 0 && (
        <Section title="Materials used up" hint="Grease, sealant, wire and similar. The code is the Airbus material number.">
          <ul className="amm-list">
            {consumables.map((c, i) => (
              <li className="amm-row" key={i}>
                <div className="amm-main"><span className="amm-name">{c.designation}</span><span className="amm-pn">{c.ref}</span></div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {tools.length > 0 && (
        <Section title="Tools and equipment">
          <ul className="amm-list">{tools.map((t, i) => <ToolRow tool={t} key={i} />)}</ul>
        </Section>
      )}

      {parts.length === 0 && consumables.length === 0 && tools.length === 0 && (
        <p className="muted">This task lists no parts, materials or tools.</p>
      )}

      {variant.notes.length > 0 && (
        <Section title="Warnings and cautions from the manual">
          <ul className="amm-list">
            {variant.notes.map((n) => (
              <li key={n.code} className={`amm-note ${n.kind === 'warning' ? 'danger' : 'caution'}`}>
                <b>{n.kind === 'warning' ? 'Warning' : 'Caution'}</b>
                <span>{n.text}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {variant.identical_task_note && <p className="amm-note caution"><b>Note</b><span>{variant.identical_task_note}</span></p>}

      {refs.length > 0 && (
        <details>
          <summary>{refs.length} related tasks in the manual</summary>
          <ul className="amm-list" style={{ marginTop: 6 }}>
            {refs.map((r, i) => (
              <li className="amm-row" key={i}>
                <div className="amm-main"><span className="amm-name">{r.designation}</span><span className="amm-pn">{r.ref}</span></div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  )
}

function TaskCard({ task }) {
  const [idx, setIdx] = useState(0)
  const variant = task.variants[idx]
  const meta = [variant.fins?.length ? `FIN ${variant.fins.join(', ')}` : null,
                variant.zones?.length ? `Zone ${variant.zones.join(', ')}` : null,
                variant.rev_date ? `Revised ${variant.rev_date.slice(0, 4)}-${variant.rev_date.slice(4, 6)}` : null].filter(Boolean)
  return (
    <article className="amm-task">
      <header>
        <span className="chip brand">{task.function_label}</span>
        <span className="amm-title">{task.title}</span>
        <span className="tag" title={`Source: ${task.source.file}, task ${task.base_task}`}>AMM {task.base_task}</span>
      </header>
      {meta.length > 0 && <p className="muted small">{meta.join('  |  ')}</p>}
      {task.variants.length > 1 && (
        <div className="amm-tabs" role="tablist" aria-label="Task version">
          {task.variants.map((v, i) => (
            <button key={v.task_no} role="tab" aria-selected={i === idx} className={i === idx ? 'on' : ''} onClick={() => setIdx(i)}>
              Version {v.config}
            </button>
          ))}
          <span className="muted small">The manual has more than one version of this task. Pick the one that matches the job and this tail.</span>
        </div>
      )}
      <TaskVariant task={task} variant={variant} />
    </article>
  )
}

/* The AMM tasks named in one work order, and what each one uses. Reference only. */
export default function AmmPanel({ woNumber }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let alive = true
    api.amm(woNumber).then((r) => alive && setData(r), (e) => alive && setError(e))
    return () => { alive = false }
  }, [woNumber])

  return (
    <div className="amm" style={{ marginTop: 8 }}>
      <ErrorBox error={error} />
      {!data && !error && <Loading text="Reading the maintenance manual data" />}
      {data && data.tasks.length === 0 && data.not_in_amm.length === 0 && (
        <p className="muted">This work order does not name an AMM task number, so there is nothing to look up.</p>
      )}
      {data && data.tasks.map((t) => <TaskCard key={t.base_task} task={t} />)}
      {data && data.not_in_amm.length > 0 && (
        <p className="muted small">Not found in the loaded manual: {data.not_in_amm.join(', ')}. Check the task number in the current AMM.</p>
      )}
    </div>
  )
}
