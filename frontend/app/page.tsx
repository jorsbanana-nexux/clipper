"use client";

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

const STYLES = [
  { id: "mrbeast", label: "MrBeast — pop biru elektrik" },
  { id: "hormozi", label: "Hormozi — besar hijau" },
  { id: "karaoke", label: "Karaoke — isi progresif" },
  { id: "minimal", label: "Minimal — bersih" },
  { id: "none", label: "Tanpa subtitle" },
];

const ASPECTS = ["9:16", "1:1", "4:5"];

const inputStyle: React.CSSProperties = {
  padding: "14px 16px", borderRadius: 10, border: "1px solid var(--line)",
  background: "var(--panel)", color: "var(--ink)", fontSize: 15, outline: "none",
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
  const [keywords, setKeywords] = useState("");
  const [instruction, setInstruction] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false); // Topik/Instruksi tersembunyi by default
  const [style, setStyle] = useState("mrbeast");
  const [aspect, setAspect] = useState("9:16");
  const [maxClips, setMaxClips] = useState(8);
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
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(), max_clips: maxClips, mode: "podcast",
          keywords: keywords.trim(), instruction: instruction.trim(),
          subtitle_style: style, aspect,
        }),
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

  function copy(text: string, key: string) {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(""), 1500);
  }

  const pct = job ? Math.round(job.progress * 100) : 0;

  return (
    <main style={{ maxWidth: 1040, margin: "0 auto", padding: "48px 24px 96px" }}>
      <header style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--accent)", fontFamily: "monospace" }}>AI Podcast Clipper</div>
        <h1 style={{ fontSize: 56, lineHeight: 0.95, margin: "10px 0 8px", letterSpacing: "-0.02em" }}>
          CLIPPER<span style={{ color: "var(--accent)" }}>.</span>
        </h1>
        <p style={{ color: "var(--muted)", margin: 0, maxWidth: 620 }}>
          Tempel link podcast &mdash; AI menemukan momen viral, memotong hanya bagian terbaik, membingkai ulang ke {aspect} dengan subtitle word-by-word, dan menyiapkan caption + hashtag siap posting.
        </p>
      </header>

      <form onSubmit={submit} style={{ display: "grid", gap: 10, marginBottom: 28 }}>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://youtube.com/watch?v=...  (YouTube, TikTok, Instagram)"
          style={{ ...inputStyle, flex: "1 1 420px" }}
        />
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <select value={style} onChange={(e) => setStyle(e.target.value)} style={{ ...inputStyle, flex: 1, minWidth: 180 }}>
            {STYLES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
          <select value={aspect} onChange={(e) => setAspect(e.target.value)} style={{ ...inputStyle, width: 90 }}>
            {ASPECTS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={maxClips} onChange={(e) => setMaxClips(Number(e.target.value))} style={{ ...inputStyle, width: 110 }}>
            {[4, 5, 6, 7, 8, 9, 10].map((n) => <option key={n} value={n}>{n} clips</option>)}
          </select>
          <button disabled={busy} type="submit"
            style={{ padding: "14px 22px", borderRadius: 10, border: "none", background: busy ? "var(--line)" : "var(--accent)", color: "#0b0d10", fontWeight: 700, fontSize: 15, cursor: busy ? "default" : "pointer", whiteSpace: "nowrap" }}>
            {busy ? "Processing..." : "Generate clips"}
          </button>
        </div>

        {/* "Human steer": pilih topik/instruksi editor secara opsional. Disembunyikan
            secara default (klik untuk buka) supaya tampilan utama tetap cuma
            URL + jumlah clip seperti yang diminta -- fiturnya tetap ada bagi
            yang mau, tidak dihapus, cuma tidak lagi memenuhi tampilan utama. */}
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          style={{ justifySelf: "start", background: "none", border: "none", color: "var(--muted)", fontSize: 12, cursor: "pointer", padding: "2px 0", textDecoration: "underline" }}>
          {showAdvanced ? "▾ Sembunyikan opsi lanjutan" : "▸ Opsi lanjutan (arahkan AI ke topik tertentu)"}
        </button>
        {showAdvanced && (
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr" }}>
            <input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="Topik yang kamu mau (opsional): mis. 'insight uang, cerita lucu'"
              style={inputStyle}
              title="Steer the AI: moments matching these topics get priority"
            />
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Instruksi editor (opsional): mis. 'cari yang kontras/debat'"
              style={inputStyle}
            />
          </div>
        )}
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
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
            <span style={{ color: "var(--ok)", fontWeight: 700 }}>{job.clips.length} clips siap diunduh</span>
            <a href={`/api/jobs/${job.job_id}/zip`}
              style={{ padding: "10px 16px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--line)", color: "var(--ink)", fontWeight: 700, fontSize: 13, textDecoration: "none" }}>
              ⬇ Download semua (ZIP)
            </a>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
            {job.clips.map((c) => (
              <div key={c.index} style={{ borderRadius: 12, background: "var(--panel)", border: "1px solid var(--line)", overflow: "hidden", display: "flex", flexDirection: "column" }}>
                <video src={c.download_url} controls preload="metadata" style={{ width: "100%", aspectRatio: aspect === "1:1" ? "1/1" : aspect === "4:5" ? "4/5" : "9/16", background: "#000", display: "block" }} />
                <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>#{c.index} &middot; {c.title}</span>
                    <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--accent-2)" }}>★ {c.viral_score}/10</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>{fmt(c.start_time)} &ndash; {fmt(c.end_time)} &middot; {c.duration}s</div>

                  {c.scores && (
                    <div style={{ padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--line)" }}>
                      <ScoreBar label="Hook" value={c.scores.hook} />
                      <ScoreBar label="Payoff" value={c.scores.payoff} />
                      <ScoreBar label="Emosi" value={c.scores.emotion} />
                      <ScoreBar label="Quotable" value={c.scores.quotability} />
                      <ScoreBar label="Energi" value={c.scores.energy} />
                    </div>
                  )}

                  {c.reason && <div style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>&ldquo;{c.reason}&rdquo;</div>}

                  {c.caption && (
                    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                      <div style={{ flex: 1, fontSize: 12, padding: "8px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--line)", color: "var(--ink)" }}>
                        {c.caption}
                        {c.hashtags?.length > 0 && (
                          <div style={{ marginTop: 4, color: "var(--accent-2)" }}>
                            {c.hashtags.map((h) => `#${h}`).join(" ")}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => copy(`${c.caption}\n\n${(c.hashtags || []).map((h) => `#${h}`).join(" ")}`, `cap-${c.index}`)}
                        style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 11, cursor: "pointer", whiteSpace: "nowrap" }}>
                        {copied === `cap-${c.index}` ? "✓ Copied" : "Copy caption"}
                      </button>
                    </div>
                  )}

                  <a href={c.download_url} download={c.filename}
                    style={{ marginTop: "auto", display: "block", textAlign: "center", padding: "10px", borderRadius: 8, background: "var(--accent)", color: "#0b0d10", fontWeight: 700, fontSize: 13, textDecoration: "none" }}>
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
