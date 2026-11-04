import React, { useCallback, useEffect, useState } from "react";
type Check = { status: string; code: string; checked_at: number | null };
type Entry = { id: string; alias: string; repository: string; revision: number; agent_id: string; local_path: string; connection_check: Check };
type Agent = { agent_id: string; online: boolean };
type Component = { ready: boolean; version: string | null; commit: string | null };
type Request = <T>(path: string, body?: unknown, method?: string) => Promise<T>;
const base = "/admin/api/repositories";
const messages: Record<string, string> = {
  OK: "로컬 저장소와 GitHub 연결 확인 완료", PATH_NOT_FOUND: "로컬 경로가 없습니다.",
  PATH_ACCESS_DENIED: "Agent에 폴더 접근 권한이 없습니다.", NOT_GIT_ROOT: "Git 저장소의 최상위 폴더를 지정하세요.",
  ORIGIN_MISMATCH: "origin이 등록한 GitHub 저장소와 다릅니다.", REMOTE_UNAVAILABLE: "GitHub 접근 실패: Agent 계정의 네트워크와 Git 인증을 확인하세요.",
  GIT_UNAVAILABLE: "Agent에서 Git을 찾을 수 없습니다.", CHECK_FAILED: "Agent에서 저장소를 확인하지 못했습니다.",
  AGENT_TIMEOUT: "확인 시간이 초과됐습니다. 선택한 Agent의 실행 상태를 확인하세요."
};
function checkText(check: Check) {
  if (check.status === "pending") return "Agent 응답 대기 중…";
  if (check.status === "running") return "Agent에서 연결 확인 중…";
  return messages[check.code] || "연결 확인 필요";
}

