# LKH MCP admin frontend

React 19 + TypeScript + Vite admin SPA. The Python MCP server serves the built files under /admin; no extra browser-facing ports.

Build: `cd frontend && npm install && npm run build`. Naru Docker image builds frontend automatically.

NanumSquare by NAVER (SIL OFL 1.1): https://help.naver.com/service/30016/contents/18088 . The CSS loads public hosted webfont from moonspam/NanumSquare; no font binaries are copied into this repository. Ensure the private WARP clients can access jsDelivr, or install NanumSquare locally (fallback: Malgun Gothic). License notice in `frontend/NANUMSQUARE-LICENSE.md`.
