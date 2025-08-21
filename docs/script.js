const BACKEND_URL = "https://hospital-analytics.onrender.com";  

async function loadPatients() {
  const res = await fetch(`${BACKEND_URL}/patients`);
  const data = await res.json();
  document.getElementById("patients").innerHTML =
    "<pre>" + JSON.stringify(data, null, 2) + "</pre>";
}

async function loadDoctors() {
  const res = await fetch(`${BACKEND_URL}/admissions`);
  const data = await res.json();
  document.getElementById("doctors").innerHTML =
    "<pre>" + JSON.stringify(data, null, 2) + "</pre>";
}
