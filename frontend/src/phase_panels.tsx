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
  const [phaseFilter, setPhaseFilter] = useState("all");
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
        setEvents(prev => [...new Map([...prev, ...data.events].map(e => [e.seq, e])).values()].slice(-400));
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
      <label>단계 필터 <select value={phaseFilter} onChange={e => setPhaseFilter(e.target.value)}>
        {["all","codex","git","build","test","graphify","cleanup","unknown"].map(p => <option key={p} value={p}>{p}</option>)}
      </select></label>
      <ol style={{ maxHeight: 280, overflowY: "auto", fontFamily: "monospace" }}>
        {events.filter(e => phaseFilter === "all" || e.phase === phaseFilter).map(e => <li key={e.seq}>
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
  const [instructionSearch, setInstructionSearch] = useState("");
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
      <label>지침 검색 <input value={instructionSearch} onChange={e => setInstructionSearch(e.target.value)} placeholder="이름 / Scope" /></label>
      <p className="muted">Draft는 MCP에 노출되지 않으며 관리자가 발행한 버전만 적용됩니다.</p>
      <button className="button" onClick={() => {
        setSelected(""); setName(""); setScope("global"); setScopeKey(""); setBody(""); setVersions([]);
      }}>새 지침</button>
      <div className="table-wrap"><table><thead><tr><th>이름</th><th>Scope</th><th>버전</th></tr></thead>
        <tbody>{entries.filter(e => (e.name + " " + e.scope + " " + e.scope_key).toLowerCase().includes(instructionSearch.toLowerCase())).map(e => <tr key={e.id}><td>
          <button type="button" className="button" onClick={() => void select(e)}>{e.name}</button>
        </td><td>{e.scope}:{e.scope_key}</td><td>
          {e.published_revision ?? "미발행"} / {e.revision}
        </td></tr>)}</tbody></table></div>
    </section>
    <section className="panel">
      <h2>{selected ? "지침 수정·발행" : "지침 작성"}</h2>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="field-grid">
        <label className="form-field"><span>지침 이름</span>
          <input value={name} disabled={!!selected} onChange={e => setName(e.target.value)} placeholder="instruction_name" maxLength={60} />
        </label>
        <label className="form-field"><span>적용 범위</span>
          <select value={scope} disabled={!!selected} onChange={e => setScope(e.target.value)}>
            {["global","project","agent","tool"].map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        {scope !== "global" && <label className="form-field field-full"><span>범위 식별자</span>
          <input value={scopeKey} disabled={!!selected} onChange={e => setScopeKey(e.target.value)} placeholder="project-or-agent-id" />
        </label>}
        <label className="form-field field-full"><span>지침 본문</span>
          <textarea className="instruction-editor" rows={12} value={body}
            onChange={e => setBody(e.target.value)} maxLength={4000} placeholder="Codex가 참고할 지침을 입력하세요." />
          <small className="field-hint">{body.length} / 4000자 · Draft로 저장한 뒤 명시적으로 발행합니다.</small>
        </label>
      </div>
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
type AlertState = { queue: Record<string, number>; alerts: string[];
  agents: {total: number; online: number}; stale_leases: number };
export function OperationsPanel() {
  // Deliberately no polling: updating alerts, metrics and logs while the user
  // scrolls/selects text reorders the table and makes incident analysis unusable.
  const [logs, setLogs] = useState<Log[]>([]);
  const [logFilter, setLogFilter] = useState("");
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [alerts, setAlerts] = useState<AlertState | null>(null);
  const [runtime, setRuntime] = useState<{cpu_percent: number; memory_mb: number | null;
    threads: number; uptime_seconds: number} | null>(null);
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState(0);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const loadLogs = useCallback(async () => {
    setLoadingLogs(true);
    try {
      const data = await secureApi<{events: Log[]; cursor: number}>(
        `/admin/api/operations/logs?cursor=${cursor}`);
      setLogs(prev => [...new Map([...prev, ...data.events].map(e => [e.id, e])).values()].slice(-400));
      setCursor(data.cursor);
      setError("");
    } catch (err) { setError((err as Error).message); }
    finally { setLoadingLogs(false); }
  }, [cursor]);

  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      const [metric, alert] = await Promise.all([
        secureApi<{buckets: Bucket[]; runtime: typeof runtime}>("/admin/api/operations/metrics?minutes=60"),
        secureApi<AlertState>("/admin/api/operations/alerts"),
      ]);
      setBuckets(metric.buckets);
      setRuntime(metric.runtime);
      setAlerts(alert);
      setUpdatedAt(new Date());
      setError("");
    } catch (err) { setError((err as Error).message); }
    finally { setLoadingStats(false); }
  }, []);

  useEffect(() => {
    // Mount-time fetch only. Further requests require explicit button clicks.
    void loadLogs();
    void loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const maxCount = Math.max(1, ...buckets.map(b => b.requests));
  return <div className="operations-view">
    <section className="panel">
      <div className="heading">
        <div><h2>운영 지표 · 최근 60분</h2><p className="muted">자동 갱신 없음 · 읽기 중 화면이 움직이지 않습니다.</p></div>
        <button type="button" className="button" disabled={loadingStats} onClick={() => void loadStats()}>
          {loadingStats ? "조회 중..." : "지표·경고 새로고침"}
        </button>
      </div>
      {alerts && <p role="status" className="status-strip">
        대기 {alerts.queue.queued ?? 0}건 · Agent {alerts.agents.online}/{alerts.agents.total} Online
        · 경고 {alerts.alerts.length ? alerts.alerts.join(", ") : "없음"}
      </p>}
      {error && <p role="alert" className="error">{error}</p>}
      <p>CPU {runtime?.cpu_percent ?? "—"}% · RSS {runtime?.memory_mb ?? "—"} MB ·
        Threads {runtime?.threads ?? "—"} · Uptime {runtime?.uptime_seconds ?? "—"}초
        {updatedAt && <span className="muted"> · 갱신 {updatedAt.toLocaleTimeString("ko-KR")}</span>}</p>
      <div className="pixel-chart" role="img" aria-label="최근 60분 분당 요청량 막대 그래프">
        {buckets.slice(-60).map(b => <div key={b.minute}
          title={new Date(b.minute * 1000).toLocaleTimeString("ko-KR") + " · 요청 " + b.requests + "건, 오류 " + b.errors + "건"}
          className={"pixel-bar" + (b.errors ? " has-error" : "")}
          style={{ height: Math.max(3, Math.round(96 * b.requests / maxCount)) }} />)}
      </div>
      <div className="table-wrap"><table><thead><tr><th>분</th><th>요청</th><th>오류</th><th>평균 ms</th></tr></thead>
        <tbody>{buckets.slice(-60).map(b => <tr key={b.minute}>
          <td>{new Date(b.minute * 1000).toLocaleTimeString("ko-KR")}</td>
          <td>{b.requests}</td><td>{b.errors}</td><td>{b.avg_duration_ms}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel">
      <div className="heading">
        <div><h2>구조화 로그</h2><p className="muted">자동 갱신 중지 · 다음 기록은 버튼을 눌러 불러옵니다.</p></div>
        <button className="button" type="button" disabled={loadingLogs} onClick={() => void loadLogs()}>
          {loadingLogs ? "조회 중..." : "다음 로그 100건"}
        </button>
      </div>
      <label className="form-field"><span>로그 검색 (현재 로드된 항목)</span>
        <input value={logFilter} onChange={e => setLogFilter(e.target.value)}
          placeholder="도구명 / 분류 / 결과 / Trace ID" />
      </label>
      <p className="muted">표시 {logs.length}건 · 30일 보존 · 프롬프트·명령·인증정보 저장하지 않음</p>
      <div className="table-wrap stable-log-table"><table><thead><tr>
        <th>시각</th><th>분류</th><th>이름</th><th>결과</th><th>ms</th><th>Trace ID</th>
      </tr></thead><tbody>
        {logs.filter(e => (e.name + " " + e.category + " " + e.result + " " + e.trace_id)
          .toLowerCase().includes(logFilter.toLowerCase())).map(e => <tr key={e.id}>
          <td>{new Date(e.at * 1000).toLocaleString("ko-KR")}</td>
          <td>{e.category}</td><td>{e.name}</td><td>{e.result}</td>
          <td>{e.duration_ms}</td><td title={e.trace_id}>{e.trace_id.slice(0, 10)}</td>
        </tr>)}
      </tbody></table></div>
    </section>
  </div>;
}
