# Central engineering skills on LKH MCP

## Contract

Matt Pocock's engineering skills are **hosted by the LKH MCP server**, rather than installed as local Codex/Claude/ChatGPT plugins. The pinned upstream repository is https://github.com/mattpocock/skills at commit `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d` (MIT license retained).

The MCP server exposes `engineering_skills_list`, `engineering_skill_get`, `engineering_skill_reference`, and `engineering_workflow`. All are read-only and never execute upstream scripts. A client's MCP connection must already be configured; no promise is made that a generic native Skill tool will discover these automatically.

Development agents should use `engineering_workflow` at the beginning of a relevant task and read the selected `engineering_skill_get` documents. LKH native Windows Agent work queues **inject server-hosted instructions** for verify, diagnose and fix, so the Windows host needs no Matt Pocock plugin. The agent still needs its existing Codex CLI and approved local checkout. Graphify retains its separate execution contract.

## Server installation (not client installation)

On the Windows MCP build/server host, from the repository root:

```powershell
.\scripts\install-matt-skills.ps1
```

On a Linux MCP server/build host:

```bash
bash scripts/install-matt-skills.sh
```

Both installers fetch only upstream GitHub content pinned to the reviewed commit and refuse to replace an existing different folder. They do **not** restart a service, deploy to production, or alter Codex client plugins. The directory `vendor/mattpocock-skills` is ignored by Git; keep the upstream `LICENSE` and `.lkh-pinned-revision` marker. A pre-staged copy can alternatively be referenced via the server-only absolute path environment variable `LKH_ENGINEERING_SKILLS_ROOT`.

Native Windows packaging includes this vendor directory. The build script refuses a missing staged package. Linux/Docker packaging must include the same folder in the build context or mount it read-only and set the server path override, since Git ignores it. Verify that the actual running MCP process can see the files.

## Authority and safety

Higher-priority system/user/project rules always override third-party skill text. In particular, upstream `implement` says to commit by default, but LKH requires **separate explicit commit and push approvals**. Deployment, DB/schema, secrets/authentication and destructive work require separate approval. External issue/PR changes are also authorization gated. The server provides procedural Markdown, not arbitrary shell access.

The Windows Agent claim route requires `engineering_skills_version: 1`; old Agent builds are rejected rather than silently ignoring the new guidance. The queue keeps verify/diagnose/fix jobs queued if server skills are unavailable, returning a non-secret `engineering_skills_unavailable` reason. A job claim does not imply task completion; confirm real tool execution.

For all three job kinds, claim also attaches the published `lkh-mcp-usage` and `windows-gradle-verification` documents to `engineering_guidance`, including their IDs, scope, published revisions and bodies. Resolution uses the job's project, claiming Agent and `codex_enqueue` tool context with the existing tool > agent > project > global precedence. Draft edits never replace the published snapshot. An unregistered document is represented as `found: false`; lookup/schema failures or a combined payload above 50,000 characters leave the job queued with `engineering_instructions_unavailable`, without a lease or quota consumption. Resolution reuses the claim transaction and does not create instruction tables or publish/edit instructions.

The Agent's local verification profile is used for verify, diagnose and fix. Queued instructions cannot choose asset paths or change sandbox/network policy. Prepared Gradle commands, toolchain metadata and preflight results are supplied in the prompt; compilers and tests must still actually run. Reports may include `status` (`completed`, `environment_blocked`, `compile_failed`, `test_failed`, `incomplete`) and actual `tests_executed`, `tests_failed`, `tests_skipped` counts. Unknown counts remain absent/null; failure statuses cannot become successful tasks. See [environment registration and refresh](BUILD_AND_CONFIGURATION.md#windows-agent-검증-환경-준비).

## Tests and user acceptance

1. Run `python -m compileall -q src windows_agent tests`.
2. Run `$env:PYTHONPATH='src'; python -m unittest discover -s tests -t . -p 'test_*.py' -v` on Windows. On Linux use `PYTHONPATH=src python -m unittest discover -s tests -t . -p 'test_*.py' -v`.
3. Run `npm ci`, `npm run build` in `frontend`.
4. On the MCP server/staging service, call `engineering_skills_list`, `engineering_workflow('bugfix')`, `engineering_skill_get('tdd')`, and `engineering_skill_reference('tdd','tests.md')`. Verify SHA, policy and content, and that `../LICENSE` is rejected.
5. On a **separate approved staging Windows Agent**, queue a verify task by approved SHA and confirm the generated Codex prompt follows the centrally supplied TDD procedure without installing the Matt Pocock plugin locally. Check an unprepared server does not lease a verify job. Do not use production as a test environment without separate approval.

Code, integration, executed tests and production deployment must be reported independently.