export function ApprovedRepositories({ request }: { request: Request }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [components, setComponents] = useState<Record<string, Component>>({});
  const [editing, setEditing] = useState<Entry | null>(null);
  const [alias, setAlias] = useState("");
  const [repository, setRepository] = useState("");
  const [agentId, setAgentId] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const reload = useCallback(async () => {
    const data = await request<{ repositories: Entry[]; public_skills: Record<string, Component> }>(base);
    setEntries(data.repositories); setComponents(data.public_skills);
  }, [request]);
  const reloadAgents = useCallback(async () => { setAgents((await request<{ agents: Agent[] }>("/admin/api/codex/agents")).agents); }, [request]);
  useEffect(() => { void reload().catch(e => setError(e.message)); void reloadAgents().catch(e => setError(e.message)); }, [reload, reloadAgents]);
  const checking = entries.some(e => ["pending", "running"].includes(e.connection_check.status));
  useEffect(() => {
    if (!checking) return;
    const timer = setInterval(() => { void reload().catch(e => setError(e.message)); }, 3000);
    return () => clearInterval(timer);
  }, [checking, reload]);
  function reset() { setEditing(null); setAlias(""); setRepository(""); setAgentId(""); setLocalPath(""); }
  async function action(run: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await run(); } catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (editing && !confirm("설정을 변경하면 이 프로젝트의 대기 작업이 취소됩니다. 계속할까요?")) return;
    await action(async () => {
      const result = await request<{ cancelled_jobs?: number }>(editing ? `${base}/${editing.id}` : base,
        { alias, repository, agent_id: agentId, local_path: localPath, ...(editing ? { revision: editing.revision } : {}) }, editing ? "PUT" : "POST");
      reset(); await reload(); setNotice(`프로젝트 실행 설정을 저장했습니다. Agent가 다음 연결 시 반영합니다.${result.cancelled_jobs ? ` 대기 작업 ${result.cancelled_jobs}개 취소.` : ""}`);
    });
  }
  return <section className="panel">
    <h2>Repository 설정</h2>
    <p className="hint">프로젝트별 GitHub 저장소, 실행할 Agent와 해당 PC의 로컬 경로를 등록합니다. 최대 10개입니다.</p>
    <p className="hint">Graphify: {components.graphify?.ready ? components.graphify.version : "설치 구성요소 확인 필요"} · UI UX Pro Max: {components.uiux?.ready ? components.uiux.version : "설치 구성요소 확인 필요"}</p>
    <p className="hint">저장 시 폴더를 생성하거나 pull하지 않습니다. 연결 확인은 선택한 Agent에서 폴더·origin·GitHub 접근을 읽기 전용으로 확인합니다.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <p role="status" aria-live="polite">{busy ? "처리 중…" : notice}</p>
    <button className="button" type="button" disabled={busy} onClick={() => void action(async () => { await reload(); await reloadAgents(); })}>목록 새로고침</button>
    <div className="table-wrap"><table><thead><tr><th>프로젝트 / GitHub</th><th>실행할 Agent / 로컬 경로</th><th>연결 상태</th><th>관리</th></tr></thead><tbody>
      {entries.map(item => <tr key={item.id}>
        <td><strong>{item.alias}</strong><br />{item.repository}</td>
        <td>{item.agent_id || "Agent 지정 필요"}<br /><code>{item.local_path || "로컬 경로 지정 필요"}</code></td>
        <td><span role="status">{checkText(item.connection_check)}</span>{item.connection_check.checked_at && <><br /><small>{new Date(item.connection_check.checked_at * 1000).toLocaleString()}</small></>}</td>
        <td><div className="actions">
          <button className="button" type="button" disabled={busy} onClick={() => { setEditing(item); setAlias(item.alias); setRepository(item.repository); setAgentId(item.agent_id); setLocalPath(item.local_path); setError(""); }}>수정</button>
          <button className="button" type="button" disabled={busy || !item.agent_id || !item.local_path || ["pending", "running"].includes(item.connection_check.status)} onClick={() => void action(async () => {
            await request(`${base}/${item.id}/test`, { revision: item.revision }, "POST"); await reload(); setNotice(`${item.alias}: ${item.agent_id}에 저장소 연결 확인을 요청했습니다.`);
          })}>저장소 연결 확인</button>
          <button className="button danger" type="button" disabled={busy} onClick={() => { if(confirm(`${item.alias} 승인을 삭제하고 대기 작업을 취소할까요? 저장소 파일은 변경되지 않습니다.`)) void action(async () => { await request(`${base}/${item.id}`, { revision: item.revision }, "DELETE"); if(editing?.id === item.id) reset(); await reload(); setNotice("저장소 승인을 삭제했습니다."); }); }}>삭제</button>
        </div></td>
      </tr>)}
    </tbody></table></div>
    {!entries.length && <p className="muted">등록된 저장소가 없습니다.</p>}
    <form onSubmit={e => void save(e)}><fieldset disabled={busy} className="settings-form"><legend>{editing ? "프로젝트 실행 설정 수정" : "프로젝트 실행 설정 추가"}</legend>
      <label>프로젝트 별칭<input required maxLength={40} pattern="[A-Za-z0-9_-]+" placeholder="ITAM" value={alias} onChange={e => setAlias(e.target.value)} /></label>
      <label>GitHub 저장소<input required maxLength={140} placeholder="owner/ITAM" value={repository} onChange={e => setRepository(e.target.value)} /></label>
      <label>실행할 Agent<input required list="repository-agents" maxLength={40} pattern="[A-Za-z0-9_-]+" placeholder="Agent를 선택하거나 ID 입력" value={agentId} onChange={e => setAgentId(e.target.value)} />
        <datalist id="repository-agents">{agents.map(a => <option key={a.agent_id} value={a.agent_id}>{a.online ? "연결됨" : "오프라인"}</option>)}</datalist>
        <span className="hint">Agent가 오프라인이면 다시 연결될 때 설정과 연결 확인 요청이 전달됩니다.</span>
      </label>
      <label>로컬 경로<input required maxLength={1024} placeholder={"C:\\개발\\ITAM"} value={localPath} onChange={e => setLocalPath(e.target.value)} />
        <span className="hint">선택한 Agent PC에 이미 존재하는 Git 저장소의 최상위 폴더입니다.</span>
      </label>
      <div className="actions"><button className="button" type="submit">저장</button><button className="button" type="button" onClick={reset}>새 항목 / 취소</button></div>
    </fieldset></form>
  </section>;
}
