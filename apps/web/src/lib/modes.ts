// Short names for the masking modes, for tight spots like the sidebar.
const SHORT: Record<string, string> = {
  pii_context: "PII + context", resolution: "Entity res.", resolution_classify: "Entity res. + classify", spark: "Spark",
}

export const modeShort = (mode?: string | null) => (mode ? SHORT[mode] ?? mode : null)
