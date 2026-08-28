const dashboardStatus = document.getElementById("dashboard-status");
const markAbsenteesBtn = document.getElementById("mark-absentees-btn");

function showMessage(text, type) {
  dashboardStatus.textContent = text;
  dashboardStatus.className = "status-message show status-" + type;
}

// --- Manual status override ---
document.querySelectorAll(".override-select").forEach((select) => {
  select.addEventListener("change", async (e) => {
    const studentId = e.target.dataset.studentId;
    const date = e.target.dataset.date;
    const status = e.target.value;

    const formData = new FormData();
    formData.append("student_id", studentId);
    formData.append("date", date);
    formData.append("status", status);

    try {
      const response = await fetch("/update_attendance", {
        method: "POST",
        body: formData
      });
      const data = await response.json();
      showMessage(data.message, data.success ? "success" : "error");

      if (data.success) {
        setTimeout(() => window.location.reload(), 800);
      }
    } catch (err) {
      showMessage("Something went wrong updating attendance.", "error");
    }
  });
});

// --- Mark today's absentees ---
markAbsenteesBtn.addEventListener("click", async () => {
  const formData = new FormData();

  try {
    const response = await fetch("/mark_absentees", {
      method: "POST",
      body: formData
    });
    const data = await response.json();
    showMessage(data.message, data.success ? "success" : "error");

    if (data.success) {
      setTimeout(() => window.location.reload(), 1000);
    }
  } catch (err) {
    showMessage("Something went wrong marking absentees.", "error");
  }
});

// --- Delete student ---
document.querySelectorAll(".delete-btn").forEach((btn) => {
  btn.addEventListener("click", async (e) => {
    const studentId = e.target.dataset.studentId;

    if (!confirm(`Delete student ${studentId}? This also removes their attendance history.`)) {
      return;
    }

    try {
      const response = await fetch(`/delete_student/${studentId}`, {
        method: "POST"
      });
      const data = await response.json();
      showMessage(data.message, data.success ? "success" : "error");

      if (data.success) {
        setTimeout(() => window.location.reload(), 800);
      }
    } catch (err) {
      showMessage("Something went wrong deleting the student.", "error");
    }
  });
});
