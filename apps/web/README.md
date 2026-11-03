# Muse Shield web app

React + TypeScript + Vite, with shadcn/ui (Base UI + Tailwind) and TanStack Query. The same
build is what the Electron desktop app will load later. Engine types and the API client
come from `packages/core`, which the React Native app will reuse.

```bash
npm install            # in apps/web
npm run dev            # http://localhost:5173, proxies engine routes to 127.0.0.1:8765
npm run build          # dist/, served by the engine at http://127.0.0.1:8765/
```

Start the engine first, from the repo root (prototype mode: masking sends raw text to Muse
Spark, so use fake data only):

```bash
MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.app
```

Colours: each data type has its own pastel (people lavender, amounts mint, IDs and secrets rose, contacts sky, places sand, dates lilac); hidden passages are blue.
