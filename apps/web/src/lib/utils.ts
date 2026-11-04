export { cn } from "cn"

/** "accounts/a/models/muse-shield-glimmer-lora-v2-full#accounts/a/deployments/d" -> "muse-shield-glimmer-lora-v2-full" */
export function modelLabel(model: string | null | undefined): string {
  if (!model) return "off"
  return model.split("#")[0].split("/").pop() || model
}

export const isGlimmer = (model: string | null | undefined) => !!model && model.includes("glimmer")
