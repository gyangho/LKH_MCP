import React, { useCallback, useEffect, useState } from "react";

type Profile = {
  name: string; host: string; port: number; service: string; sid: string; dsn: string;
  username: string; allowed_tables: string; enabled: boolean;
};
type Connection = Profile & { id: string; revision: number; password_configured: boolean; updated_at: string };
type Request = <T>(path: string, body?: unknown, method?: string) => Promise<T>;
const empty = (): Profile => ({ name: "", host: "127.0.0.1", port: 1521, service: "", sid: "", dsn: "",
  username: "", allowed_tables: "", enabled: true });
const base = "/admin/api/oracle/connections";

export function OracleConnections({ request }: { request: Request }) {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [draft, setDraft] = useState<Profile>(empty);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const reload = useCallback(async () => {
    const response = await request<{ connections: Connection[] }>(base);
    setConnections(response.connections);
  }, [request]);
  useEffect(() => { void reload().catch(e => setError(e.message)); }, [reload]);
  function reset() { setEditing(null); setDraft(empty()); setPassword(""); }
  async function action(run: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await run(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    await action(async () => {
      await request(editing ? `${base}/${editing.id}` : base,
        { ...draft, password, ...(editing ? { revision: editing.revision } : {}) }, editing ? "PUT" : "POST");
      reset(); await reload(); setNotice("연결을 저장했습니다.");
    });
  }
  return <>
    <section className="panel">
      <h2>Oracle 데이터베이스 연결</h2>
      <p className="hint">연결마다 계정과 조회 허용 테이블을 분리합니다. MCP 도구에서는 연결 ID를 선택하세요.</p>
      <div className="actions">
        <button type="button" className="button" disabled={busy} onClick={() => void action(async () => { await reload(); setNotice("목록을 새로고침했습니다. 편집 중인 값은 유지됩니다."); })}>목록 새로고침</button>
        <button type="button" className="button" disabled={busy} onClick={reset}>새 연결 작성</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <p role="status" aria-live="polite">{busy ? "처리 중…" : notice}</p>
      {!connections.length && <p className="muted">등록된 연결이 없습니다. 아래에서 첫 연결을 추가하세요.</p>}
      <div className="table-wrap"><table><thead><tr><th>연결</th><th>주소 / 사용자</th><th>상태</th><th>관리</th></tr></thead><tbody>
        {connections.map(c => <tr key={c.id}>
          <td><strong>{c.name}</strong><br /><code>{c.id}</code></td>
          <td>{c.dsn || `${c.host}:${c.port} / ${c.service || c.sid}`}<br />{c.username}</td>
          <td>{c.enabled ? "활성" : "비활성"}</td>
          <td><div className="actions">
            <button type="button" className="button" disabled={busy} onClick={() => { setEditing(c); const { id, revision, password_configured, updated_at, ...profile } = c; setDraft(profile); setPassword(""); setError(""); setNotice(`${c.name} 편집 중`); }}>수정</button>
            <button type="button" className="button" disabled={busy} onClick={() => void action(async () => { await request(`${base}/${c.id}/test`, {}); setNotice(`${c.name}: 저장된 설정의 연결 테스트 성공`); })}>저장된 연결 테스트</button>
            <button type="button" className="button danger" disabled={busy} onClick={() => {
              if (confirm(`${c.name} 연결정보를 삭제할까요? 실제 데이터베이스는 변경되지 않습니다.`)) void action(async () => { await request(`${base}/${c.id}`, { revision: c.revision }, "DELETE"); if (editing?.id === c.id) reset(); await reload(); setNotice("연결정보를 삭제했습니다."); });
            }}>삭제</button>
          </div></td>
        </tr>)}
      </tbody></table></div>
    </section>
    <section className="panel">
      <h2>{editing ? `${editing.name} 수정` : "새 연결 추가"}</h2>
      <form onSubmit={e => void save(e)}>
        <fieldset disabled={busy} className="settings-form">
          <legend>{editing ? `연결 ID: ${editing.id}` : "연결 정보"}</legend>
          <label>연결 이름<input required maxLength={80} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
          <label>호스트<input required={!draft.dsn} maxLength={253} value={draft.host} onChange={e => setDraft({ ...draft, host: e.target.value })} /></label>
          <label>포트<input required type="number" min={1} max={65535} value={draft.port} onChange={e => setDraft({ ...draft, port: Number(e.target.value) })} /></label>
          <label>Service Name<input maxLength={128} disabled={!!draft.dsn} value={draft.service} onChange={e => setDraft({ ...draft, service: e.target.value, sid: "" })} /></label>
          <label>SID<input maxLength={128} disabled={!!draft.dsn} value={draft.sid} onChange={e => setDraft({ ...draft, sid: e.target.value, service: "" })} /></label>
          <label>사용자<input required maxLength={512} autoComplete="off" value={draft.username} onChange={e => setDraft({ ...draft, username: e.target.value })} /></label>
          <label>암호<input type="password" required={!editing} maxLength={1024} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
            <span className="hint">{editing ? "비워두면 기존 암호를 유지합니다." : "Windows 보호 기능으로 암호화해 저장합니다."}</span></label>
          <label>조회 허용 테이블<input maxLength={2000} placeholder="OWNER.TABLE1,OWNER.TABLE2" value={draft.allowed_tables} onChange={e => setDraft({ ...draft, allowed_tables: e.target.value })} />
            <span className="hint">빈 값은 테이블 조회를 차단합니다. *는 해당 계정이 접근 가능한 전체 테이블을 허용합니다.</span></label>
          <label className="choice"><input type="checkbox" checked={draft.enabled} onChange={e => setDraft({ ...draft, enabled: e.target.checked })} /> 연결 활성화</label>
          <details><summary>고급: 직접 DSN</summary><label>DSN<input maxLength={512} value={draft.dsn} onChange={e => setDraft({ ...draft, dsn: e.target.value, service: "", sid: "" })} /></label><p className="hint">입력하면 호스트·포트 대신 사용합니다. Service Name/SID와 함께 설정할 수 없습니다.</p></details>
          <div className="actions"><button className="button" type="submit">{busy ? "저장 중…" : "연결 저장"}</button><button className="button" type="button" onClick={reset}>편집 취소</button></div>
        </fieldset>
      </form>
    </section>
  </>;
}
