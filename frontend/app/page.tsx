"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Clip = {
  index: number;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  viral_score: number;
  reason: string;
  hook: string;
  download_url: string;
  filename: string;
};

type JobStatus = {
  job_id: string;
  status: string;
  progress: number;
  stage: string;
  message: string;
  clips: Clip[];
  error: string;
};

function fmt(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [maxClips, setMaxClips] = useState(8);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setError("");
    setBusy(true);
    setJob(null);
    try {
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), max_clips: maxClips, mode: "podcast" }),
      });
      if (!r.ok) throw new Error(await r.text());
      const j: JobStatus = await r.json();
      setJob(j);
      poll(j.job_id);
    } catch (err: any) {
      setError(err.message || "Failed to start job");
      setBusy(false);
    }
  }

  async function poll(jobId: string) {
    stopPolling();
    timer.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/jobs/${jobId}`);
        if (!r.ok) throw new Error(await r.text());
        const j: JobStatus = await r.json();
        setJob(j);
        if (j.status === "done" || j.status === "error") {
          stopPolling();
          setBusy(false);
        }
      } catch {
        /* transient */
      }
    }, 1500);
  }

  const pct = job ? Math.round(job.progress * 100) : 0;

  return (
    <main style={{ maxWidth: 980, margin: "0 auto", padding: "48px 24px 96px" }}>
      <header style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--accent)", fontFamily: "monospace" }}>AI Podcast Clipper</div>
        <h1 style={{ fontSize: 56, lineHeight: 0.95, margin: "10px 0 8px", letterSpacing: "-0.02em" }}>
          CLIPPER<span style={{ color: "var(--accent)" }}>.</span>
        </h1>
        <p style={{ color: "var(--muted)", margin: 0, maxWidth: 560 }}>
          Tempel link podcast &mdash; AI menemukan momen viral, memotong hanya bagian terbaik, lalu membingkai ulang ke 9:16 dengan subtitle word-by-word.
        </p>
      </header>

      <form onSubmit={submit} style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 28 }}>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://youtube.com/watch?v=...  (YouTube, TikTok, Instagram)"
          style={{ flex: "1 1 420px", padding: "14px 16px", borderRadius: 10, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 15 }}
        />
        <select value={maxClips} onChange={(e) => setMaxClips(Number(e.target.value))}
          style={{ padding: "14px 12px", borderRadius: 10, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 15 }}>
          {[4,5,6,7,8,9,10].map((n) => <option key={n} value={n}>{n} clips</option>)}
        </select>
        <button disabled={busy} type="submit"
          style={{ padding: "14px 22px", borderRadius: 10, border: "none", background: busy ? "var(--line)" : "var(--accent)", color: "#0b0d10", fontWeight: 700, fontSize: 15, cursor: busy ? "default" : "pointer" }}>
          {busy ? "Processing..." : "Generate clips"}
        </button>
      </form>

      {error && <div style={{ padding: 12, borderRadius: 8, background: "#2a1518", border: "1px solid #5c2a2a", color: "#ff9a9a", marginBottom: 20 }}>{error}</div>}

      {job && job.status !== "done" && job.status !== "error" && (
        <div style={{ padding: 20, borderRadius: 12, background: "var(--panel)", border: "1px solid var(--line)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ color: "var(--muted)" }}>{job.message || "Working..."}</span>
            <span style={{ fontFamily: "monospace", color: "var(--accent-2)" }}>{pct}%</span>
          </div>
          <div style={{ height: 10, borderRadius: 6, background: "var(--line)", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${pct}%`, background: "linear-gradient(90deg, var(--accent), var(--accent-2))", transition: "width 0.5s ease" }} />
          </div>
        </div>
      )}

      {job && job.status === "error" && (
        <div style={{ padding: 12, borderRadius: 8, background: "#2a1518", border: "1px solid #5c2a2a", color: "#ff9a9a" }}>{job.error}</div>
      )}

      {job && job.status === "done" && (
        <div>
          <div style={{ color: "var(--ok)", fontWeight: 700, marginBottom: 18 }}>{job.clips.length} clips siap diunduh</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
            {job.clips.map((c) => (
              <div key={c.index} style={{ borderRadius: 12, background: "var(--panel)", border: "1px solid var(--line)", overflow: "hidden" }}>
                <video src={c.download_url} controls preload="metadata" style={{ width: "100%", aspectRatio: "9/16", background: "#000", display: "block" }} />
                <div style={{ padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>#{c.index}</span>
                    <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--accent-2)" }}>★ {c.viral_score}/10</span>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{c.title}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>{fmt(c.start_time)} &ndash; {fmt(c.end_time)} &middot; {c.duration}s</div>
                  <a href={c.download_url} download={c.filename}
                    style={{ display: "block", textAlign: "center", padding: "10px", borderRadius: 8, background: "var(--accent)", color: "#0b0d10", fontWeight: 700, fontSize: 13, textDecoration: "none" }}>
                    Download
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
