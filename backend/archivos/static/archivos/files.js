window.__FILES_JS_LOADED__ = true;
console.log("✅ files.js cargado");

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

    previewTitle.textContent = name;
    previewMeta.textContent = mime || "—";

    openBtn.classList.remove("d-none");
    dlBtn.classList.remove("d-none");
    openBtn.href = previewUrl;
    dlBtn.href = downloadUrl;

    // limpiar
    previewSurface.innerHTML = "";

    // render
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
      // Si quieres ocultar UI del visor PDF:
      iframe.src = previewUrl + "#toolbar=0&navpanes=0";
      iframe.onerror = () => {
        previewSurface.innerHTML = `<div class="text-muted">No se pudo previsualizar el PDF.</div>`;
      };
      previewSurface.appendChild(iframe);
      return;
    }

    previewSurface.innerHTML = `<div class="text-muted">Sin previsualización para este tipo. Usa “Abrir” o “Descargar”.</div>`;
  }

  // selección
  tbody?.addEventListener("click", (e) => {
    const row = e.target.closest(".file-row");
    if (!row) return;

    // click en enlace o botón Ver => preview
    if (e.target.classList.contains("file-open") || e.target.classList.contains("btn-preview")) {
      e.preventDefault();
      tbody.querySelectorAll(".file-row.table-active").forEach(r => r.classList.remove("table-active"));
      row.classList.add("table-active");
      setPreview(row);
    }
  });

  // filtro
  searchInput?.addEventListener("input", () => {
    const q = searchInput.value.trim().toLowerCase();
    tbody.querySelectorAll(".file-row").forEach(row => {
      const name = row.dataset.name || "";
      row.style.display = name.includes(q) ? "" : "none";
    });
  });
})();

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
}

document.addEventListener("DOMContentLoaded", () => {
  // ---------- Subir carpeta ----------
  const folderInput = document.getElementById("folderUploadInput");
  if (folderInput) {
    folderInput.addEventListener("change", async () => {
      const files = Array.from(folderInput.files || []);
      if (!files.length) return;

      const url = folderInput.dataset.uploadUrl;
      const form = new FormData();
      form.append("keep_root", "1");

      for (const file of files) {
        form.append("files", file);
        form.append("relpath", file.webkitRelativePath || file.name);
      }

      const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
      const res = await fetch(url, {
        method: "POST",
        headers: csrf ? { "X-CSRFToken": csrf } : {},
        body: form,
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        alert(data.error || "Error subiendo carpeta");
        return;
      }
      window.location.reload();
    });
  }

  // ---------- Selección + eliminar masivo ----------
  const deleteBtn = document.getElementById("btnDeleteSelected");
  const checkAll = document.getElementById("checkAll");

  function getSelectedIds() {
    return Array.from(document.querySelectorAll(".rowCheck:checked")).map(cb => cb.value);
  }

  function refreshDeleteButton() {
    if (!deleteBtn) return;
    deleteBtn.disabled = getSelectedIds().length === 0;
  }

  // activar/desactivar botón al marcar
  document.querySelectorAll(".rowCheck").forEach(cb => {
    cb.addEventListener("change", refreshDeleteButton);
  });

  // checkAll
  if (checkAll) {
    checkAll.addEventListener("change", () => {
      document.querySelectorAll(".rowCheck").forEach(cb => {
        cb.checked = checkAll.checked;
      });
      refreshDeleteButton();
    });
  }

// click eliminar masivo
if (deleteBtn) {
  deleteBtn.addEventListener("click", () => {
    const selected = getSelectedIds();
    if (!selected.length) return;

    if (!confirm(`¿Eliminar ${selected.length} archivo(s) seleccionado(s)?`)) return;

    fetch(deleteBtn.dataset.url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(selected.map(id => ["ids", id])),
    })
    .then(res => res.json())
    .then(data => {
      if (!data.ok) {
        alert(data.error || "No se pudieron eliminar.");
        return;
      }
      location.reload();
    })
    .catch(() => alert("Error de red eliminando archivos."));
  });

  refreshDeleteButton();
}
