// ====== CONFIG ======
const BACKEND_URL = "https://hospital-analytics.onrender.com"; // your Render URL
const AUTO_REFRESH_MS = 60000; // 1 minute

// ====== STATE ======
const state = {
  start: null,
  end: null,
  ward_ids: [],
  doctor_ids: [],
  status: "all",
  charts: {}
};

// ====== HELPERS ======
const qs = (sel) => document.querySelector(sel);
function buildParams() {
  const p = new URLSearchParams();
  if (state.start) p.set("start", state.start);
  if (state.end) p.set("end", state.end);
  if (state.ward_ids.length) p.set("ward_ids", state.ward_ids.join(","));
  if (state.doctor_ids.length) p.set("doctor_ids", state.doctor_ids.join(","));
  if (state.status) p.set("status", state.status);
  return p.toString();
}
async function api(path) {
  const url = `${BACKEND_URL}${path}${path.includes("?") ? "&" : "?"}${buildParams()}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
function setMultiSelect(selectEl, items, idKey, labelKey) {
  selectEl.innerHTML = "";
  items.forEach(it => {
    const opt = document.createElement("option");
    opt.value = it[idKey];
    opt.textContent = it[labelKey];
    selectEl.appendChild(opt);
  });
}
function getSelected(selectEl) {
  return Array.from(selectEl.selectedOptions).map(o => parseInt(o.value, 10));
}

// ====== INITIAL DATA FOR FILTERS ======
async function loadFilterOptions() {
  // wards
  const wards = await api("/wards/utilization"); // {wards:[{ward_id, ward_name,...}]}
  setMultiSelect(qs("#wardSelect"), wards.wards, "ward_id", "ward_name");
  // doctors
  const docs = await api("/doctors/workload"); // {doctors:[{doctor_id, name,...}]}
  setMultiSelect(qs("#doctorSelect"), docs.doctors, "doctor_id", "name");
}

// ====== KPI RENDER ======
async function refreshKPIs() {
  const data = await api("/kpis");
  // beds
  qs("#kpiOcc").textContent = `${data.beds.occupancy_rate}%`;
  qs("#kpiBeds").textContent = `${data.beds.occupied} / ${data.beds.total}`;
  // admissions
  qs("#kpiActive").textContent = data.admissions.active;
  qs("#kpiDischToday").textContent = data.admissions.discharges_today;
  qs("#kpiLOS").textContent = `${data.admissions.avg_length_of_stay_days} d`;
  qs("#kpiDischCount").textContent = data.admissions.discharged;
  // doctors
  qs("#kpiDocsPresent").textContent = data.doctors.present;
  qs("#kpiDocsBusy").textContent = data.doctors.busy;
  qs("#kpiDocsTotal").textContent = data.doctors.total;
}

// ====== CHARTS ======
function ensureChart(id, config) {
  if (state.charts[id]) { state.charts[id].destroy(); }
  state.charts[id] = new Chart(qs("#"+id), config);
}

async function refreshCharts() {
  // Admissions series
  const series = await api("/admissions/series?granularity=day");
  const labels = series.series.map(r => r.bucket);
  const values = series.series.map(r => r.admissions);
  ensureChart("admissionsChart", {
    type: "line",
    data: { labels, datasets: [{ label: "Admissions", data: values }] },
    options: { responsive:true, interaction:{mode:"index", intersect:false}, plugins:{legend:{display:false}}, scales:{x:{ticks:{maxRotation:0}}}}
  });

  // Ward utilization
  const wards = await api("/wards/utilization");
  const wLabels = wards.wards.map(w => w.ward_name);
  const wOcc = wards.wards.map(w => w.occupancy_rate);
  ensureChart("wardsChart", {
    type: "bar",
    data: { labels: wLabels, datasets: [{ label:"Occupancy %", data:wOcc }] },
    options:{ responsive:true, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true,max:100}}}
  });

  // Doctor status
  const docs = await api("/doctors/workload");
  const dLabels = docs.doctors.map(d => d.name);
  const dBusy = docs.doctors.map(d => d.is_busy ? 1 : 0);
  const dPresent = docs.doctors.map(d => d.is_present ? 1 : 0);
  ensureChart("doctorsChart", {
    type: "bar",
    data: { labels: dLabels,
      datasets: [
        { label:"Present", data:dPresent },
        { label:"Busy", data:dBusy }
      ]},
    options:{ responsive:true, interaction:{mode:"index",intersect:false} }
  });
}

// ====== APPLY FILTERS ======
function readFilters() {
  state.start = qs("#startDate").value || null;
  state.end = qs("#endDate").value || null;
  state.ward_ids = getSelected(qs("#wardSelect"));
  state.doctor_ids = getSelected(qs("#doctorSelect"));
  state.status = qs("#statusSelect").value;
}
async function applyFilters() {
  readFilters();
  await Promise.all([refreshKPIs(), refreshCharts()]);
}

// ====== INIT + AUTO REFRESH ======
async function init() {
  await loadFilterOptions();
  await applyFilters();
  setInterval(applyFilters, AUTO_REFRESH_MS);
}
document.getElementById("applyBtn").addEventListener("click", applyFilters);
init();
