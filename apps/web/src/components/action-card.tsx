import { Chip, MaskedText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { ActionStatus, AgentAction } from "@muse-shield/core"
import {
  ArrowRight, Calculator, FolderOpen, Sheet, CalendarClock, CalendarDays, CalendarPlus, Check, ChevronRight, Contact, FileText, Globe, HeartPulse,
  Inbox, Landmark, Loader2, Mail, MessagesSquare, NotebookPen, Send, ShieldAlert, ShieldX, Wrench, X,
} from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useState } from "react"

const TOOLS: Record<string, { icon: typeof Mail; wants: string; run: string; done: string }> = {
  send_email: { icon: Mail, wants: "send an email", run: "Send email", done: "Email" },
  create_calendar_event: { icon: CalendarPlus, wants: "create a calendar event", run: "Create event", done: "Event" },
  save_note: { icon: NotebookPen, wants: "save a private note", run: "Save note", done: "Note" },
  read_inbox: { icon: Inbox, wants: "read your inbox", run: "Read", done: "Inbox" },
  search_contacts: { icon: Contact, wants: "look up your contacts", run: "Search", done: "Contacts" },
  list_events: { icon: CalendarDays, wants: "read your calendar", run: "Read", done: "Calendar" },
  reschedule_event: { icon: CalendarClock, wants: "move a calendar event", run: "Move event", done: "Event" },
  list_folder: { icon: FolderOpen, wants: "open your documents folder", run: "Open", done: "Folder" },
  search_files: { icon: FileText, wants: "search your documents", run: "Search", done: "Documents" },
  query_table: { icon: Sheet, wants: "calculate over a table on your device", run: "Calculate", done: "Table" },
  read_file: { icon: FileText, wants: "read a document", run: "Read", done: "Document" },
  read_transactions: { icon: Landmark, wants: "read your bank statement", run: "Read", done: "Statement" },
  read_health_records: { icon: HeartPulse, wants: "read your medical reports", run: "Read", done: "Health records" },
  read_channel: { icon: MessagesSquare, wants: "read a team chat channel", run: "Read", done: "Channel" },
  post_message: { icon: Send, wants: "post in a team chat channel", run: "Post message", done: "Message" },
  compute: { icon: Calculator, wants: "calculate on your device", run: "Calculate", done: "Calculator" },
  web_search: { icon: Globe, wants: "search the web", run: "Search", done: "Search" },
}
export const toolMeta = (tool: string) => TOOLS[tool] ?? { icon: Wrench, wants: `use ${tool}`, run: "Run", done: tool }

/** What a running tool is doing, for the live status line while Muse Spark works. */
const DOING: Record<string, string> = {
  read_inbox: "Accessing your mail", search_contacts: "Looking up your contacts", list_events: "Checking your calendar",
  list_folder: "Opening your documents folder", search_files: "Searching your documents", read_file: "Reading the document",
  query_table: "Adding up the table on your device", compute: "Calculating on your device", read_transactions: "Reading your bank statement",
  read_health_records: "Reading your medical reports", read_channel: "Reading the team chat", web_search: "Searching the web",
}
export const toolDoing = (tool: string, google = false) =>
  tool === "read_inbox" && google ? "Accessing your Gmail"
    : (tool === "list_events" || tool === "search_contacts") && google ? `${DOING[tool]} on Google`
    : DOING[tool] ?? `Running ${toolMeta(tool).done.toLowerCase()}`
export const CALC_TOOLS = new Set(["compute", "query_table"])

const FIELD_LABEL: Record<string, string> = {
  to: "To", attendees: "Invite", subject: "Subject", title: "Title", body: "Body", start: "When",
  duration_minutes: "Minutes", location: "Where", query: "Query", channel: "Channel", text: "Message", event_id: "Event",
  file_id: "File", expression: "Sum", unit: "Shown as", folder_id: "Folder", source_id: "Table", operation: "Operation",
  column: "Column", contains: "Rows containing", contains_column: "In column", month: "Month", group_by: "Per",
}

const show = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v == null ? "" : String(v))

/** A tool call Muse Spark planned. Pending: you see the real values it will use and decide. Otherwise: a compact step. */
export function ActionCard({ action, busy, onDecide }: {
  action: AgentAction; busy?: boolean; onDecide?: (decision: "confirm" | "deny") => void
}) {
  return action.status === "pending" && onDecide
    ? <PendingAction action={action} busy={!!busy} onDecide={onDecide} />
    : <ActionStep action={action} />
}

