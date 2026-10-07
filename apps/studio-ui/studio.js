/* Shunya Studios - 2.5D studio client.
 *
 * This page is a projection of backend state (spec 12): it loads /studio/state, then
 * applies events from /ws/studio. Nothing here invents activity. Avatar movement is
 * animated locally at a fixed walking speed, so it never depends on LLM latency (spec 43).
 * All text from the backend is inserted with textContent - agent output is untrusted.
 */
(() => {
  "use strict";

  // ------------------------------------------------------------------ helpers
  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  };
  // When the server requires a token it is kept as a cookie, so images and the WebSocket carry it too.
  const askToken = () => {
    const token = prompt("This studio requires an access token (SHUNYA_API_TOKEN):");
    if (!token) return false;
    document.cookie = `shunya_token=${encodeURIComponent(token.trim())}; path=/; SameSite=Strict; max-age=2592000`;
    return true;
  };
  const api = async (path, opts) => {
    let r = await fetch(path, opts);
    if (r.status === 401 && askToken()) r = await fetch(path, opts);
    if (!r.ok) {
      let detail = r.statusText;
      try { detail = (await r.json()).detail || detail; } catch (_) { /* not json */ }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const type = r.headers.get("content-type") || "";
    return type.includes("json") ? r.json() : r.text();
  };
  const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const money = (v) => "$" + Number(v || 0).toFixed(v >= 1 ? 2 : 4);
  const elapsed = (iso) => {
    const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
    return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((n) => String(n).padStart(2, "0")).join(":");
  };

  // ------------------------------------------------------------------ office layout (grid units)
  const ROOMS = {
    executive:     { x: 1,  y: 1,  w: 8,  h: 5, label: "EXECUTIVE",        color: "#2b2640" },
    design:        { x: 1,  y: 7,  w: 8,  h: 7, label: "DESIGN",           color: "#3a2436" },
    art:           { x: 1,  y: 15, w: 8,  h: 7, label: "ART",              color: "#3b2f1f" },
    meeting:       { x: 11, y: 1,  w: 8,  h: 6, label: "MEETING ROOM",     color: "#22303a" },
    engineering:   { x: 11, y: 8,  w: 11, h: 8, label: "ENGINEERING",      color: "#1f2b45" },
    qa:            { x: 21, y: 1,  w: 9,  h: 6, label: "QA LAB",           color: "#1d3a2d" },
    devops:        { x: 24, y: 8,  w: 6,  h: 6, label: "BUILD / SERVERS",  color: "#3a2424" },
    environment:   { x: 11, y: 17, w: 7,  h: 5, label: "ENVIRONMENT",      color: "#2b3a20" },
    animation:     { x: 19, y: 17, w: 5,  h: 5, label: "ANIMATION",        color: "#33254a" },
    audio:         { x: 25, y: 15, w: 5,  h: 3.5, label: "AUDIO",          color: "#1f3a3a" },
    documentation: { x: 25, y: 19, w: 5,  h: 3, label: "DOCS",             color: "#2c2f36" },
  };
  const GRID = { w: 31, h: 23 };
  const TW = 56, TH = 28;
  const STATE_ICON = {
    IDLE: "☕", UNDERSTANDING: "💭", PLANNING: "📋", READING: "📖", SEARCHING: "🔍", CODING: "⌨️", COMPILING: "⚙️",
    TESTING: "🧪", DEBUGGING: "🐞", REVIEWING: "🔎", MEETING: "💬", REPORTING: "📝", BLOCKED: "❗",
    WAITING_APPROVAL: "🔔", FAILED: "✖", SUCCESS: "✔",
  };
  const STATE_COLOR = { BLOCKED: "#ef5d5d", FAILED: "#ef5d5d", WAITING_APPROVAL: "#f5b84a", SUCCESS: "#3ecf8e", MEETING: "#49b8d6" };

  const deskOf = (a) => {
    const key = ROOMS[a.avatar.room] ? a.avatar.room : "engineering", room = ROOMS[key];
    const count = Math.max(1, [...S.agents.values()].filter((x) => (ROOMS[x.avatar.room] ? x.avatar.room : "engineering") === key).length);
    const cols = Math.max(1, Math.floor((room.w - 0.6) / 2.2));
    const rows = Math.ceil(count / cols);
    const dy = rows > 1 ? Math.min(2.4, (room.h - 2.4) / (rows - 1)) : 0;
    const i = a.avatar.desk || 0;
    return { x: room.x + 1.3 + (i % cols) * 2.2, y: room.y + 1.6 + Math.floor(i / cols) * dy };
  };
  const meetingSeat = (i, n) => {
    const r = ROOMS.meeting, cx = r.x + r.w / 2, cy = r.y + r.h / 2 + 0.2;
    const ang = (i / Math.max(n, 3)) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(ang) * 2.5, y: cy + Math.sin(ang) * 1.7 };
  };
  const slot = (room, i, cols = 3) => ({ x: room.x + room.w - 1.4 - (i % cols) * 1.6, y: room.y + room.h - 1.3 - Math.floor(i / cols) * 1.5 });

  // ------------------------------------------------------------------ state
  const S = {
    state: null, agents: new Map(), sprites: new Map(), meetings: new Map(), lastSeq: 0, selected: null,
    tab: "tasks", empTab: "TASK", empData: null, feed: [], ws: null, refreshTimer: null, hover: null,
  };

  function targetOf(a) {
    const loc = a.location || "desk";
    if (a.state === "OFFLINE") return deskOf(a);
    if (loc.startsWith("meeting")) {
      let i = 0, n = 3;
      for (const m of S.meetings.values()) {
        const idx = m.participants.indexOf(a.id);
        if (idx >= 0) { i = idx; n = m.participants.length; }
      }
      return meetingSeat(i, n);
    }
    const order = [...S.agents.values()].filter((x) => x.enabled).map((x) => x.id).indexOf(a.id);
    if (loc === "qa_lab") return a.avatar.room === "qa" ? deskOf(a) : slot(ROOMS.qa, order % 6);
    if (loc === "server_room") return slot(ROOMS.devops, 0, 2);
    if (loc === "whiteboard") {
      const room = ROOMS[a.avatar.room] || ROOMS.engineering;
      return { x: room.x + 0.9 + ((a.avatar.desk || 0) % 3) * 0.9, y: room.y + 0.75 };
    }
    return deskOf(a);
  }

  function syncSprites() {
    for (const a of S.agents.values()) {
      let sp = S.sprites.get(a.id);
      const t = targetOf(a);
      if (!sp) { sp = { x: t.x, y: t.y, tx: t.x, ty: t.y, phase: Math.random() * 6, flash: 0 }; S.sprites.set(a.id, sp); }
      sp.tx = t.x; sp.ty = t.y;
    }
  }

  // ------------------------------------------------------------------ canvas rendering
  const canvas = $("#office"), ctx = canvas.getContext("2d");
  let view = { scale: 1, ox: 0, oy: 0, w: 0, h: 0 };

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(rect.width * dpr); canvas.height = Math.floor(rect.height * dpr);
    const worldW = (GRID.w + GRID.h) * TW / 2, worldH = (GRID.w + GRID.h) * TH / 2 + 90;
    const scale = Math.min(rect.width / worldW, (rect.height - 70) / worldH) * 0.98;
    view = { scale, w: rect.width, h: rect.height, dpr,
             ox: rect.width / 2 - ((GRID.w - GRID.h) * TW / 4) * scale, oy: (rect.height - 70 - worldH * scale) / 2 + 70 * scale };
  }
  const iso = (gx, gy, z = 0) => ({ x: view.ox + (gx - gy) * TW / 2 * view.scale, y: view.oy + ((gx + gy) * TH / 2 - z) * view.scale });

  function poly(points, fill, stroke) {
    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
  }
  const shade = (hex, f) => {
    const n = parseInt(hex.slice(1), 16);
    const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.max(0, Math.min(255, Math.round(v * f))));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  };
  function box(gx, gy, w, d, h, color, z0 = 0) {
    const a = iso(gx, gy, z0 + h), b = iso(gx + w, gy, z0 + h), c = iso(gx + w, gy + d, z0 + h), e = iso(gx, gy + d, z0 + h);
    const c0 = iso(gx + w, gy + d, z0), e0 = iso(gx, gy + d, z0), b0 = iso(gx + w, gy, z0);
    poly([e, c, c0, e0], shade(color, 0.7));
    poly([b, c, c0, b0], shade(color, 0.5));
    poly([a, b, c, e], color);
  }
  function text(str, p, size, color, align = "center", weight = "600", scale = view.scale) {
    ctx.font = `${weight} ${Math.max(9, size * scale)}px "Segoe UI", system-ui, sans-serif`;
    ctx.textAlign = align; ctx.textBaseline = "middle"; ctx.fillStyle = color;
    ctx.fillText(str, p.x, p.y);
  }

  function drawRoom(key, r) {
    const p = [iso(r.x, r.y), iso(r.x + r.w, r.y), iso(r.x + r.w, r.y + r.h), iso(r.x, r.y + r.h)];
    poly(p, r.color, "#3b445a");
    // low back walls
    const wall = 26;
    poly([iso(r.x, r.y), iso(r.x + r.w, r.y), iso(r.x + r.w, r.y, wall), iso(r.x, r.y, wall)], shade(r.color, 1.45));
    poly([iso(r.x, r.y), iso(r.x, r.y + r.h), iso(r.x, r.y + r.h, wall), iso(r.x, r.y, wall)], shade(r.color, 1.2));
    text(r.label, iso(r.x + r.w / 2, r.y + r.h - 0.45), 11, "#ffffff55");
    if (key !== "meeting" && key !== "devops") { // whiteboard on the back wall
      poly([iso(r.x + 0.5, r.y, 6), iso(r.x + 3.2, r.y, 6), iso(r.x + 3.2, r.y, 22), iso(r.x + 0.5, r.y, 22)], "#dfe6f2cc");
    }
  }

  function drawables(now) {
    const items = [];
    // meeting table
    const m = ROOMS.meeting;
    items.push({ d: m.x + m.w / 2 + m.y + m.h / 2, draw: () => box(m.x + m.w / 2 - 1.6, m.y + m.h / 2 - 0.7, 3.2, 1.6, 12, "#6b5a45") });
    // server racks
    const dv = ROOMS.devops;
    const building = [...S.agents.values()].some((a) => a.state === "COMPILING");
    for (let i = 0; i < 4; i++) {
      const gx = dv.x + 0.6 + i * 1.25, gy = dv.y + 0.5;
      items.push({ d: gx + gy + 0.4, draw: () => {
        box(gx, gy, 0.9, 0.8, 44, "#2a3140");
        for (let k = 0; k < 5; k++) {
          const on = building ? Math.sin(now / 90 + i * 2 + k * 1.7) > 0 : (i + k) % 3 === 0;
          const led = iso(gx + 0.15 + (k % 2) * 0.3, gy + 0.8, 10 + k * 7);
          ctx.fillStyle = on ? (building ? "#f5b84a" : "#3ecf8e") : "#16202b";
          ctx.fillRect(led.x, led.y, 3 * view.scale, 2 * view.scale);
        }
      } });
    }
    // desks
    for (const a of S.agents.values()) {
      const d = deskOf(a), sp = S.sprites.get(a.id);
      const atDesk = sp && Math.hypot(sp.x - d.x, sp.y - d.y) < 0.2 && a.state !== "OFFLINE";
      items.push({ d: d.x + d.y - 0.75, draw: () => {
        box(d.x - 0.55, d.y - 1.0, 1.1, 0.55, 13, a.enabled ? "#7b6a55" : "#4a4f5a");
        const glow = atDesk && ["CODING", "DEBUGGING", "READING", "SEARCHING", "REVIEWING", "COMPILING", "REPORTING", "UNDERSTANDING"].includes(a.state);
        box(d.x - 0.28, d.y - 0.95, 0.56, 0.08, 11, glow ? "#9fd0ff" : "#2c3442", 13);
      } });
    }
    // employees (an OFFLINE role is an empty desk - spec 12)
    for (const a of S.agents.values()) {
      if (a.state === "OFFLINE") continue;
      const sp = S.sprites.get(a.id);
      if (sp) items.push({ d: sp.x + sp.y, draw: () => drawEmployee(a, sp, now) });
    }
    return items.sort((p, q) => p.d - q.d);
  }

  function drawEmployee(a, sp, now) {
    const moving = Math.hypot(sp.tx - sp.x, sp.ty - sp.y) > 0.02;
    const bob = moving ? Math.abs(Math.sin(now / 110 + sp.phase)) * 3 : (a.state === "CODING" || a.state === "DEBUGGING" ? Math.sin(now / 160 + sp.phase) * 0.8 : 0);
    // people are drawn at a minimum size so they stay readable and clickable in a small window
    const p = iso(sp.x, sp.y, bob), s = Math.max(view.scale, 0.62), col = a.avatar.color || "#5b8cff";
    ctx.fillStyle = "#0006";
    ctx.beginPath(); ctx.ellipse(iso(sp.x, sp.y).x, iso(sp.x, sp.y).y, 11 * s, 5 * s, 0, 0, Math.PI * 2); ctx.fill();
    if (S.selected === a.id) {
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(iso(sp.x, sp.y).x, iso(sp.x, sp.y).y, 15 * s, 7 * s, 0, 0, Math.PI * 2); ctx.stroke();
    }
    // body
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.roundRect(p.x - 8 * s, p.y - 30 * s, 16 * s, 26 * s, 7 * s); ctx.fill();
    ctx.fillStyle = shade(col, 0.7);
    ctx.fillRect(p.x - 8 * s, p.y - 12 * s, 16 * s, 3 * s);
    // head
    ctx.fillStyle = "#f1c9a5";
    ctx.beginPath(); ctx.arc(p.x, p.y - 37 * s, 8 * s, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = shade(col, 0.45);
    ctx.beginPath(); ctx.arc(p.x, p.y - 39.5 * s, 8 * s, Math.PI, Math.PI * 2); ctx.fill();
    // name
    text(a.name, { x: p.x, y: p.y + 9 * s }, 11, "#e6e9f0", "center", "600", s);
    // state bubble
    const icon = a.paused ? "⏸" : STATE_ICON[a.state];
    if (icon && !(a.state === "IDLE" && !a.paused && moving)) {
      const pulse = ["BLOCKED", "WAITING_APPROVAL", "FAILED"].includes(a.state) ? 1 + Math.sin(now / 200) * 0.12 : 1;
      const by = p.y - 58 * s, r = 11 * s * pulse;
      ctx.fillStyle = STATE_COLOR[a.state] || "#141922"; ctx.strokeStyle = "#ffffff30"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x, by, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.save();
      if (a.state === "COMPILING") { ctx.translate(p.x, by); ctx.rotate(now / 400); ctx.translate(-p.x, -by); }
      text(icon, { x: p.x, y: by + 1 }, 12, "#fff", "center", "400", s);
      ctx.restore();
      if (a.state === "CODING" || a.state === "DEBUGGING") {
        const dots = ".".repeat(1 + Math.floor(now / 300) % 3);
        text(dots, { x: p.x + 16 * s, y: by }, 12, "#9fd0ff", "left", "600", s);
      }
    }
    sp.screen = { x: p.x, y: p.y - 28 * s, r: Math.max(18, 30 * s) };
  }

  function drawSign() {
    const st = S.state && S.state.stats;
    if (!st) return;
    const dv = ROOMS.devops, p = iso(dv.x + dv.w / 2, dv.y, 40);
    const building = [...S.agents.values()].some((a) => a.state === "COMPILING");
    const label = building ? "BUILD: RUNNING" : `BUILD: ${st.build || "—"}`;
    const color = building ? "#f5b84a" : st.build === "PASSED" ? "#3ecf8e" : st.build ? "#ef5d5d" : "#8a93a6";
    text(label, p, 12, color);
  }

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    for (const sp of S.sprites.values()) { // walk: along x, then along y, at 5 tiles/second
      const step = 5 * dt;
      const dx = sp.tx - sp.x, dy = sp.ty - sp.y;
      if (Math.abs(dx) > 0.001) sp.x += Math.sign(dx) * Math.min(Math.abs(dx), step);
      else if (Math.abs(dy) > 0.001) sp.y += Math.sign(dy) * Math.min(Math.abs(dy), step);
    }
    ctx.setTransform(view.dpr || 1, 0, 0, view.dpr || 1, 0, 0);
    ctx.clearRect(0, 0, view.w, view.h);
    poly([iso(0, 0), iso(GRID.w, 0), iso(GRID.w, GRID.h), iso(0, GRID.h)], "#151a24", "#262d3d");
    for (const [key, r] of Object.entries(ROOMS)) drawRoom(key, r);
    for (const item of drawables(now)) item.draw();
    drawSign();
    requestAnimationFrame(frame);
  }

  function pick(ev) {
    const rect = canvas.getBoundingClientRect(), x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    let best = null, bestD = 1e9;
    for (const [id, sp] of S.sprites) {
      const a = S.agents.get(id);
      if (!sp.screen || !a || a.state === "OFFLINE") continue;
      const d = Math.hypot(sp.screen.x - x, sp.screen.y - y);
      if (d < sp.screen.r && d < bestD) { best = id; bestD = d; }
    }
    return { id: best, x, y };
  }
  canvas.addEventListener("mousemove", (ev) => {
    const { id, x, y } = pick(ev), tip = $("#tooltip");
    canvas.style.cursor = id ? "pointer" : "default";
    if (!id) { tip.hidden = true; return; }
    const a = S.agents.get(id);
    tip.replaceChildren(el("div", "t-name", `${a.name} · ${a.role}`), el("div", "", `${a.state}${a.paused ? " (paused)" : ""}${a.task_id ? " · " + a.task_id : ""}`));
    if (a.current_action) tip.append(el("div", "muted", a.current_action));
    tip.style.left = x + 14 + "px"; tip.style.top = y + 10 + "px"; tip.hidden = false;
  });
  canvas.addEventListener("mouseleave", () => { $("#tooltip").hidden = true; });
  canvas.addEventListener("click", (ev) => {
    const { id } = pick(ev);
    if (id) { S.selected = id; setTab("employee"); loadEmployee(); }
  });

  // ------------------------------------------------------------------ top bar
  function renderTop() {
    const st = S.state; if (!st) return;
    $("#project-line").textContent = `PROJECT: ${(st.project && st.project.name || "SHUNYA").toUpperCase()}  ·  agents: ${st.provider}  ·  unreal: ${st.unreal_available ? "connected toolchain" : "not installed"}`;
    const e = st.epic;
    $("#epic-title").textContent = e ? `${e.id} · ${e.title} — ${e.status} · ${e.done}/${e.tasks} tasks` : "No active feature";
    $("#epic-fill").style.width = (e ? e.progress : 0) + "%";
    const s = st.stats, chips = $("#chips"); chips.replaceChildren();
    const chip = (label, value, cls) => { const c = el("span", "chip " + (cls || "")); c.append(label + " ", el("b", "", value)); chips.append(c); };
    chip("Agents", s.agents); chip("Working", s.working); chip("Meeting", s.meeting); chip("Testing", s.testing);
    chip("Blocked", s.blocked, s.blocked ? "bad" : "");
    chip("Build", s.build || "—", s.build === "PASSED" ? "good" : s.build ? "bad" : "");
    chip("Tests", s.tests ? `${s.tests.passed} / ${s.tests.total}` : "—", s.tests ? (s.tests.status === "PASSED" ? "good" : "bad") : "");
    chip("Open bugs", s.open_bugs, s.open_bugs ? "warn" : "");
    chip("Cost", money(s.cost_usd));
  }

  // ------------------------------------------------------------------ tasks panel
  const pill = (status) => el("span", "pill " + status, String(status).replace(/_/g, " "));
  const button = (label, cls, fn) => {
    const b = el("button", "btn small " + (cls || "ghost"), label);
    b.addEventListener("click", async (ev) => {
      ev.stopPropagation(); b.disabled = true;
      try { await fn(); } catch (e) { alert(e.message); } finally { b.disabled = false; refreshSoon(0); }
    });
    return b;
  };
  const agentName = (id) => (S.agents.get(id) || {}).name || id || "—";

  function taskActions(t) {
    const box = el("div", "actions");
    const live = !["DONE", "CANCELLED"].includes(t.status);
    if (live && t.status !== "BLOCKED") box.append(t.paused ? button("Resume", "", () => post(`/tasks/${t.id}/resume`)) : button("Pause", "", () => post(`/tasks/${t.id}/pause`)));
    if (t.status === "BLOCKED") box.append(button("Retry", "", () => post(`/tasks/${t.id}/retry`, { note: prompt("Guidance for the team (optional):") || "" })));
    if (live) box.append(button("Cancel", "", () => confirm(`Cancel ${t.id}?`) ? post(`/tasks/${t.id}/cancel`) : null));
    box.append(button("Details", "", () => showTask(t.id)));
    return box;
  }

  function renderTasks() {
    const panel = $("#panel-tasks"); panel.replaceChildren();
    const tasks = (S.state && S.state.tasks) || [];
    const features = tasks.filter((t) => t.type === "FEATURE" || t.type === "EPIC").reverse();
    if (!features.length) { panel.append(el("p", "muted", "No work yet. Type a feature request below — the Director, Producer, a programmer, the reviewer, the Build Engineer and QA will take it from there, and you approve the merge.")); return; }
    for (const f of features) {
      const card = el("div", "card");
      const head = el("div", "row between"); head.append(el("span", "id", f.id), pill(f.paused ? "PAUSED" : f.status));
      card.append(head, el("h4", "", f.title));
      const kids = tasks.filter((t) => t.parent_id === f.id);
      if (kids.length) card.append(el("div", "sub", `${kids.filter((k) => k.status === "DONE").length} of ${kids.length} tasks done`));
      if (f.result && f.result.plan_summary) card.append(el("div", "sub", f.result.plan_summary));
      if (f.result && f.result.blocked_reason && f.status === "BLOCKED") card.append(el("div", "reason", f.result.blocked_reason));
      for (const c of tasks.filter((t) => t.parent_id === f.id)) {
        const row = el("div", "child");
        const h = el("div", "row between"); h.append(el("span", "id", `${c.id} · ${c.priority}`), pill(c.status));
        row.append(h, el("div", "", c.title), el("div", "sub", `${c.track} · ${agentName(c.owner)}${c.owner ? "" : " (" + c.assignee_capability.replace(/_/g, " ") + ")"} · ${c.acceptance_criteria.length} criteria`));
        if (c.result && c.result.blocked_reason && c.status === "BLOCKED") row.append(el("div", "reason", c.result.blocked_reason));
        if (!["DONE", "PLANNED"].includes(c.status)) row.append(taskActions(c));
        else row.addEventListener("click", () => showTask(c.id));
        card.append(row);
      }
      const whole = el("div", "child"); whole.append(el("div", "sub", "Whole feature")); whole.append(taskActions(f));
      card.append(whole); panel.append(card);
    }
  }

  async function showTask(id) {
    const t = await api(`/tasks/${id}`), body = el("div");
    const kv = el("div", "kv");
    const add = (k, v) => kv.append(el("span", "", k), el("span", "", v));
    add("Status", t.status); add("Type", t.type); add("Owner", agentName(t.owner)); add("Branch", t.branch || "—");
    add("Trace", t.trace_id); add("Cost", `${money(t.cost_usd)} · ${t.llm_calls} LLM calls · ${t.tokens} tokens`);
    body.append(el("p", "", t.description), kv);
    if (t.acceptance_criteria.length) { body.append(el("h4", "", "Acceptance criteria")); const ul = el("ul"); t.acceptance_criteria.forEach((c) => ul.append(el("li", "", c))); body.append(ul); }
    if (t.feedback.length) { body.append(el("h4", "", "Open feedback")); body.append(el("pre", "block", t.feedback.join("\n"))); }
    body.append(el("h4", "", "History"));
    body.append(el("pre", "block", t.history.map((h) => `${hhmm(h.at)}  ${(h.from_status || "").padEnd(18)} → ${h.to_status.padEnd(18)} ${h.actor}  ${h.reason}`).join("\n")));
    if (t.builds.length) { body.append(el("h4", "", "Builds")); body.append(el("pre", "block", t.builds.map((b) => `${b.id}  ${b.status.padEnd(7)} ${b.agent_id}  ${b.duration_s}s  ${b.diagnostics.map((d) => `\n    ${d.file}(${d.line}): ${d.code} ${d.message}`).join("")}`).join("\n"))); }
    if (t.tests.length) { body.append(el("h4", "", "Test runs")); body.append(el("pre", "block", t.tests.map((r) => `${r.id}  ${r.status}  ${r.passed} passed / ${r.failed} failed  filter=${r.filter}${r.results.map((x) => `\n    [${x.result}] ${x.name} ${x.messages.join("; ")}`).join("")}`).join("\n"))); }
    const shots = t.artifacts.filter((a) => a.content_type === "image/png");
    if (shots.length) { body.append(el("h4", "", "Evidence")); shots.forEach((a) => body.append(evidenceImage(a.id))); }
    if (t.messages.length) { body.append(el("h4", "", "Structured messages")); body.append(el("pre", "block", t.messages.map((m) => `${hhmm(m.timestamp)} ${m.type}  ${m.sender} → ${m.receiver}: ${m.summary}`).join("\n"))); }
    if (t.artifacts.length) {
      body.append(el("h4", "", "Artifacts"));
      const ul = el("ul");
      t.artifacts.forEach((a) => { const li = el("li"); const link = el("a", "", `${a.type} v${a.version} — ${a.title}`); link.href = `/artifacts/${a.id}`; link.target = "_blank"; link.style.color = "#9fc0ff"; li.append(link); ul.append(li); });
      body.append(ul);
    }
    openModal(`${t.id} — ${t.title}`, body);
  }

  // ------------------------------------------------------------------ approvals panel
  function renderApprovals() {
    const panel = $("#panel-approvals"); panel.replaceChildren();
    const list = (S.state && S.state.approvals) || [];
    const badge = $("#approval-count"); badge.hidden = !list.length; badge.textContent = list.length;
    const policy = el("label", "policy");
    const box = el("input"); box.type = "checkbox"; box.checked = (S.state && S.state.auto_approve_max_risk) === "LOW";
    box.addEventListener("change", async () => { try { await post("/settings/approval-policy", { max_risk: box.checked ? "LOW" : "" }); } catch (e) { alert(e.message); } refreshSoon(0); });
    policy.append(box, " Auto-approve merges whose computed risk is LOW (you still decide everything else)");
    panel.append(policy);
    if (!list.length) { panel.append(el("p", "muted", "Nothing is waiting for your approval.")); return; }
    for (const a of list) {
      const card = el("div", "card"), ev = a.evidence || {}, qa = ev.qa || {};
      const head = el("div", "row between"); head.append(el("span", "id", `${a.id} · ${a.task_id}`), pill(a.risk_level));
      card.append(head, el("h4", "", a.requested_action), el("div", "sub", `Requested by ${agentName(a.agent_id)}`), el("p", "", a.reason));
      card.append(el("div", "sub", "Risk (computed): " + a.risk_reasons.join("; ")));
      const facts = el("div", "row"); facts.style.margin = "6px 0";
      facts.append("Build ", pill((ev.build || {}).status || "NOT_RUN"), " Tests ", pill(qa.tests_status || "NOT_RUN"), " Review ", pill((ev.review || {}).verdict || "—"), " QA ", pill(qa.verdict || "—"));
      card.append(facts);
      if (qa.test_run) card.append(el("div", "sub", `QA test run ${qa.test_run.id}: ${qa.test_run.passed} passed, ${qa.test_run.failed} failed`));
      const ul = el("ul", "plain");
      (qa.criteria || []).forEach((c) => { const li = el("li"); li.append(el("span", c.met ? "check" : "cross", c.met ? "✔ " : "✖ "), c.criterion); li.append(el("div", "sub", c.evidence)); ul.append(li); });
      card.append(ul, el("div", "sub", "Files: " + (ev.changed_files || []).join(", ")));
      (ev.images || []).forEach((id) => card.append(evidenceImage(id)));
      const comment = el("textarea", "comment"); comment.placeholder = "Comment (required to request rework)";
      const decide = (path, extra) => post(`/approvals/${a.id}/${path}`, { comment: comment.value, ...extra });
      const actions = el("div", "actions");
      actions.append(
        button("View diff", "", async () => openModal(`Diff — ${a.task_id}`, diffView((await api(`/approvals/${a.id}`)).diff))),
        button("Approve & merge", "good", () => decide("approve")),
        button("Request rework", "", () => { if (!comment.value.trim()) throw new Error("Say what should change."); return decide("reject", { rework: true }); }),
        button("Reject", "bad", () => decide("reject")),
      );
      card.append(comment, actions); panel.append(card);
    }
  }

  function evidenceImage(id) {
    const img = el("img", "evidence"); img.src = `/artifacts/${id}`; img.alt = "evidence screenshot";
    img.addEventListener("click", () => { const big = el("img"); big.src = img.src; big.style.maxWidth = "100%"; openModal("Evidence", big); });
    return img;
  }

  function diffView(diff) {
    const pre = el("div", "diff");
    for (const line of String(diff || "(empty diff)").split("\n")) {
      const cls = line.startsWith("diff --git") ? "file" : line.startsWith("@@") ? "hunk" : line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : "";
      const span = el("span", cls, line); if (!cls) span.style.display = "block"; pre.append(span);
    }
    return pre;
  }

  // ------------------------------------------------------------------ activity feed (operational trace, not chain-of-thought)
  function describe(e) {
    const p = e.payload || {};
    switch (e.type) {
      case "AGENT_TOOL_CALLED": return { text: p.summary, cls: p.ok ? "" : "err" };
      case "AGENT_STATUS_CHANGED": return ["MEETING", "BLOCKED", "WAITING_APPROVAL", "FAILED"].includes(p.to) ? { text: `${p.to}: ${p.action || ""}`, cls: p.to === "MEETING" ? "" : "hl" } : null;
      case "TASK_CREATED": return { text: `Created ${e.task_id}: ${p.title}` };
      case "TASK_ASSIGNED": return { text: `Assigned ${e.task_id}` };
      case "TASK_STATUS_CHANGED": return { text: `${e.task_id}: ${p.from} → ${p.to}${p.reason ? " — " + p.reason : ""}`, cls: p.to === "DONE" ? "ok" : ["BLOCKED", "FAILED"].includes(p.to) ? "err" : "" };
      case "BUILD_STARTED": return { text: "Build started" };
      case "BUILD_PASSED": return { text: `Build passed (${p.duration_s}s)`, cls: "ok" };
      case "BUILD_FAILED": return { text: `Build ${p.status} — ${p.errors} error(s)`, cls: "err" };
      case "TEST_STARTED": return { text: `Tests started: ${p.filter}` };
      case "TEST_PASSED": return { text: `Tests passed ${p.passed}/${p.passed + p.failed}`, cls: "ok" };
      case "TEST_FAILED": return { text: `Tests ${p.status}: ${p.passed} passed, ${p.failed} failed`, cls: "err" };
      case "BUG_CREATED": return { text: `Bug ${p.bug_id}: ${p.title}`, cls: "err" };
      case "MEETING_STARTED": return { text: `Meeting started: ${p.objective}` };
      case "MEETING_ENDED": return { text: `Meeting ended — ${(p.decisions || []).slice(-1)[0] || ""}` };
      case "APPROVAL_REQUIRED": return { text: `Approval required (${p.risk}): ${p.action}`, cls: "hl" };
      case "APPROVAL_GRANTED": return { text: "Approval granted", cls: "ok" };
      case "APPROVAL_REJECTED": return { text: `Approval rejected${p.rework ? " — rework requested" : ""}`, cls: "err" };
      case "AGENT_ESCALATED": return { text: `Escalated to ${p.escalate_to || "human"}: ${p.reason}`, cls: "err" };
      case "AGENT_FAILED": return { text: `Run ${p.status}: ${p.reason}`, cls: "err" };
      case "MESSAGE_SENT": return { text: `${p.type} → ${agentName(p.receiver)}: ${p.summary}` };
      case "STUDIO_RECOVERED": return { text: `Studio restarted — resumed ${p.resumed_features} feature(s)`, cls: "hl" };
      default: return null;
    }
  }
  function pushFeed(e) {
    const d = describe(e); if (!d) return;
    S.feed.push({ time: e.timestamp, who: e.agent_id, ...d });
    if (S.feed.length > 400) S.feed.shift();
    if (S.tab === "activity") renderFeed();
  }
  function renderFeed() {
    const panel = $("#panel-activity"), atBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 30;
    const feed = el("div", "feed");
    for (const f of S.feed) {
      const line = el("div", "line"); line.append(el("span", "time", hhmm(f.time)));
      if (f.who) line.append(el("span", "who", agentName(f.who)));
      line.append(el("span", f.cls || "", f.text)); feed.append(line);
    }
    panel.replaceChildren(feed);
    if (atBottom) panel.scrollTop = panel.scrollHeight;
  }

  // ------------------------------------------------------------------ employee detail panel (spec 13)
  async function loadEmployee() {
    if (!S.selected) return;
    try { S.empData = await api(`/agents/${S.selected}`); } catch (_) { return; }
    renderEmployee();
  }
  function renderEmployee() {
    const d = S.empData, panel = $("#panel-employee"); if (!d) return;
    panel.replaceChildren();
    const head = el("div", "emp-head"), av = el("div", "emp-avatar", d.name[0]); av.style.background = d.avatar.color;
    const who = el("div"); who.append(el("div", "emp-name", d.name.toUpperCase()), el("div", "sub", d.role));
    head.append(av, who); panel.append(head);
    const run = d.run || {}, kv = el("div", "kv");
    const add = (k, v) => kv.append(el("span", "", k), el("span", "", v));
    add("Status", `${d.state}${d.paused ? " (paused)" : ""}`);
    add("Task", d.task ? `${d.task.id} — ${d.task.title}` : "—");
    add("Elapsed", d.state === "IDLE" ? "—" : elapsed(d.since));
    add("Model", run.model || d.profile.model.model || `${d.profile.model.tier} tier`);
    add("Tokens", ((run.input_tokens || 0) + (run.output_tokens || 0)).toLocaleString());
    add("Cost", money(run.cost_usd));
    add("Files inspected", (run.files_inspected || []).length); add("Files modified", (run.files_modified || []).length);
    add("Tool calls", run.tool_calls || 0); add("Current action", d.current_action || "—");
    panel.append(kv);

    const tabs = el("div", "subtabs");
    for (const t of ["TASK", "FILES", "DIFF", "ACTIVITY", "LOGS", "MEMORY", "TOOLS", "PERMISSIONS"]) {
      const b = el("button", t === S.empTab ? "active" : "", t);
      b.addEventListener("click", () => { S.empTab = t; renderEmployee(); }); tabs.append(b);
    }
    panel.append(tabs);
    const body = el("div"); panel.append(body);
    const pre = (s) => body.append(el("pre", "block", s || "—"));
    switch (S.empTab) {
      case "TASK":
        if (!d.task) { pre("No task assigned."); break; }
        pre(`${d.task.id} [${d.task.status}]\n${d.task.title}\n\n${d.task.description}\n\nAcceptance criteria:\n${d.task.acceptance_criteria.map((c, i) => `  ${i + 1}. ${c}`).join("\n")}${d.task.feedback.length ? "\n\nFeedback to address:\n  " + d.task.feedback.join("\n  ") : ""}`);
        break;
      case "FILES": pre(`Inspected:\n  ${(run.files_inspected || []).join("\n  ") || "—"}\n\nModified:\n  ${(run.files_modified || []).join("\n  ") || "—"}`); break;
      case "DIFF":
        if (!d.task) { pre("No task."); break; }
        body.append(el("p", "muted", "loading…"));
        api(`/tasks/${d.task.id}/diff`).then((diff) => body.replaceChildren(diffView(diff || "(no committed diff yet)"))).catch(() => {});
        break;
      case "ACTIVITY": pre(d.activity.slice().reverse().map((a) => `${hhmm(a.time)} ${a.ok ? " " : "✖"} ${a.summary}`).join("\n")); break;
      case "LOGS": pre(d.activity.filter((a) => !a.ok).map((a) => `${hhmm(a.time)} ${a.tool}\n${a.error}`).join("\n\n") || "No errors."); break;
      case "MEMORY": pre(d.memory.map((m) => `[${m.kind}] ${m.title}\n  ${m.content}`).join("\n\n") || "No memories yet."); break;
      case "TOOLS": pre(d.profile.tools.join("\n") || "(no tools - deterministic role)"); break;
      case "PERMISSIONS": pre(Object.entries(d.profile.permissions).map(([k, v]) => `${k.padEnd(22)} ${v}`).join("\n") + `\n\nWritable areas: ${d.profile.write_globs.join(", ") || "none"}\nBudgets: ${d.profile.max_iterations} iterations · ${d.profile.max_tool_calls} tool calls · ${d.profile.token_budget.toLocaleString()} tokens · ${money(d.profile.cost_budget)} per run\nSupervisor: ${d.profile.supervisor || "you"}`); break;
    }
    const actions = el("div", "actions");
    actions.append(
      d.paused ? button("RESUME", "", () => post(`/agents/${d.id}/resume`).then(loadEmployee)) : button("PAUSE", "", () => post(`/agents/${d.id}/pause`).then(loadEmployee)),
      button("CANCEL TASK", "", () => d.task ? (confirm(`Cancel ${d.task.id}?`) ? post(`/tasks/${d.task.id}/cancel`) : null) : Promise.reject(new Error("No task to cancel."))),
      button("REQUEST REPORT", "", async () => openModal(`Report — ${d.name}`, el("pre", "block", (await api(`/agents/${d.id}/report`)).report))),
    );
    panel.append(actions);
  }

  // ------------------------------------------------------------------ tabs, modal, request form
  function setTab(tab) {
    S.tab = tab;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    for (const t of ["tasks", "approvals", "activity", "employee"]) $("#panel-" + t).hidden = t !== tab;
    if (tab === "activity") renderFeed();
  }
  $("#tabs").addEventListener("click", (ev) => { const b = ev.target.closest("button[data-tab]"); if (b) setTab(b.dataset.tab); });
  function openModal(title, node) { $("#modal-title").textContent = title; $("#modal-body").replaceChildren(node); $("#modal").hidden = false; }
  $("#modal-close").addEventListener("click", () => { $("#modal").hidden = true; });
  $("#modal").addEventListener("click", (ev) => { if (ev.target.id === "modal") $("#modal").hidden = true; });
  $("#request-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = $("#request-input"), text = input.value.trim();
    if (text.length < 3) return;
    try { await post("/tasks", { request: text }); input.value = ""; setTab("tasks"); refreshSoon(0); } catch (e) { alert(e.message); }
  });

  // ------------------------------------------------------------------ data flow
  function applyState(state) {
    S.state = state;
    S.meetings = new Map(state.meetings.map((m) => [m.id, m]));
    for (const a of state.agents) S.agents.set(a.id, { ...(S.agents.get(a.id) || {}), ...a });
    syncSprites(); renderTop(); renderTasks(); renderApprovals();
  }
  async function refresh() {
    try { applyState(await api("/studio/state")); if (S.tab === "employee" && S.selected) loadEmployee(); } catch (_) { /* server restarting */ }
  }
  function refreshSoon(ms = 250) { clearTimeout(S.refreshTimer); S.refreshTimer = setTimeout(refresh, ms); }

  function onEvent(e) {
    if (e.seq <= S.lastSeq) return;
    S.lastSeq = e.seq;
    const p = e.payload || {};
    if (e.type === "AGENT_STATUS_CHANGED" && S.agents.has(e.agent_id)) {
      const a = S.agents.get(e.agent_id);
      a.state = p.to; a.current_action = p.action || ""; a.location = p.location || "desk"; a.task_id = e.task_id;
      syncSprites();
    } else if (e.type === "MEETING_STARTED") {
      S.meetings.set(p.meeting_id, { id: p.meeting_id, participants: p.participants || [] }); syncSprites();
    } else if (e.type === "MEETING_ENDED") {
      S.meetings.delete(p.meeting_id);
    }
    pushFeed(e);
    if (e.type !== "AGENT_STATUS_CHANGED" || ["IDLE", "BLOCKED", "WAITING_APPROVAL", "SUCCESS", "FAILED"].includes(p.to)) refreshSoon();
    if (e.type === "APPROVAL_REQUIRED") setTab("approvals");
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/studio?since=${S.lastSeq}`);
    S.ws = ws;
    const conn = $("#conn");
    ws.onopen = () => { conn.textContent = "live"; conn.className = "conn on"; };
    ws.onmessage = (m) => { const msg = JSON.parse(m.data); if (msg.kind === "event") onEvent(msg.event); };
    ws.onclose = () => { conn.textContent = "reconnecting…"; conn.className = "conn off"; setTimeout(() => { refresh(); connect(); }, 1500); };
  }

  async function boot() {
    resize(); window.addEventListener("resize", resize);
    const state = await api("/studio/state");
    applyState(state);
    const recent = await api("/events?recent=true&limit=150");
    recent.forEach((e) => { const d = describe(e); if (d) S.feed.push({ time: e.timestamp, who: e.agent_id, ...d }); });
    S.lastSeq = state.last_seq;
    connect();
    setInterval(() => { if (S.tab === "employee" && S.selected) loadEmployee(); }, 2500);
    requestAnimationFrame(frame);
  }
  boot().catch((e) => { $("#project-line").textContent = "Backend not reachable: " + e.message; });
})();
