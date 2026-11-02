import React, { useCallback, useEffect, useState } from "react";
type Entry = { id: string; alias: string; repository: string; revision: number };
type Request = <T>(path: string, body?: unknown, method?: string) => Promise<T>;
const base = "/admin/api/repositories";

export function ApprovedRepositories({ request }: { request: Request }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [alias, setAlias] = useState("");
  const [repository, setRepository] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const reload = useCallback(async () => { setEntries((await request<{ repositories: Entry[] }>(base)).repositories); }, [request]);
  useEffect(() => { void reload().catch(e => setError(e.message)); }, [reload]);
  function reset() { setEditing(null); setAlias(""); setRepository(""); }
  async function action(run: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await run(); } catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (editing && !confirm("저장소 승인을 변경하면 해당 별칭의 대기 작업은 취소됩니다. 계속할까요?")) return;
    await action(async () => {
      const result = await request<{ cancelled_jobs?: number }>(editing ? `${base}/${editing.id}` : base,
        { alias, repository, ...(editing ? { revision: editing.revision } : {}) }, editing ? "PUT" : "POST");
      reset(); await reload(); setNotice(`승인 저장소를 저장했습니다.${result.cancelled_jobs ? ` 대기 작업 ${result.cancelled_jobs}개 취소.` : ""}`);
    });
  }
  return <section className="panel">
    <h2>승인된 GitHub 저장소</h2>
    <p className="hint">최대 10개. 별칭과 저장소는 Agent의 프로젝트 설정과 일치해야 합니다. 이 목록 변경은 로컬 checkout이나 Agent 설정 파일을 수정하지 않습니다.</p>
    <p className="hint">승인 변경·삭제 시 해당 별칭의 대기 작업은 취소하며 실행 중인 작업이 있으면 변경을 거부합니다.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <p role="status" aria-live="polite">{busy ? "처리 중…" : notice}</p>
    <button className="button" type="button" disabled={busy} onClick={() => void action(reload)}>목록 새로고침</button>
    <div className="table-wrap"><table><thead><tr><th>프로젝트 별칭</th><th>저장소</th><th>관리</th></tr></thead><tbody>
      {entries.map(item => <tr key={item.id}><td>{item.alias}</td><td>{item.repository}</td><td><div className="actions">
        <button className="button" type="button" disabled={busy} onClick={() => { setEditing(item); setAlias(item.alias); setRepository(item.repository); setError(""); }}>수정</button>
        <button className="button danger" type="button" disabled={busy} onClick={() => { if(confirm(`${item.alias} 승인을 삭제하고 대기 작업을 취소할까요? 저장소 파일은 변경되지 않습니다.`)) void action(async () => { await request(`${base}/${item.id}`, { revision: item.revision }, "DELETE"); if(editing?.id === item.id) reset(); await reload(); setNotice("저장소 승인을 삭제했습니다."); }); }}>삭제</button>
      </div></td></tr>)}
    </tbody></table></div>
    {!entries.length && <p className="muted">승인된 저장소가 없습니다.</p>}
    <form onSubmit={e => void save(e)}><fieldset disabled={busy} className="settings-form"><legend>{editing ? "승인 저장소 수정" : "승인 저장소 추가"}</legend>
      <label>프로젝트 별칭<input required maxLength={40} pattern="[A-Za-z0-9_-]+" placeholder="LKH_MCP" value={alias} onChange={e => setAlias(e.target.value)} /></label>
      <label>GitHub 저장소<input required maxLength={140} placeholder="owner/repository" value={repository} onChange={e => setRepository(e.target.value)} /></label>
      <div className="actions"><button className="button" type="submit">저장</button><button className="button" type="button" onClick={reset}>새 항목 / 취소</button></div>
    </fieldset></form>
  </section>;
}