function PendingAction({ action, busy, onDecide }: { action: AgentAction; busy: boolean; onDecide: (d: "confirm" | "deny") => void }) {
  const meta = toolMeta(action.tool)
  const Icon = meta.icon
  const fields = Object.keys(action.args).filter((k) => !(k in { to: 1, attendees: 1 }) || !action.recipients.length)
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className="w-full overflow-hidden rounded-md border border-foreground/20 bg-card shadow-soft"
      role="dialog"
      aria-label={`Muse Spark wants to ${meta.wants}`}
    >
      <div className="flex items-start gap-3 border-b px-5 py-4">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-sm bg-foreground text-background">
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="font-heading text-[20px] leading-tight font-normal tracking-[-0.01em]">Muse Spark wants to {meta.wants}</p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            It planned this with placeholders only. The real values are filled in here, and nothing runs until you confirm.
          </p>
        </div>
      </div>

      {action.recipients.length > 0 && (
        <div className="border-b px-5 py-3">
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">{action.args.attendees ? "Invites" : "Goes to"}</div>
          <ul className="space-y-1">
            {action.recipients.map((r) => (
              <li key={r.label} className="flex flex-wrap items-center gap-2 text-[13.5px]">
                <Chip label={r.label} size="xs" tip="What Muse Spark wrote" />
                <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                {r.person && <span className="font-medium">{r.person}</span>}
                <span className="font-mono text-[12.5px] text-muted-foreground">{r.address}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11.5px] text-muted-foreground">Addresses come from your vault, never from the model.</p>
        </div>
      )}

      <div className="grid grid-cols-2 max-md:grid-cols-1">
        <div className="border-r px-5 py-3 max-md:border-r-0 max-md:border-b">
          <div className="mb-2 eyebrow text-muted-foreground">Muse Spark planned</div>
          <Fields fields={fields} values={action.args} masked />
        </div>
        <div className="bg-subtle px-5 py-3">
          <div className="mb-2 eyebrow text-muted-foreground">Runs on your device</div>
          <Fields fields={fields} values={action.preview} />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-subtle px-5 py-3">
        <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          {action.unmasked.length > 0 ? (
            <>Fills in {action.unmasked.length} hidden {action.unmasked.length === 1 ? "value" : "values"}:
              {action.unmasked.slice(0, 6).map((l) => <Chip key={l} label={l} size="xs" />)}
              {action.unmasked.length > 6 && <span>+{action.unmasked.length - 6}</span>}</>
          ) : "Uses no hidden values."}
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => onDecide("deny")}>Cancel</Button>
          <Button disabled={busy} onClick={() => onDecide("confirm")}>
            {busy && <Loader2 className="animate-spin" />} {meta.run}
          </Button>
        </div>
      </div>
    </motion.div>
  )
}

function Fields({ fields, values, masked }: { fields: string[]; values: Record<string, unknown>; masked?: boolean }) {
  return (
    <dl className="space-y-1.5 text-[13.5px] leading-relaxed">
      {fields.map((k) => (
        <div key={k}>
          <dt className="text-[11.5px] text-muted-foreground">{FIELD_LABEL[k] ?? k}</dt>
          <dd className="break-words whitespace-pre-wrap">{masked ? <MaskedText text={show(values[k])} size="xs" /> : show(values[k])}</dd>
        </div>
      ))}
    </dl>
  )
}

const STEP: Record<Exclude<ActionStatus, "pending">, { icon: typeof Check; text: (tool: string) => string }> = {
  done: { icon: Check, text: (t) => `${toolMeta(t).done} done` },
  refused: { icon: ShieldX, text: (t) => `Blocked by your privacy rules: ${toolMeta(t).wants}` },
  denied: { icon: X, text: (t) => `You cancelled: ${toolMeta(t).wants}` },
  failed: { icon: ShieldAlert, text: (t) => `Couldn’t ${toolMeta(t).wants}` },
}

