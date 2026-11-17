/* ClipForge front-end: create jobs, poll progress, preview clips, publish via browser. */

const $ = (sel, el = document) => el.querySelector(sel);
const jobsEl = $("#jobs");
const jobTpl = $("#job-tpl");
const clipTpl = $("#clip-tpl");
const jobEls = new Map();      // job id -> element
const clipState = new Map();   // `${job}:${clip}` -> {platform, edits:{platform: text}}
const RUNNING = new Set(["queued", "downloading", "transcribing", "highlighting", "rendering", "packaging"]);

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

$("#job-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#go");
  btn.disabled = true;
  try {
    const body = {
      source: $("#source").value.trim(),
      style: $("#style").value,
      clip_count: parseInt($("#clip_count").value, 10) || 5,
      reframe: $("#reframe").value || null,
    };
    const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
    renderJob(job, true);
    $("#source").value = "";
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
  }
});

function fmtTime(s) {
  s = Math.max(0, Math.round(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function renderJob(job, prepend = false) {
  let el = jobEls.get(job.id);
  if (!el) {
    el = jobTpl.content.firstElementChild.cloneNode(true);
    el.dataset.id = job.id;
    jobEls.set(job.id, el);
    prepend ? jobsEl.prepend(el) : jobsEl.append(el);
  }
  $(".job-title", el).textContent = job.video ? job.video.title : "Preparing…";
  $(".job-source", el).textContent = `${job.source} · ${job.style} · ${job.clip_count} clips`;
  const badge = $(".status", el);
  badge.textContent = job.status;
  badge.className = "badge status " + (job.status === "done" ? "done" : job.status === "error" ? "error" : "running");
  $(".bar", el).style.width = `${Math.round(job.progress * 100)}%`;
  $(".job-message", el).textContent = job.message || "";

  const clipsEl = $(".clips", el);
  for (const clip of job.clips || []) {
    let cel = clipsEl.querySelector(`[data-index="${clip.index}"]`);
    if (!cel) {
      cel = clipTpl.content.firstElementChild.cloneNode(true);
      cel.dataset.index = clip.index;
      clipsEl.append(cel);
      $("video", cel).src = clip.video_url;
      if (clip.thumb_url) $("video", cel).poster = clip.thumb_url;
      wireClip(job, clip, cel);
    }
    updateClip(job, clip, cel);
  }
}

function wireClip(job, clip, cel) {
  const key = `${job.id}:${clip.index}`;
  clipState.set(key, { platform: "tiktok", edits: {} });
  const ta = $(".caption", cel);
  ta.addEventListener("input", () => { clipState.get(key).edits[clipState.get(key).platform] = ta.value; });
  $(".copy", cel).addEventListener("click", async () => {
    await navigator.clipboard.writeText(ta.value);
    flash(cel, "Caption copied ✓");
  });
  $(".post", cel).addEventListener("click", async () => {
    const st = clipState.get(key);
    const btn = $(".post", cel);
    btn.disabled = true;
    try {
      const r = await api(`/api/jobs/${job.id}/clips/${clip.index}/publish`, {
        method: "POST",
        body: JSON.stringify({ platform: st.platform, caption: ta.value }),
      });
      pollPublish(r.session.id, cel);
    } catch (err) {
      flash(cel, "Error: " + err.message);
    } finally {
      btn.disabled = false;
    }
  });
}

function updateClip(job, clip, cel) {
  const key = `${job.id}:${clip.index}`;
  const st = clipState.get(key);
  const h = clip.highlight;
  $(".clip-title", cel).textContent = `${clip.index}. ${h.title}`;
  $(".clip-meta", cel).textContent = `${fmtTime(h.start)} → ${fmtTime(h.end)} · ${Math.round(h.end - h.start)}s · ${h.mood}`;
  $(".clip-reason", cel).textContent = h.reason || "";
  $(".score", cel).textContent = `🔥 ${Math.round(h.score)}`;
  $(".download", cel).href = `/api/jobs/${job.id}/clips/${clip.index}/download`;

  const tabs = $(".tabs", cel);
  const posts = clip.posts || {};
  if (Object.keys(posts).length && !tabs.children.length) {
    for (const id of ["tiktok", "youtube", "instagram", "facebook", "x"]) {
      const meta = window.PLATFORMS[id];
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = meta.name;
      b.dataset.platform = id;
      b.addEventListener("click", () => { st.platform = id; showPlatform(clip, cel); });
      tabs.append(b);
    }
    showPlatform(clip, cel);
  }
  cel._clip = clip;
}

function showPlatform(clip, cel) {
  const jobId = cel.closest(".job").dataset.id;
  const st = clipState.get(`${jobId}:${clip.index}`);
  const ta = $(".caption", cel);
  for (const b of $(".tabs", cel).children) b.classList.toggle("active", b.dataset.platform === st.platform);
  const post = (clip.posts || {})[st.platform];
  ta.value = st.edits[st.platform] ?? (post ? post.full_caption : "");
  $(".post", cel).textContent = `Open in ${window.PLATFORMS[st.platform].name} →`;
}

function flash(cel, msg) {
  const p = $(".publish-status", cel);
  p.textContent = msg;
  setTimeout(() => { if (p.textContent === msg) p.textContent = ""; }, 4000);
}

async function pollPublish(sid, cel) {
  const p = $(".publish-status", cel);
  for (let i = 0; i < 2000; i++) {
    let s;
    try { s = await api(`/api/publish/${sid}`); } catch { break; }
    p.textContent = `${s.platform}: ${s.message}`;
    if (["error", "closed", "submitted"].includes(s.status)) break;
    await new Promise(r => setTimeout(r, 1500));
  }
}

async function refresh() {
  try {
    const jobs = await api("/api/jobs");
    for (const job of jobs.reverse()) renderJob(job);
    const anyRunning = jobs.some(j => RUNNING.has(j.status));
    setTimeout(refresh, anyRunning ? 1200 : 5000);
  } catch {
    setTimeout(refresh, 3000);
  }
}
refresh();
