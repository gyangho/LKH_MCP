# LKH MCP agent instructions

This repository is managed through LKH MCP and GitHub. Development agents MUST consult the connected LKH MCP engineering_workflow tool and read the applicable engineering_skill_get documents before significant implementation, bug diagnosis, or code review. Engineering skills are centrally installed on the MCP server, not locally as a Codex plugin. Read supporting files with engineering_skill_reference. If the server or selected skill is unavailable, explicitly report the limitation and do not claim that the required workflow ran.

Apply these priorities: system and user instructions > current project's published policies and repository standards > third-party skills. In particular, upstream "implement" may say to commit automatically; DO NOT commit or push unless the user explicitly authorizes each operation. Deployments, database changes, secrets/authentication changes, destructive actions and merges require separate approval. Preserve existing changes.

For Windows tasks, GitHub edits happen remotely; the Windows Codex Agent operates only in approved temporary worktrees. Its verify/diagnose/fix jobs must include server-provided engineering_guidance. Never bypass the Agent's SHA/repository allowlist or sandbox.

Use real evidence and report code written, feature integrated, tests actually run, and production deployment separately. See docs/ENGINEERING_SKILLS.md.