/** A finished tool call in the thread: one line, with what was planned and what ran behind a toggle. */
export function ActionStep({ action }: { action: AgentAction }) {
  const [open, setOpen] = useState(action.status === "refused")
  if (action.status === "pending") {
    return <StepLine icon={Loader2} spin text={`Waiting for your OK to ${toolMeta(action.tool).wants}`} />
  }
  const s = STEP[action.status]
  const result = action.result as { status?: string }
  const where = action.recipients.map((r) => r.address).join(", ")
  const summary = action.status === "done"
    ? [`${toolMeta(action.tool).done}: ${result.status ?? "done"}`, where && `to ${where}`].filter(Boolean).join(" · ")
    : s.text(action.tool)
  const fields = Object.keys(action.args)
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="w-full">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className={cn("flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-[13px] transition-colors hover:bg-subtle",
          action.status === "refused" && "border-dashed border-foreground/50")}>
        <span className="grid size-5 shrink-0 place-items-center rounded-sm bg-muted">
          {(() => { const I = toolMeta(action.tool).icon; return <I className="size-3.5" aria-hidden /> })()}
        </span>
        <s.icon className="size-3.5 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1 truncate">{summary}</span>
        <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden">
            <div className="mt-1.5 space-y-2 rounded-md border bg-subtle px-3.5 py-3">
              {action.violations.length > 0 && (
                <ul className="space-y-1 text-[13px]">
                  {action.violations.map((v) => (
                    <li key={v} className="flex gap-1.5"><ShieldX className="mt-0.5 size-3.5 shrink-0" aria-hidden /><MaskedText text={v} size="xs" /></li>
                  ))}
                </ul>
              )}
              {action.error && <p className="text-[13px]">{action.error}</p>}
              {fields.length > 0 && (
                <div>
                  <div className="mb-1 eyebrow text-muted-foreground">Muse Spark planned</div>
                  <Fields fields={fields} values={action.args} masked />
                </div>
              )}
              {action.status === "done" && <ReadResult action={action} />}
              {action.status === "refused" && (
                <p className="text-[11.5px] text-muted-foreground">Nothing ran and no hidden value was filled in.</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

type Rec = Record<string, unknown>
const QUIET = new Set(["from", "date", "start", "end", "ts", "kind", "count", "items"]) // shown small, above the record
const TITLE = new Set(["subject", "name", "event"])
const HIDDEN = new Set(["id", "status", "outbox_id", "note_id", "shared_outside", "channel"])

/** What a tool brought back, exactly as Muse Spark got it: every name, address and amount already a placeholder. */
function ReadResult({ action }: { action: AgentAction }) {
  const result = action.result as Rec
  const lists = Object.entries(result).filter(([, v]) => Array.isArray(v) && v.some((x) => x && typeof x === "object"))
  const records = lists.length ? (lists[0][1] as Rec[]) : result.text || result.result ? [result] : []
  if (!records.length) return null
  const trusted = action.tool === "search_contacts"
  return (
    <div>
      <div className="mb-1 eyebrow text-muted-foreground">What Muse Spark got back</div>
      <ul className="space-y-2">
        {records.map((r, i) => (
          <li key={String(r.id ?? i)} className="rounded-md border bg-card px-3 py-2 text-[13px] leading-relaxed">
            {Object.entries(r).filter(([k, v]) => !HIDDEN.has(k) && typeof v === "string" && v).map(([k, v]) => (
              <div key={k} className={cn(QUIET.has(k) ? "truncate text-[12px] text-muted-foreground" : TITLE.has(k) ? "font-medium"
                : "line-clamp-4 whitespace-pre-wrap text-muted-foreground")}>
                {k === "result" && <span className="mr-1 text-muted-foreground">Result:</span>}
                <MaskedText text={v as string} size="xs" />
              </div>
            ))}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[11.5px] text-muted-foreground">
        {action.tool === "compute" || action.tool === "query_table"
          ? "Worked out on your device with the real amounts; Muse Spark only got the placeholders."
          : <>Read on your device and masked before Muse Spark saw it{action.mask_cost_usd ? ` · masking $${action.mask_cost_usd.toFixed(4)}` : ""}.{" "}
            {trusted ? "Your own address book counts as you, so these addresses can be recipients."
              : "Addresses found here can’t be used as recipients unless you write them yourself."}</>}
      </p>
    </div>
  )
}

/** One quiet line: a pending step, or a tool step whose action is no longer in memory (the engine restarted). */
export function StepLine({ icon: Icon, text, spin }: { icon: typeof Check; text: string; spin?: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-[13px] text-muted-foreground">
      <Icon className={cn("size-3.5 shrink-0", spin && "animate-spin")} aria-hidden />
      <span className="truncate">{text}</span>
    </div>
  )
}
