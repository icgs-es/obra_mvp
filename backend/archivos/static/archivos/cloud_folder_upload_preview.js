/*
 * INTASA Documents · Folder Upload Preview · P2A
 *
 * Esta fase:
 * - selecciona una carpeta local;
 * - construye un manifiesto de metadatos;
 * - consulta únicamente el endpoint preflight;
 * - no transmite el contenido de ningún archivo;
 * - no invoca el endpoint de ejecución.
 */
(function () {
  "use strict";

  const chooseButton = document.getElementById(
    "folderUploadChooseButton"
  );
  const folderInput = document.getElementById(
    "folderUploadInput"
  );
  const panel = document.getElementById(
    "folderUploadPreview"
  );

  if (!chooseButton || !folderInput || !panel) {
    return;
  }

  const preflightUrl = panel.dataset.preflightUrl || "";
  const currentPath = panel.dataset.currentPath || "";

  const csrfTokenInput = panel.querySelector(
    "input[name='csrfmiddlewaretoken']"
  );

  const csrfToken = csrfTokenInput
    ? csrfTokenInput.value
    : "";

  const clearButton = document.getElementById(
    "folderUploadClearButton"
  );
  const revalidateButton = document.getElementById(
    "folderUploadRevalidateButton"
  );
  const executeButton = document.getElementById(
    "folderUploadExecuteButton"
  );
  const policySelect = document.getElementById(
    "folderUploadPolicy"
  );
  const replacePanel = document.getElementById(
    "folderUploadReplacePanel"
  );
  const replaceConfirm = document.getElementById(
    "folderUploadReplaceConfirm"
  );

  const statusBox = document.getElementById(
    "folderUploadStatus"
  );
  const supportBox = document.getElementById(
    "folderUploadSupportWarning"
  );
  const scopeWarning = document.getElementById(
    "folderUploadScopeWarning"
  );
  const conflictSection = document.getElementById(
    "folderUploadConflictSection"
  );
  const conflictBody = document.getElementById(
    "folderUploadConflictBody"
  );
  const conflictTruncated = document.getElementById(
    "folderUploadConflictTruncated"
  );
  const fileBody = document.getElementById(
    "folderUploadFileBody"
  );
  const fileTruncated = document.getElementById(
    "folderUploadFileTruncated"
  );

  const rootNameValue = document.getElementById(
    "folderUploadRootName"
  );
  const destinationValue = document.getElementById(
    "folderUploadDestination"
  );
  const teamValue = document.getElementById(
    "folderUploadTeam"
  );
  const filesValue = document.getElementById(
    "folderUploadFilesCount"
  );
  const directoriesValue = document.getElementById(
    "folderUploadDirectoriesCount"
  );
  const sizeValue = document.getElementById(
    "folderUploadTotalSize"
  );
  const conflictsValue = document.getElementById(
    "folderUploadConflictsCount"
  );
  const operationValue = document.getElementById(
    "folderUploadOperation"
  );

  const filePreviewLimit = 200;
  const conflictPreviewLimit = 100;

  let selectedFiles = [];
  let descriptors = [];
  let directories = [];
  let currentPreflight = null;
  let preflightValidatedAt = 0;
  let requestController = null;
  let validationSequence = 0;

  function show(element, visible) {
    if (!element) {
      return;
    }

    element.classList.toggle("d-none", !visible);
  }

  function humanSize(bytes) {
    let value = Number(bytes || 0);

    if (!Number.isFinite(value) || value < 0) {
      return "—";
    }

    const units = [
      "B",
      "KB",
      "MB",
      "GB",
      "TB"
    ];

    let index = 0;

    while (
      value >= 1024
      && index < units.length - 1
    ) {
      value /= 1024;
      index += 1;
    }

    if (index === 0) {
      return Math.round(value) + " " + units[index];
    }

    return value.toLocaleString(
      "es-ES",
      {
        maximumFractionDigits: 1,
        minimumFractionDigits: 0
      }
    ) + " " + units[index];
  }

  function setStatus(message, variant, loading) {
    statusBox.className =
      "alert mb-3 alert-" + (variant || "secondary");

    statusBox.replaceChildren();

    if (loading) {
      const spinner = document.createElement("span");
      spinner.className =
        "spinner-border spinner-border-sm me-2";
      spinner.setAttribute("aria-hidden", "true");
      statusBox.appendChild(spinner);
    }

    const text = document.createElement("span");
    text.textContent = message;
    statusBox.appendChild(text);

    show(statusBox, true);
  }

  function setText(element, value) {
    if (element) {
      element.textContent = String(
        value === undefined || value === null
          ? "—"
          : value
      );
    }
  }

  function createBadge(text, variant) {
    const badge = document.createElement("span");
    badge.className =
      "badge folder-upload-status-badge text-bg-"
      + variant;
    badge.textContent = text;
    return badge;
  }

  function statusForEntry(entry, policy) {
    const collision = String(
      entry.collision_kind || ""
    );

    if (!collision) {
      return {
        text: "Nuevo",
        variant: "success"
      };
    }

    if (policy === "skip") {
      return {
        text: "Se omitirá",
        variant: "secondary"
      };
    }

    if (policy === "rename") {
      return {
        text: "Se renombrará",
        variant: "primary"
      };
    }

    if (policy === "replace") {
      return {
        text: "Se reemplazará",
        variant: "warning"
      };
    }

    return {
      text: "Conflicto",
      variant: "danger"
    };
  }

  function relativePathForFile(file) {
    return String(
      file.webkitRelativePath || ""
    )
      .replace(/\\/g, "/")
      .replace(/^\/+/, "");
  }

  function collectSelection(fileList) {
    const files = Array.from(fileList || []);
    const directorySet = new Set();
    const roots = new Set();
    const localDescriptors = [];
    let totalSize = 0;

    for (const file of files) {
      const relativePath = relativePathForFile(
        file
      );

      if (!relativePath) {
        throw new Error(
          "El navegador no ha proporcionado la ruta "
          + "relativa de la carpeta."
        );
      }

      const parts = relativePath.split("/");

      if (parts.length < 2) {
        throw new Error(
          "La selección no contiene una carpeta raíz válida."
        );
      }

      roots.add(parts[0]);
      totalSize += Number(file.size || 0);

      for (
        let index = 1;
        index < parts.length;
        index += 1
      ) {
        directorySet.add(
          parts.slice(0, index).join("/")
        );
      }

      localDescriptors.push({
        relative_path: relativePath,
        size: Number(file.size || 0)
      });
    }

    if (roots.size !== 1) {
      throw new Error(
        "La selección debe pertenecer a una única "
        + "carpeta raíz."
      );
    }

    localDescriptors.sort(function (left, right) {
      return left.relative_path.localeCompare(
        right.relative_path,
        "es",
        {
          numeric: true,
          sensitivity: "base"
        }
      );
    });

    return {
      files: files,
      descriptors: localDescriptors,
      directories: Array.from(directorySet).sort(
        function (left, right) {
          const depthDifference =
            left.split("/").length
            - right.split("/").length;

          if (depthDifference !== 0) {
            return depthDifference;
          }

          return left.localeCompare(
            right,
            "es",
            {
              numeric: true,
              sensitivity: "base"
            }
          );
        }
      ),
      rootName: Array.from(roots)[0],
      totalSize: totalSize
    };
  }

  function renderLocalFiles(localDescriptors) {
    fileBody.replaceChildren();

    const visible = localDescriptors.slice(
      0,
      filePreviewLimit
    );

    for (const descriptor of visible) {
      const row = document.createElement("tr");
      row.dataset.relativePath =
        descriptor.relative_path;

      const pathCell = document.createElement("td");
      pathCell.className =
        "folder-upload-preview-path";

      const icon = document.createElement("i");
      icon.className =
        "bi bi-file-earmark me-2 text-secondary";

      const pathText = document.createElement("span");
      pathText.textContent =
        descriptor.relative_path;

      pathCell.appendChild(icon);
      pathCell.appendChild(pathText);

      const sizeCell = document.createElement("td");
      sizeCell.className =
        "text-end text-nowrap text-muted";
      sizeCell.textContent = humanSize(
        descriptor.size
      );

      const statusCell = document.createElement("td");
      statusCell.className = "text-end";
      statusCell.appendChild(
        createBadge(
          "Pendiente",
          "light border text-dark"
        )
      );

      row.appendChild(pathCell);
      row.appendChild(sizeCell);
      row.appendChild(statusCell);
      fileBody.appendChild(row);
    }

    const remaining =
      localDescriptors.length - visible.length;

    if (remaining > 0) {
      fileTruncated.textContent =
        "Se muestran los primeros "
        + visible.length.toLocaleString("es-ES")
        + " archivos. Hay "
        + remaining.toLocaleString("es-ES")
        + " adicionales.";
      show(fileTruncated, true);
    } else {
      show(fileTruncated, false);
    }
  }

  function renderServerFileStates(data) {
    const entries = (
      data
      && data.manifest
      && Array.isArray(data.manifest.files)
    )
      ? data.manifest.files
      : [];

    const entryMap = new Map();

    for (const entry of entries) {
      entryMap.set(
        entry.relative_path,
        entry
      );
    }

    const policy = data.summary
      ? data.summary.policy
      : policySelect.value;

    for (const row of fileBody.querySelectorAll("tr")) {
      const statusCell = row.lastElementChild;
      const entry = entryMap.get(
        row.dataset.relativePath
      );

      statusCell.replaceChildren();

      if (!entry) {
        statusCell.appendChild(
          createBadge(
            "No validado",
            "danger"
          )
        );
        continue;
      }

      const status = statusForEntry(
        entry,
        policy
      );

      statusCell.appendChild(
        createBadge(
          status.text,
          status.variant
        )
      );
    }
  }

  function renderConflicts(data) {
    const conflicts = Array.isArray(
      data.conflicts
    )
      ? data.conflicts
      : [];

    conflictBody.replaceChildren();

    if (!conflicts.length) {
      show(conflictSection, false);
      return;
    }

    show(conflictSection, true);

    const visible = conflicts.slice(
      0,
      conflictPreviewLimit
    );

    for (const conflict of visible) {
      const row = document.createElement("tr");

      const pathCell = document.createElement("td");
      pathCell.className =
        "folder-upload-preview-path";
      pathCell.textContent = conflict.path;

      const typeCell = document.createElement("td");
      typeCell.className = "text-nowrap";

      const kind = String(conflict.kind || "");

      if (kind === "directory") {
        typeCell.textContent =
          "Carpeta existente";
      } else if (kind === "file") {
        typeCell.textContent =
          "Archivo existente";
      } else {
        typeCell.textContent =
          "Elemento no clasificado";
      }

      row.appendChild(pathCell);
      row.appendChild(typeCell);
      conflictBody.appendChild(row);
    }

    const remaining =
      conflicts.length - visible.length;

    if (remaining > 0) {
      conflictTruncated.textContent =
        "Hay "
        + remaining.toLocaleString("es-ES")
        + " conflictos adicionales.";
      show(conflictTruncated, true);
    } else {
      show(conflictTruncated, false);
    }
  }

  function clearServerResult() {
    currentPreflight = null;
    preflightValidatedAt = 0;

    setText(teamValue, "Pendiente");
    setText(conflictsValue, "—");
    setText(operationValue, "—");

    show(scopeWarning, false);
    show(conflictSection, false);

    for (const row of fileBody.querySelectorAll("tr")) {
      const statusCell = row.lastElementChild;
      statusCell.replaceChildren();
      statusCell.appendChild(
        createBadge(
          "Pendiente",
          "light border text-dark"
        )
      );
    }

    executeButton.disabled = true;
  }

  function renderPreflight(data) {
    currentPreflight = data;
    preflightValidatedAt = Date.now();

    const summary = data.summary || {};
    const team = data.team || {};

    setText(
      rootNameValue,
      summary.root_name || "—"
    );
    setText(
      filesValue,
      Number(summary.files || 0)
        .toLocaleString("es-ES")
    );
    setText(
      directoriesValue,
      Number(summary.directories || 0)
        .toLocaleString("es-ES")
    );
    setText(
      sizeValue,
      humanSize(summary.total_size)
    );
    setText(
      conflictsValue,
      Number(summary.conflicts || 0)
        .toLocaleString("es-ES")
    );
    setText(
      teamValue,
      team.name || "—"
    );
    setText(
      operationValue,
      data.operation_id
        ? data.operation_id.slice(0, 12)
        : "—"
    );

    if (data.scope_warning) {
      scopeWarning.textContent =
        data.scope_warning;
      show(scopeWarning, true);
    } else {
      show(scopeWarning, false);
    }

    renderConflicts(data);
    renderServerFileStates(data);

    if (data.can_execute) {
      setStatus(
        "Carpeta validada correctamente. "
        + "No se ha subido ningún archivo.",
        "success",
        false
      );
    } else {
      setStatus(
        "La carpeta se ha analizado, pero la política "
        + "seleccionada impide continuar mientras "
        + "existan conflictos.",
        "warning",
        false
      );
    }

    executeButton.disabled = !Boolean(
      data.can_execute
    );
  }

  async function validateSelection() {
    if (!descriptors.length) {
      return;
    }

    const policy = policySelect.value;
    const allowReplace =
      policy === "replace"
      && replaceConfirm.checked;

    show(
      replacePanel,
      policy === "replace"
    );

    if (
      policy === "replace"
      && !allowReplace
    ) {
      clearServerResult();

      setStatus(
        "Para analizar la opción Reemplazar debes "
        + "confirmar expresamente que los archivos "
        + "existentes podrían sustituirse en P2B.",
        "warning",
        false
      );

      return;
    }

    if (!preflightUrl || !csrfToken) {
      setStatus(
        "No se pudo inicializar la validación segura.",
        "danger",
        false
      );
      return;
    }

    if (requestController) {
      requestController.abort();
    }

    requestController = new AbortController();
    validationSequence += 1;

    const sequence = validationSequence;

    clearServerResult();

    chooseButton.disabled = true;
    revalidateButton.disabled = true;
    policySelect.disabled = true;
    replaceConfirm.disabled = true;

    setStatus(
      "Analizando estructura, permisos y conflictos…",
      "info",
      true
    );

    const payload = {
      path: currentPath,
      policy: policy,
      allow_replace: allowReplace,
      files: descriptors,
      directories: directories
    };

    try {
      const response = await fetch(
        preflightUrl,
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest"
          },
          body: JSON.stringify(payload),
          signal: requestController.signal
        }
      );

      const raw = await response.text();
      let data = null;

      try {
        data = JSON.parse(raw);
      } catch (parseError) {
        throw new Error(
          response.redirected
            ? "La sesión ha caducado o requiere iniciar sesión."
            : "El servidor no devolvió una respuesta JSON válida."
        );
      }

      if (
        !response.ok
        || !data
        || data.ok !== true
      ) {
        const message =
          data
          && data.error
          && data.error.message
            ? data.error.message
            : "No se pudo validar la carpeta.";

        throw new Error(message);
      }

      if (sequence !== validationSequence) {
        return;
      }

      renderPreflight(data);

    } catch (error) {
      if (error && error.name === "AbortError") {
        return;
      }

      if (sequence !== validationSequence) {
        return;
      }

      clearServerResult();

      setStatus(
        error && error.message
          ? error.message
          : "No se pudo validar la carpeta.",
        "danger",
        false
      );

    } finally {
      if (sequence === validationSequence) {
        chooseButton.disabled = false;
        revalidateButton.disabled = false;
        policySelect.disabled = false;
        replaceConfirm.disabled = false;
      }
    }
  }

  function resetPreview() {
    if (requestController) {
      requestController.abort();
      requestController = null;
    }

    validationSequence += 1;
    selectedFiles = [];
    descriptors = [];
    directories = [];
    currentPreflight = null;
    preflightValidatedAt = 0;

    folderInput.value = "";
    policySelect.value = "skip";
    replaceConfirm.checked = false;

    fileBody.replaceChildren();
    conflictBody.replaceChildren();

    show(panel, false);
    show(replacePanel, false);
    show(scopeWarning, false);
    show(conflictSection, false);
    show(fileTruncated, false);
    show(conflictTruncated, false);

    executeButton.disabled = true;
  }

  chooseButton.addEventListener(
    "click",
    function () {
      folderInput.value = "";
      folderInput.click();
    }
  );

  folderInput.addEventListener(
    "change",
    function () {
      try {
        const selection = collectSelection(
          folderInput.files
        );

        selectedFiles = selection.files;
        descriptors = selection.descriptors;
        directories = selection.directories;
        currentPreflight = null;

        show(panel, true);

        setText(
          rootNameValue,
          selection.rootName
        );
        setText(
          destinationValue,
          currentPath || "Archivos"
        );
        setText(
          filesValue,
          descriptors.length.toLocaleString("es-ES")
        );
        setText(
          directoriesValue,
          directories.length.toLocaleString("es-ES")
        );
        setText(
          sizeValue,
          humanSize(selection.totalSize)
        );
        setText(
          conflictsValue,
          "Pendiente"
        );
        setText(
          teamValue,
          "Pendiente"
        );
        setText(
          operationValue,
          "—"
        );

        renderLocalFiles(descriptors);

        setStatus(
          "Carpeta leída localmente. "
          + "Iniciando prevalidación segura…",
          "secondary",
          false
        );

        validateSelection();

      } catch (error) {
        show(panel, true);
        clearServerResult();

        setStatus(
          error && error.message
            ? error.message
            : "No se pudo leer la carpeta seleccionada.",
          "danger",
          false
        );
      }
    }
  );

  policySelect.addEventListener(
    "change",
    validateSelection
  );

  replaceConfirm.addEventListener(
    "change",
    validateSelection
  );

  revalidateButton.addEventListener(
    "click",
    validateSelection
  );

  clearButton.addEventListener(
    "click",
    resetPreview
  );

  if (!("webkitdirectory" in folderInput)) {
    chooseButton.disabled = true;

    supportBox.textContent =
      "Este navegador no permite seleccionar carpetas "
      + "completas. Puedes seguir usando “Subir archivos” "
      + "o abrir INTASA Documents con un navegador compatible.";

    show(supportBox, true);
  }

  // P2B_EXECUTION_BRIDGE
  function setInteractionLocked(locked) {
    const controls = [
      chooseButton,
      clearButton,
      revalidateButton,
      policySelect,
      replaceConfirm,
      folderInput
    ];

    for (const control of controls) {
      if (control) {
        control.disabled = Boolean(locked);
      }
    }

    if (locked) {
      executeButton.disabled = true;
    } else {
      executeButton.disabled = !Boolean(
        currentPreflight
        && currentPreflight.can_execute
      );
    }
  }

  function setFileExecutionStatus(
    relativePath,
    text,
    variant,
    detail
  ) {
    for (
      const row
      of fileBody.querySelectorAll("tr")
    ) {
      if (
        row.dataset.relativePath
        !== relativePath
      ) {
        continue;
      }

      const statusCell = row.lastElementChild;

      statusCell.replaceChildren();
      statusCell.appendChild(
        createBadge(
          text,
          variant
        )
      );

      if (detail) {
        statusCell.title = detail;
      } else {
        statusCell.removeAttribute("title");
      }

      break;
    }
  }

  function getExecutionState() {
    return {
      selectedFiles: selectedFiles.slice(),
      descriptors: descriptors.map(
        function (item) {
          return {
            relative_path: item.relative_path,
            size: item.size
          };
        }
      ),
      directories: directories.slice(),
      preflight: currentPreflight,
      preflightValidatedAt: preflightValidatedAt,
      currentPath: currentPath,
      csrfToken: csrfToken
    };
  }

  window.IntasaFolderUploadPreview = Object.freeze({
    getState: getExecutionState,
    relativePathForFile: relativePathForFile,
    refreshValidation: validateSelection,
    resetPreview: resetPreview,
    setStatus: setStatus,
    setInteractionLocked: setInteractionLocked,
    setFileStatus: setFileExecutionStatus,
    setExecuteEnabled: function (enabled) {
      executeButton.disabled = !Boolean(enabled);
    }
  });

})();
