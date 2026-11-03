import { createEngine } from "@muse-shield/core"

// Same origin in dev (Vite proxies engine routes) and when the engine serves the build.
// Electron sets VITE_ENGINE_URL to the bundled engine's address.
export const engine = createEngine(import.meta.env.VITE_ENGINE_URL ?? "")
