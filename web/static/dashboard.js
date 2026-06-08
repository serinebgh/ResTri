// dashboard.js — pilote la page via WebSocket (Flask-SocketIO)

const socket = io();
const $ = (id) => document.getElementById(id);

// ───── Barre du haut : se masque quand on descend, réapparaît quand on remonte ─────
(() => {
  const bar = document.getElementById("topbar");
  let lastY = window.scrollY;
  window.addEventListener("scroll", () => {
    const y = window.scrollY;
    if (y > lastY && y > 90) bar.classList.add("hidden");   // descente
    else                     bar.classList.remove("hidden"); // montée
    lastY = y;
  }, { passive: true });
})();

const BAND_BGR = {
  BLACK:"#282828", BROWN:"#a03c00", RED:"#dc0000", ORANGE:"#ff7800",
  YELLOW:"#d2d200", GREEN:"#32b400", BLUE:"#001ec8", PURPLE:"#8c008c",
  GRAY:"#787878", WHITE:"#dcdcc8", GOLD:"#d7b400", SILVER:"#c0c0c0",
};
const BIN_COLORS = ["#3fb950", "#d29922", "#f0883e", "#a371f7"];

let currentBins = [];

function setBadge(id, on){
  const el = $(id);
  el.classList.toggle("on", !!on);
  el.classList.toggle("off", !on);
}

// ───── Affichage de la config des 4 bacs ─────
function renderBins(bins){
  currentBins = bins;
  const box = $("bins");
  box.innerHTML = "";
  bins.forEach((b) => {
    const reject = b.reject || b.value == null;
    const row = document.createElement("div");
    row.className = "bin-row";
    row.style.borderLeft = `4px solid ${reject ? "#f85149" : BIN_COLORS[b.index % 4]}`;
    row.innerHTML = `
      <span class="bin-tag">Bac ${b.index + 1} · ${b.angle}°</span>
      <input class="bin-val" data-i="${b.index}" value="${reject ? "rebut" : b.label}">
      <span class="bin-cnt" id="bincnt-${b.index}">0</span>`;
    box.appendChild(row);
  });
}

function updateCounters(c){
  let total = 0;
  currentBins.forEach((b) => {
    const v = c[String(b.index)] || 0;
    const el = $(`bincnt-${b.index}`);
    if (el) el.textContent = v;
    total += v;
  });
  $("cnt-total").textContent = total;
}

function updateConfidence(pct){
  const fill = $("conf-fill");
  fill.style.width = pct + "%";
  $("conf-val").textContent = pct.toFixed(0) + "%";
  fill.style.background = pct >= 75 ? "var(--green)"
                        : pct >= 45 ? "var(--amber)" : "var(--red)";
}

// ───── WebSocket ─────
socket.on("connect",    () => setBadge("ws-badge", true));
socket.on("disconnect", () => setBadge("ws-badge", false));

socket.on("status", (s) => {
  setBadge("cam-badge",   s.camera_connected);
  setBadge("stm32-badge", s.stm32_connected);
  if (s.bins) renderBins(s.bins);
  if (s.counters) updateCounters(s.counters);
});

socket.on("bins", (m) => { if (m.bins) renderBins(m.bins); });

// Détection d'une résistance verrouillée
socket.on("detection", (d) => {
  $("value").textContent = d.value_str;

  const cat = $("category");
  cat.textContent = "➜ " + (d.bin_label || "?") + "  (bac " + ((d.bin_index ?? 0) + 1) + ")";
  cat.style.color = d.bin_reject ? "var(--red)" : BIN_COLORS[(d.bin_index ?? 0) % 4];

  const bands = $("bands");
  bands.innerHTML = "";
  (d.bands || []).forEach(name => {
    const b = document.createElement("div");
    b.className = "b";
    b.style.background = BAND_BGR[name] || "#888";
    b.title = name;
    bands.appendChild(b);
  });

  updateConfidence(d.confidence || 0);
  if (d.counters) updateCounters(d.counters);
});

socket.on("counters_reset", (c) => {
  updateCounters(c);
  $("value").textContent = "—";
  $("bands").innerHTML = "";
  $("category").textContent = "en attente…";
  $("category").style.color = "";
  updateConfidence(0);
});

// Console série STM32
socket.on("stm32", (m) => {
  const log = $("stm32-log");
  log.textContent += m.line + "\n";
  log.scrollTop = log.scrollHeight;
});

// ───── Chargement initial de la config ─────
fetch("/api/bins").then(r => r.json()).then(j => renderBins(j.bins));

// ───── Boutons ─────
$("btn-save-bins").addEventListener("click", () => {
  const payload = { bins: [] };
  document.querySelectorAll(".bin-val").forEach(inp => {
    payload.bins.push({ value: inp.value });
  });
  fetch("/api/bins", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  })
  .then(r => r.json())
  .then(j => { renderBins(j.bins); alert("Configuration des bacs enregistrée ✅"); });
});

$("btn-reset").addEventListener("click", () => fetch("/api/reset", {method:"POST"}));
$("btn-save").addEventListener("click", () => {
  fetch("/api/save", {method:"POST"}).then(r => r.json())
    .then(j => { if (j.path) console.log("crop sauvé:", j.path); });
});
