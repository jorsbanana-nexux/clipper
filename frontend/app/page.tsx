"use client";

// CLIPPER — v0.4 UI: SATU ALUR LURUS.
// Tempel URL -> jadi clip. Tidak ada opsi, tidak ada pilihan gaya —
// pipeline berjalan dengan preset flagship (MrBeast, 9:16, 8 clip).
// Semua keputusan kreatif ada di .env backend, bukan di sini.

import { useCallback, useEffect, useRef, useState } from "react";

type Scores = { hook: number; payoff: number; emotion: number; quotability: number; energy: number };

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
  scores: Scores;
  caption: string;
  hashtags: string[];
  srt_url: string;
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

function scoreColor(v: number) {
  return v >= 8 ? "var(--ok)" : v >= 5 ? "var(--accent-2)" : "var(--muted)";
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
      <span style={{ width: 86, fontSize: 11, color: "var(--muted)" }}>{label}</span>
      <div style={{ flex: 1, height: 6, borderRadius: 4, background: "var(--line)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${value * 10}%`, background: scoreColor(value), borderRadius: 4 }} />
      </div>
      <span style={{ width: 22, fontSize: 11, fontFamily: "monospace", color: "var(--muted)", textAlign: "right" }}>{value}</span>
    </div>
  );
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState("");
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
      // ALUR TUNGGAL: hanya URL. Gaya subtitle, aspek, jumlah clip —
      // semua ditentukan preset backend (MrBeast · 9:16 · 8 clip).
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), mode: "podcast" }),
      });
      if (!r.ok) throw new Error(await r.text());
      const j: JobStatus = await r.json();
      setJob(j);
      poll(j.job_id);
    } catch (err: any) {
      setError(err.message || "Gagal memulai job");
      setBusy(false);
    }
  }

  async function poll(jobId: string) {
    stopPolling();
    timer.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/jobs/${jobId}`);
        const j: JobStatus = await r.json();
        setJob(j);
        if (j.status === "done" || j.status === "error") {
          stopPolling();
          setBusy(false);
          if (j.status === "error") setError(j.error || j.message || "Job gagal");
        }
      } catch (err: any) {
        stopPolling();
        setBusy(false);
        setError(err.message || "Koneksi ke backend terputus");
      }
    }, 1500);
  }

  function copy(text: string, tag: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(tag);
      setTimeout(() => setCopied(""), 1600);
    });
  }

  const running = busy && job && job.status !== "done" && job.status !== "error";

  return (
    <main style={{ maxWidth: 920, margin: "0 auto", padding: "48px 20px 80px" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 40, margin: 0, letterSpacing: -1, fontWeight: 800 }}>
          CLIPPER<span style={{ color: "var(--accent)" }}>.</span>
        </h1>
        <p style={{ color: "var(--muted)", margin: "6px 0 0", fontSize: 15 }}>
          Tempel link video → AI menemukan momen viral → clip 9:16 siap posting.
        </p>
      </header>

      {/* ---- SATU FORM: URL + tombol. Selesai. ---- */}
      <form onSubmit={submit} style={{ display: "flex", gap: 10 }}>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://youtube.com/watch?v=..."
          autoFocus
          style={{
            flex: 1, padding: "16px 18px", borderRadius: 12, fontSize: 16,
            border: "1px solid var(--line)", background: "var(--panel)",
            color: "var(--ink)", outline: "none",
          }}
        />
        <button
          type="submit"
          disabled={busy || !url.trim()}
          style={{
            padding: "16px 28px", borderRadius: 12, fontSize: 16, fontWeight: 700,
            background: "var(--accent)", color: "#fff", border: "none", cursor: "pointer",
            opacity: busy || !url.trim() ? 0.55 : 1,
          }}
        >
          {busy ? "Memproses..." : "Buat Clip"}
        </button>
      </form>

      {error && (
        <p style={{ color: "#ff6b6b", background: "#2a1414", padding: "10px 14px", borderRadius: 10, fontSize: 14, marginTop: 16, whiteSpace: "pre-wrap" }}>
          {error}
        </p>
      )}

      {/* ---- PROGRESS ---- */}
      {running && job && (
        <section style={{ marginTop: 32 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--muted)", marginBottom: 8 }}>
            <span>{job.message || job.stage}</span>
            <span>{Math.round(job.progress * 100)}%</span>
          </div>
          <div style={{ height: 10, borderRadius: 6, background: "var(--line)", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${job.progress * 100}%`, background: "linear-gradient(90deg, var(--accent), var(--accent-2))", transition: "width .4s" }} />
          </div>
        </section>
      )}

      {/* ---- LIBRARY ---- */}
      {job && job.status === "done" && job.clips.length > 0 && (
        <section style={{ marginTop: 36 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
            <h2 style={{ fontSize: 22, margin: 0 }}>
              {job.clips.length} clip siap <span style={{ color: "var(--ok)" }}>✓</span>
            </h2>
            <a
              href={`/api/jobs/${job.job_id}/zip`}
              style={{ fontSize: 14, fontWeight: 600, color: "#fff", background: "var(--accent)", padding: "10px 18px", borderRadius: 10, textDecoration: "none" }}
            >
              Unduh semua (ZIP)
            </a>
          </div>

          <div style={{ display: "grid", gap: 20 }}>
            {job.clips.map((c) => (
              <article key={c.index} style={{ border: "1px solid var(--line)", borderRadius: 14, background: "var(--panel)", overflow: "hidden", display: "flex", flexDirection: "column" }}>
                {/* PREVIEW VIDEO — bisa langsung diputar sebelum diunduh */}
                <video
                  controls
                  preload="metadata"
                  src={c.download_url}
                  poster={`${c.download_url.replace(/[^/]+$/, "")}thumb.jpg`}
                  style={{ width: "100%", maxHeight: 480, background: "#000", display: "block" }}
                />
                <div style={{ padding: "18px 20px" }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "baseline", marginBottom: 8 }}>
                    <span style={{ fontFamily: "monospace", color: "var(--accent)", fontWeight: 700 }}>#{c.index}</span>
                    <h3 style={{ margin: 0, fontSize: 17, flex: 1 }}>{c.title}</h3>
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>{fmt(c.start_time)} → {fmt(c.end_time)} · {c.duration}s</span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                    <span style={{ fontWeight: 800, fontSize: 20, color: scoreColor(c.viral_score) }}>{c.viral_score}</span>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>/10 viral</span>
                  </div>

                  <div style={{ marginBottom: 12 }}>
                    <ScoreBar label="Hook" value={c.scores.hook} />
                    <ScoreBar label="Payoff" value={c.scores.payoff} />
                    <ScoreBar label="Emosi" value={c.scores.emotion} />
                    <ScoreBar label="Quotable" value={c.scores.quotability} />
                    <ScoreBar label="Energi" value={c.scores.energy} />
                  </div>

                  <p style={{ color: "var(--muted)", fontSize: 13, margin: "0 0 12px" }}>{c.reason}</p>

                  {c.caption && (
                    <div style={{ border: "1px dashed var(--line)", borderRadius: 10, padding: "10px 12px", marginBottom: 10 }}>
                      <p style={{ margin: "0 0 8px", fontSize: 14 }}>{c.caption}</p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {c.hashtags.map((h) => (
                          <span key={h} style={{ fontSize: 12, color: "var(--accent-2)", background: "var(--bg)", padding: "2px 8px", borderRadius: 999 }}>#{h}</span>
                        ))}
                      </div>
                      <button
                        onClick={() => copy(`${c.caption}\n\n${c.hashtags.map((h) => `#${h}`).join(" ")}`, `cap-${c.index}`)}
                        style={{ marginTop: 10, fontSize: 12, background: "transparent", border: "1px solid var(--line)", color: "var(--ink)", padding: "6px 12px", borderRadius: 8, cursor: "pointer" }}
                      >
                        {copied === `cap-${c.index}` ? "Tersalin ✓" : "Salin caption + hashtag"}
                      </button>
                    </div>
                  )}

                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <a href={c.download_url} download={c.filename} style={{ fontSize: 14, fontWeight: 600, color: "#fff", background: "var(--accent)", padding: "10px 18px", borderRadius: 10, textDecoration: "none" }}>
                      Unduh MP4
                    </a>
                    {c.srt_url && (
                      <a href={c.srt_url} download={`${c.filename.replace(".mp4", "")}.srt`} style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", border: "1px solid var(--line)", padding: "10px 18px", borderRadius: 10, textDecoration: "none" }}>
                        Unduh SRT
                      </a>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {job && job.status === "done" && job.clips.length === 0 && (
        <p style={{ marginTop: 32, color: "var(--muted)" }}>Tidak ada momen yang lolos quality gate. Coba video lain.</p>
      )}
    </main>
  );
}
