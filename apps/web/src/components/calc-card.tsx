import { MaskedText } from "@/components/privacy-text"
import { engine } from "@/lib/engine"
import type { AgentAction } from "@muse-shield/core"
import { useQuery } from "@tanstack/react-query"
import { Calculator, Cpu, Eye, ShieldCheck } from "lucide-react"
import { motion } from "motion/react"

type Rec = Record<string, unknown>
const str = (v: unknown) => (v == null ? "" : String(v))

/** One calculation as text: "expression = result", with placeholders (as Muse Spark planned and got it back). */
function stepText(a: AgentAction): { what: string; result: string } {
  const args = a.args as Rec
  const result = str((a.result as Rec)?.result)
  if (a.tool === "compute") return { what: str(args.expression), result }
  const op = str(args.operation || "sum")
  const parts = [`${op} of ${str(args.column) || "rows"}`]
  if (args.contains) parts.push(`where ${str(args.contains_column) || "row"} contains “${str(args.contains)}”`)
  if (args.month) parts.push(`in ${str(args.month)}`)
  if (args.group_by) parts.push(`per ${str(args.group_by)}`)
  return { what: parts.join(" "), result }
}

/** Consecutive on-device calculations as one card that walks through the steps: what Muse Spark planned with
 *  placeholders, and the same sums with the real amounts, worked out on this device. */
export function CalcCard({ actions, chatId }: { actions: AgentAction[]; chatId: string }) {
  const steps = actions.map(stepText)
  const masked = steps.map((s) => `${s.what} = ${s.result || "…"}`).join("\n")
  const real = useQuery({ queryKey: ["calc-real", chatId, masked], queryFn: () => engine.unmask(masked, chatId), staleTime: Infinity })
  const realLines = real.data?.text.split("\n") ?? []
  const done = actions.every((a) => a.status === "done")
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="w-full overflow-hidden rounded-md border bg-card shadow-soft">
      <div className="flex items-center justify-between gap-2 border-b bg-subtle px-3.5 py-2">
        <span className="flex items-center gap-2 text-[13px] font-medium">
          <span className="grid size-6 place-items-center rounded-sm bg-foreground text-background"><Calculator className="size-3.5" aria-hidden /></span>
          Calculated on your device
        </span>
        <span className="tabular text-[11.5px] text-muted-foreground">{steps.length} step{steps.length === 1 ? "" : "s"}{done ? "" : " · running"}</span>
      </div>
      <ol className="divide-y">
        {steps.map((s, i) => (
          <motion.li key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.18 }}
            className="grid grid-cols-[1.5rem_1fr] gap-x-2 px-3.5 py-2.5">
            <span className="mt-0.5 grid size-5 place-items-center rounded-full border text-[11px] font-medium tabular">{i + 1}</span>
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                <span className="flex shrink-0 items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground"><Eye className="size-3" aria-hidden />Muse Spark</span>
                <span className="leading-relaxed"><MaskedText text={s.what} size="xs" /> <span className="text-muted-foreground">=</span> {s.result ? <MaskedText text={s.result} size="xs" /> : "…"}</span>
              </div>
              <div className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                <span className="flex shrink-0 items-center gap-1 text-[11px] uppercase tracking-wide text-emerald-700 dark:text-emerald-300"><Cpu className="size-3" aria-hidden />Your device</span>
                <span className="font-mono text-[12.5px]">
                  {realLines[i] ? <>{realLines[i].replace(/ = ([^=]*)$/, "")} = <motion.strong initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.18 + 0.25 }}
                    className="rounded-sm bg-emerald-50 px-1 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200">{realLines[i].match(/ = ([^=]*)$/)?.[1] ?? ""}</motion.strong></>
                    : <span className="text-muted-foreground">…</span>}
                </span>
              </div>
            </div>
          </motion.li>
        ))}
      </ol>
      <p className="flex items-center gap-1.5 border-t px-3.5 py-2 text-[11.5px] text-muted-foreground">
        <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
        The real amounts never left this device. Muse Spark planned the sums with placeholders and only got the results back as placeholders.
      </p>
    </motion.div>
  )
}
