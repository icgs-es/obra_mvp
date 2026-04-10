window.__FILES_JS_LOADED__ = true;
console.log("✅ files.js cargado");

// ---------------- CSRF helper (meta tag) ----------------
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return (parts.pop().split(";").shift() || "").trim();
  return "";
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const metaToken = (meta?.getAttribute("content") || "").trim();
  return metaToken || getCookie("csrftoken"); // fallback
}

// ---------------- Preview + search (IIFE) ----------------
(function () {
  const tbody = document.getElementById("filesTbody");
  const previewTitle = document.getElementById("previewTitle");
  const previewMeta = document.getElementById("previewMeta");
  const previewSurface = document.getElementById("previewSurface");
  const openBtn = document.getElementById("previewOpenBtn");
  const dlBtn = document.getElementById("previewDownloadBtn");
  const searchInput = document.getElementById("searchInput");

  function setPreview(row) {
    const name = row.querySelector(".file-open")?.textContent?.trim() || "Archivo";
    const mime = row.dataset.mime || "";
    const previewUrl = row.dataset.previewUrl;
    const downloadUrl = row.dataset.downloadUrl;

    if (previewTitle) previewTitle.textContent = name;
    if (previewMeta) previewMeta.textContent = mime || "—";

    if (openBtn) {
      openBtn.classList.remove("d-none");
      openBtn.href = previewUrl;
    }
    if (dlBtn) {
      dlBtn.classList.remove("d-none");
      dlBtn.href = downloadUrl;
    }

    if (!previewSurface) return;
    previewSurface.innerHTML = "";

    if (mime.startsWith("image/")) {
      const img = document.createElement("img");
      img.src = previewUrl;
      img.alt = name;
      img.onerror = () => {
        previewSurface.innerHTML = `<div class="text-muted">No se pudo cargar la imagen.</div>`;
      };
      previewSurface.appendChild(img);
      return;
    }

    if (mime === "application/pdf" || mime.includes("pdf")) {
      const iframe = document.createElement("iframe");
      iframe.src = previewUrl + "#toolbar=0&navpanes=0";
      iframe.onerror = () => {
        previewSurface.innerHTML = `<div class="text-muted">No se pudo previsualizar el PDF.</div>`;
      };
      previewSurface.appendChild(iframe);
      return;
    }

    previewSurface.innerHTML = `<div class="text-muted">Sin previsualización para este tipo. Usa “Abrir” o “Descargar”.</div>`;
  }

  // selección preview
  tbody?.addEventListener("click", (e) => {
    const row = e.target.closest(".file-row");
    if (!row) return;

    if (e.target.classList.contains("file-open") || e.target.classList.contains("btn-preview")) {
      e.preventDefault();
      tbody.querySelectorAll(".file-row.table-active").forEach(r => r.classList.remove("table-active"));
      row.classList.add("table-active");
      setPreview(row);
    }
  });

  // filtro búsqueda
  searchInput?.addEventListener("input", () => {
    const q = searchInput.value.trim().toLowerCase();
    tbody?.querySelectorAll(".file-row").forEach(row => {
      const name = (row.dataset.name || "").toLowerCase();
      row.style.display = name.includes(q) ? "" : "none";
    });
  });
})();

// ---------------- DOMContentLoaded: masivo + subir carpeta ----------------
document.addEventListener("DOMContentLoaded", () => {
  console.log("📂 files.js DOMContentLoaded");

  // ---------- Eliminar masivo ----------
  const deleteBtn = document.getElementById("btnDeleteSelected");
  const checkAll  = document.getElementById("checkAll");
  const rowChecks = Array.from(document.querySelectorAll(".rowCheck"));

  function getSelectedIds() {
    return rowChecks.filter(cb => cb.checked).map(cb => cb.value);
  }

  function refreshDeleteButton() {
    if (!deleteBtn) return;
    deleteBtn.disabled = getSelectedIds().length === 0;
  }

  rowChecks.forEach(cb => cb.addEventListener("change", refreshDeleteButton));
  if (checkAll) {
    checkAll.addEventListener("change", () => {
      rowChecks.forEach(cb => cb.checked = checkAll.checked);
      refreshDeleteButton();
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      const selected = getSelectedIds();
      if (!selected.length) return;

      if (!confirm(`¿Eliminar ${selected.length} archivo(s) seleccionado(s)?`)) return;

      const csrf = getCsrfToken();
      const formData = new URLSearchParams();
      selected.forEach(id => formData.append("ids", id));

      try {
        const res = await fetch(deleteBtn.dataset.url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            ...(csrf ? { "X-CSRFToken": csrf } : {}),
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
          },
          body: formData.toString(),
        });

        const ct = res.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          const txt = await res.text();
          console.error("Eliminar masivo: no JSON", res.status, txt.slice(0, 500));
          alert(`Eliminar masivo: respuesta no-JSON (status ${res.status}).`);
          return;
        }

        const data = await res.json();
        if (!res.ok || !data.ok) {
          alert(data.error || `No se pudieron eliminar (status ${res.status}).`);
          return;
        }

        location.reload();
      } catch (err) {
        console.error("Error fetch eliminar-masivo:", err);
        alert("Error de red eliminando archivos.");
      }
    });
  }

  refreshDeleteButton();

  // ---------- Subir carpeta completa (input#folderUploadInput) ----------
  const folderInput = document.getElementById("folderUploadInput");
  if (folderInput) {
    folderInput.addEventListener("change", async () => {
      const files = Array.from(folderInput.files || []);
      if (!files.length) return;

      const url = folderInput.dataset.uploadUrl;
      if (!url) {
        console.error("folderUploadInput sin data-upload-url");
        return;
      }

      const form = new FormData();
      form.append("keep_root", "1");

      for (const file of files) {
        form.append("files", file);
        form.append("relpath", file.webkitRelativePath || file.name);
      }

      const csrf = getCsrfToken();

      try {
        const res = await fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            ...(csrf ? { "X-CSRFToken": csrf } : {}),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: form, // NO Content-Type manual
        });

        const ct = res.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          const txt = await res.text();
          console.error("Subir carpeta: no JSON", res.status, txt.slice(0, 500));
          alert(`Subir carpeta: respuesta no-JSON (status ${res.status}).`);
          return;
        }

        const data = await res.json();
        if (!res.ok || !data.ok) {
          alert(data.error || `Error subiendo carpeta (status ${res.status}).`);
          return;
        }

        window.location.reload();
      } catch (err) {
        console.error("Error de red al subir carpeta:", err);
        alert("Error de red subiendo carpeta");
      }
    });
  }
});
