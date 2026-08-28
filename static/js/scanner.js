const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const scanResult = document.getElementById("scan-result");

let busy = false;
let cooldownUntil = 0;

function showMessage(el, text, type) {
  el.textContent = text;
  el.className = "status-message show status-" + type;
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" }
    });
    video.srcObject = stream;
  } catch (err) {
    showMessage(scanResult, "Could not access camera: " + err.message, "error");
  }
}

function captureFrame() {
  const ctx = canvas.getContext("2d");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.9);
  });
}

async function attemptScan() {
  const now = Date.now();
  if (busy || now < cooldownUntil || video.videoWidth === 0) return;

  busy = true;
  const blob = await captureFrame();
  const formData = new FormData();
  formData.append("image", blob, "frame.jpg");

  try {
    const response = await fetch("/scan", {
      method: "POST",
      body: formData
    });
    const data = await response.json();

    if (data.message) {
      let type = "success";

      if (!data.success) type = "error";
      else if (data.already_scanned) type = "warning";
      else if (data.status === "Late") type = "warning";

      showMessage(scanResult, data.message, type);

      // Only cool down after an actual QR read (success or a
      // recognized-but-not-registered ID), so we don't spam
      // messages every second while nothing is in frame.
      if (data.success || data.student_id) {
        cooldownUntil = Date.now() + 4000;
      }
    }
  } catch (err) {
    // Network hiccup — stay quiet, try again next tick.
  } finally {
    busy = false;
  }
}

startCamera();
setInterval(attemptScan, 1000);
