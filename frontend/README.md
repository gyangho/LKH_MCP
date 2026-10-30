# Admin frontend

React 19, TypeScript and Vite. Build with `cd frontend && npm ci && npm run build`.

Production currently serves generated assets from Python behind the private Naru gateway. Do not commit `frontend/dist`.

For current operations, read [OPERATIONS](../docs/OPERATIONS.md). For Windows Native Installer plans, see [ROADMAP](../docs/ROADMAP.md). Agent start/stop and JSONL live console are planned, not implemented.

NanumSquare font licensing: [NANUMSQUARE-LICENSE.md](NANUMSQUARE-LICENSE.md). The app falls back to Malgun Gothic when the webfont is unavailable.
