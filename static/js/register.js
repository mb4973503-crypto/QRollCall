const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const scanStatus = document.getElementById("scan-status");
const formCard = document.getElementById("form-card");
const registerStatus = document.getElementById("register-status");
const rescanBtn = document.getElementById("rescan-btn");
const registerBtn = document.getElementById("register-btn");

let scanning = true;
let scanIntervalId = null;

function showMessage(el, text, type) {
  el.textContent = text;
  el.className = "status-message show status-" + type;
}

function hideMessage(el) {
  el.className = "status-message";
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" }
    });
    video.srcObject = stream;
  } catch (err) {
    showMessage(scanStatus, "Could not access camera: " + err.message, "error");
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
  if (!scanning || video.videoWidth === 0) return;

  const blob = await captureFrame();
  const formData = new FormData();
  formData.append("image", blob, "frame.jpg");

  try {
    const response = await fetch("/decode_qr", {
      method: "POST",
      body: formData
    });
    const data = await response.json();

    if (data.success) {
      scanning = false;
      clearInterval(scanIntervalId);

      if (data.already_registered) {
        showMessage(
          scanStatus,
          `${data.student.name} (${data.student.student_id}) is already registered.`,
          "warning"
        );
        formCard.style.display = "none";
      } else {
        showMessage(scanStatus, "QR code detected! Fill in the details below.", "success");
        document.getElementById("student_id").value = data.student_id;
        formCard.style.display = "block";
      }
    }
    // If not successful (no QR detected yet), just keep scanning silently.
  } catch (err) {
    // Network hiccup — keep trying, don't spam the user.
  }
}

rescanBtn.addEventListener("click", () => {
  scanning = true;
  hideMessage(scanStatus);
  formCard.style.display = "none";
  hideMessage(registerStatus);
  document.getElementById("name").value = "";
  document.getElementById("course").value = "";
  document.getElementById("year_level").value = "";

  if (scanIntervalId) clearInterval(scanIntervalId);
  scanIntervalId = setInterval(attemptScan, 1000);
});

registerBtn.addEventListener("click", async () => {
  const studentId = document.getElementById("student_id").value.trim();
  const name = document.getElementById("name").value.trim();
  const course = document.getElementById("course").value.trim();
  const yearLevel = document.getElementById("year_level").value;

  if (!name) {
    showMessage(registerStatus, "Full name is required.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("student_id", studentId);
  formData.append("name", name);
  formData.append("course", course);
  formData.append("year_level", yearLevel);

  try {
    const response = await fetch("/register", {
      method: "POST",
      body: formData
    });
    const data = await response.json();

    showMessage(registerStatus, data.message, data.success ? "success" : "error");

    if (data.success) {
      setTimeout(() => {
        rescanBtn.click();
      }, 1500);
    }
  } catch (err) {
    showMessage(registerStatus, "Something went wrong. Please try again.", "error");
  }
});

startCamera();
scanIntervalId = setInterval(attemptScan, 1000);
