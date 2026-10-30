import { useCallback, useEffect, useState } from "react";

async function secureApi<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: body === undefined ? {} : {
      "Content-Type": "application/json", "X-LKH-Admin-Action": "1",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    location.replace("/admin/login");
    throw Error("관리자 재로그인 필요");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as {error?: string};
    throw Error(error.error || `API ${response.status}`);
  }
  return await response.json() as T;
}

type Event = { seq: number; at: number; type: string; phase: string };
export function CodexEventStream({ taskId }: { taskId: string }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<Event[]>([]);
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let alive = true;
    async function poll() {
      try {
        const data = await secureApi<{events: Event[]; cursor: number}>(
          `/admin/api/codex/events/${encodeURIComponent(taskId)}?after=${cursor}`);
        if (!alive) return;
        setEvents(prev => [...prev, ...data.events].slice(-400));
        setCursor(data.cursor);
        setError("");
      } catch (err) {
        if (alive) setError((err as Error).message);
      }
    }
    void poll();
    const timer = setInterval(() => {
      if (!document.hidden) void poll();
    }, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, [open, cursor, taskId]);
  return <section>
    <button type="button" className="button" onClick={() => setOpen(!open)}>
      {open ? "이벤트 닫기" : "Codex 실행 타임라인"}
    </button>
    {open && <div>
      <p className="muted">2초 간격 메타데이터 조회 · 명령/프롬프트/출력은 저장하지 않음</p>
      {error && <p className="error" role="alert">{error}</p>}
      <ol style={{ maxHeight: 280, overflowY: "auto", fontFamily: "monospace" }}>
        {events.map(e => <li key={e.seq}>
          {new Date(e.at * 1000).toLocaleTimeString("ko-KR")} · {e.phase} / {e.type}
        </li>)}
      </ol>
      {events.length === 0 && <p className="muted">수집된 이벤트가 없습니다.</p>}
    </div>}
  </section>;
}

type Entry = { id: string; name: string; scope: string; scope_key: string;
  revision: number; published_revision: number | null; body: string | null };
