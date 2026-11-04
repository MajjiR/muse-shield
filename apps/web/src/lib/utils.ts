export { cn } from "cn"

/** "accounts/a/models/muse-shield-glimmer-lora-v2-full#accounts/a/deployments/d" -> "muse-shield-glimmer-lora-v2-full" */
export function modelLabel(model: string | null | undefined): string {
  if (!model) return "off"
  const id = model.split("#")[0].split("/").pop() || model
  // Our fine-tunes read better by version: muse-shield-glimmer-er-v3a-s250 -> "Glimmer er-v3a (step 250)"
  const m = id.match(/^muse-shield-glimmer-(.+?)(?:-s(\d+))?$/)
  return m ? `Glimmer ${m[1]}${m[2] ? ` (step ${m[2]})` : ""}` : id
}

export const isGlimmer = (model: string | null | undefined) => !!model && model.includes("glimmer")