type Version = { revision: number; author: string; at: number; body: string };
export function InstructionsPanel() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [scope, setScope] = useState("global");
  const [scopeKey, setScopeKey] = useState("");
  const [body, setBody] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const result = await secureApi<{instructions: Entry[]}>("/admin/api/instructions");
    setEntries(result.instructions);
  }, []);
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, [refresh]);

  async function select(e: Entry) {
    setSelected(e.id);
    setName(e.name); setScope(e.scope); setScopeKey(e.scope_key);
    try {
      const result = await secureApi<{versions: Version[]}>(
        `/admin/api/instructions/${e.id}/history`);
      setVersions(result.versions);
      setBody(result.versions[0]?.body || "");
    } catch (err) { setError((err as Error).message); }
  }

  async function submit(action: "create" | "save" | "publish" | "rollback",
                        targetRevision?: number) {
    const entry = entries.find(e => e.id === selected);
    if (!entry && action !== "create") return;
    if ((action === "publish" || action === "rollback") &&
        !confirm("선택한 지침 버전을 MCP에 발행하시겠습니까?")) return;
    const payload = action === "create"
      ? { name, scope, scope_key: scope === "global" ? "" : scopeKey, body }
      : action === "save" ? { id: selected, revision: entry!.revision, body }
      : action === "publish" ? { id: selected, revision: entry!.revision }
      : { id: selected, revision: entry!.revision, target_revision: targetRevision };
    setBusy(true); setError("");
    try {
      await secureApi("/admin/api/instructions", { action, payload });
      await refresh();
      if (selected) {
        const result = await secureApi<{versions: Version[]}>(
          `/admin/api/instructions/${selected}/history`);
        setVersions(result.versions);
      }
      if (action === "create") { setBody(""); setName(""); setSelected(""); }
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return <div className="task-grid">
    <section className="panel">
      <h2>지침 목록</h2>
      <p className="muted">Draft는 MCP에 노출되지 않으며 관리자가 발행한 버전만 적용됩니다.</p>
      <button className="button" onClick={() => {
        setSelected(""); setName(""); setScope("global"); setScopeKey(""); setBody(""); setVersions([]);
      }}>새 지침</button>
      <div className="table-wrap"><table><thead><tr><th>이름</th><th>Scope</th><th>버전</th></tr></thead>
        <tbody>{entries.map(e => <tr key={e.id}><td>
          <button type="button" className="button" onClick={() => void select(e)}>{e.name}</button>
        </td><td>{e.scope}:{e.scope_key}</td><td>
          {e.published_revision ?? "미발행"} / {e.revision}
        </td></tr>)}</tbody></table></div>
    </section>
    <section className="panel">
      <h2>{selected ? "지침 수정·발행" : "지침 작성"}</h2>
      {error && <p className="error" role="alert">{error}</p>}
      <label>이름 <input value={name} disabled={!!selected} onChange={e => setName(e.target.value)} placeholder="name_slug" /></label>
      <label>범위 <select value={scope} disabled={!!selected} onChange={e => setScope(e.target.value)}>
        {["global","project","agent","tool"].map(v => <option key={v}>{v}</option>)}
      </select></label>
      {scope !== "global" && <label>범위 키 <input disabled={!!selected} value={scopeKey} onChange={e => setScopeKey(e.target.value)} /></label>}
      <label>지침 본문 <textarea rows={8} value={body} onChange={e => setBody(e.target.value)} maxLength={4000} /></label>
      <div className="actions">
        <button className="button" disabled={busy} onClick={() => void submit(selected ? "save" : "create")}>
          {selected ? "새 Draft 버전 저장" : "Draft 생성"}</button>
        {selected && <button className="button" disabled={busy} onClick={() => void submit("publish")}>현재 버전 발행</button>}
      </div>
      {selected && <details><summary>이전 버전 / 롤백</summary>
        {versions.map(v => <p key={v.revision}>v{v.revision} · {v.author} ·
          <button className="button" disabled={busy} onClick={() => void submit("rollback", v.revision)}>이 버전 발행</button>
          <button className="button" onClick={() => setBody(v.body)}>본문 복원(미저장)</button>
        </p>)}
      </details>}
    </section>
  </div>;
}

type Log = { id: number; at: number; category: string; name: string;
  result: string; duration_ms: number; trace_id: string };
type Bucket = { minute: number; requests: number; errors: number; avg_duration_ms: number };
export function OperationsPanel() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [runtime, setRuntime] = useState<{cpu_percent: number; memory_mb: number | null;
    threads: number; uptime_seconds: number} | null>(null);
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState(0);
  const refresh = useCallback(async () => {
    try {
      const [log, metric] = await Promise.all([
        secureApi<{events: Log[]; cursor: number}>(`/admin/api/operations/logs?cursor=${cursor}`),
        secureApi<{buckets: Bucket[]; runtime: typeof runtime}>(`/admin/api/operations/metrics?minutes=60`),
      ]);
      setLogs(prev => [...prev, ...log.events].slice(-200));
      setCursor(log.cursor);
      setBuckets(metric.buckets); setRuntime(metric.runtime); setError("");
    } catch (err) { setError((err as Error).message); }
  }, [cursor]);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  return <>
    <section className="panel">
      <h2>운영 지표 · 최근 60분</h2>
      {error && <p className="error" role="alert">{error}</p>}
      <p>CPU {runtime?.cpu_percent ?? "—"}% · RSS {runtime?.memory_mb ?? "—"} MB ·
        Threads {runtime?.threads ?? "—"} · Uptime {runtime?.uptime_seconds ?? "—"}초</p>
      <div className="table-wrap"><table><thead><tr><th>분</th><th>요청</th><th>오류</th><th>평균 ms</th></tr></thead>
        <tbody>{buckets.slice(-60).map(b => <tr key={b.minute}>
          <td>{new Date(b.minute * 1000).toLocaleTimeString("ko-KR")}</td>
          <td>{b.requests}</td><td>{b.errors}</td><td>{b.avg_duration_ms}</td></tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel">
      <h2>구조화 로그 (메타데이터만)</h2>
      <p className="muted">30일 보존 · 프롬프트·명령·인증 토큰·출력 본문 미저장</p>
      <div className="table-wrap"><table><thead><tr><th>시각</th><th>구분</th><th>이름</th><th>결과</th><th>ms</th><th>Trace ID</th></tr></thead>
        <tbody>{logs.slice().reverse().map(e => <tr key={e.id}>
          <td>{new Date(e.at * 1000).toLocaleString("ko-KR")}</td>
          <td>{e.category}</td><td>{e.name}</td><td>{e.result}</td><td>{e.duration_ms}</td><td title={e.trace_id}>{e.trace_id.slice(0, 10)}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
  </>;
}
