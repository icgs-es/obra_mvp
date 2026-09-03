/*
 * INTASA Documents · Folder Upload Execution · P2B
 *
 * Ejecución real:
 * - lotes pequeños y secuenciales;
 * - progreso de transferencia;
 * - estado individual;
 * - reintento de fallidos;
 * - finalización y actividad separadas.
 */
(function () {
  "use strict";

  const api = window.IntasaFolderUploadPreview;
  const panel = document.getElementById(
    "folderUploadPreview"
  );
  const executeButton = document.getElementById(
    "folderUploadExecuteButton"
  );

  if (!api || !panel || !executeButton) {
    return;
  }

  const executeUrl =
    panel.dataset.executeUrl || "";

  const retryButton = document.getElementById(
    "folderUploadRetryButton"
  );
  const refreshButton = document.getElementById(
    "folderUploadRefreshButton"
  );
  const progressSection = document.getElementById(
    "folderUploadProgressSection"
  );
  const progressTitle = document.getElementById(
    "folderUploadProgressTitle"
  );
  const progressText = document.getElementById(
    "folderUploadProgressText"
  );
  const progressBar = document.getElementById(
    "folderUploadProgressBar"
  );
  const batchProgress = document.getElementById(
    "folderUploadBatchProgress"
  );
  const footerMessage = document.getElementById(
    "folderUploadFooterMessage"
  );
  const activityWarning = document.getElementById(
    "folderUploadActivityWarning"
  );

  const countElements = {
    uploaded: document.getElementById(
      "folderUploadUploadedCount"
    ),
    renamed: document.getElementById(
      "folderUploadRenamedCount"
    ),
    replaced: document.getElementById(
      "folderUploadReplacedCount"
    ),
    skipped: document.getElementById(
      "folderUploadSkippedCount"
    ),
    failed: document.getElementById(
      "folderUploadFailedCount"
    )
  };

  const fatalCodes = new Set([
    "expired_token",
    "invalid_token",
    "manifest_signature_mismatch",
    "token_user_mismatch",
    "token_team_mismatch",
    "destination_changed",
    "policy_changed",
    "permission_denied"
  ]);

  const clientBatchFileLimit = 8;
  const clientBatchByteLimit =
    16 * 1024 * 1024;

  let activeState = null;
  let signedFileMap = new Map();
  let resultByPath = new Map();
  let failedPaths = new Set();
  let activityFileIds = new Set();
  let createdFolderPaths = new Set();
  let uploadActive = false;
  let operationFinalized = false;
  let finalizationPending = false;

  function show(element, visible) {
    if (element) {
      element.classList.toggle(
        "d-none",
        !visible
      );
    }
  }

  function setText(element, value) {
    if (element) {
      element.textContent = String(value);
    }
  }

  function errorMessage(error) {
    if (error && error.message) {
      return error.message;
    }

    return "Se produjo un error durante la subida.";
  }

  function setProgress(
    fraction,
    completed,
    total,
    message
  ) {
    const bounded = Math.max(
      0,
      Math.min(
        Number(fraction || 0),
        1
      )
    );

    const percentage = Math.round(
      bounded * 100
    );

    progressBar.style.width =
      percentage + "%";

    progressBar.textContent =
      percentage + " %";

    progressBar.setAttribute(
      "aria-valuenow",
      String(percentage)
    );

    setText(
      progressText,
      completed.toLocaleString("es-ES")
      + " de "
      + total.toLocaleString("es-ES")
    );

    if (message) {
      setText(
        batchProgress,
        message
      );
    }
  }

  function resultLabel(status) {
    const values = {
      uploaded: {
        text: "Subido",
        variant: "success"
      },
      renamed: {
        text: "Renombrado",
        variant: "primary"
      },
      replaced: {
        text: "Reemplazado",
        variant: "warning"
      },
      skipped: {
        text: "Omitido",
        variant: "secondary"
      },
      error: {
        text: "Error",
        variant: "danger"
      },
      cancelled: {
        text: "Cancelado",
        variant: "danger"
      }
    };

    return values[status] || {
      text: "Procesado",
      variant: "secondary"
    };
  }

  function normalizedStatus(item) {
    // P2B2_REFERENCE_ERROR_STATUS
    if (
      String(
        item.reference_error || ""
      ).trim()
    ) {
      return "error";
    }

    let status = String(
      item.status || ""
    ).toLowerCase();

    if (
      status === "uploaded"
      && item.collision_policy === "replace"
    ) {
      const signed = signedFileMap.get(
        item.relative_path
      );

      if (
        signed
        && signed.collision_kind
      ) {
        status = "replaced";
      }
    }

    return status || "error";
  }

  function renderCounters() {
    const counts = {
      uploaded: 0,
      renamed: 0,
      replaced: 0,
      skipped: 0,
      failed: 0
    };

    for (const item of resultByPath.values()) {
      if (
        item.status === "error"
        || item.status === "cancelled"
      ) {
        counts.failed += 1;
      } else if (
        Object.prototype.hasOwnProperty.call(
          counts,
          item.status
        )
      ) {
        counts[item.status] += 1;
      }
    }

    for (
      const [name, element]
      of Object.entries(countElements)
    ) {
      setText(
        element,
        counts[name].toLocaleString("es-ES")
      );
    }

    return counts;
  }

  function markResult(item) {
    const relativePath = String(
      item.relative_path || ""
    );

    if (!relativePath) {
      return;
    }

    const status = normalizedStatus(item);
    const detail = String(
      item.error
      || item.reference_error
      || item.target_path
      || ""
    );

    resultByPath.set(
      relativePath,
      {
        status: status,
        error: detail,
        target_path: item.target_path || ""
      }
    );

    if (
      status === "error"
      || status === "cancelled"
    ) {
      failedPaths.add(relativePath);
    } else {
      failedPaths.delete(relativePath);
    }

    const label = resultLabel(status);

    api.setFileStatus(
      relativePath,
      label.text,
      label.variant,
      detail
    );
  }

  function markRequestFailure(
    paths,
    error
  ) {
    const message = errorMessage(error);

    for (const path of paths) {
      failedPaths.add(path);

      resultByPath.set(
        path,
        {
          status: "error",
          error: message,
          target_path: ""
        }
      );

      api.setFileStatus(
        path,
        "Error",
        "danger",
        message
      );
    }

    renderCounters();
  }

  function mergeResponse(
    data,
    expectedPaths
  ) {
    for (
      const value
      of data.indexed_file_ids || []
    ) {
      const id = Number(value);

      if (Number.isInteger(id) && id > 0) {
        activityFileIds.add(id);
      }
    }

    const result = data.result || {};

    for (
      const folder
      of result.created_folders || []
    ) {
      createdFolderPaths.add(
        String(folder)
      );
    }

    const returnedPaths = new Set();

    for (const item of result.files || []) {
      returnedPaths.add(
        String(item.relative_path || "")
      );

      markResult(item);
    }

    for (
      const referenceError
      of data.reference_errors || []
    ) {
      markResult({
        relative_path:
          referenceError.relative_path,
        target_path:
          referenceError.target_path,
        status: "error",
        error: referenceError.error
      });

      returnedPaths.add(
        String(
          referenceError.relative_path || ""
        )
      );
    }

    for (const path of expectedPaths) {
      if (!returnedPaths.has(path)) {
        markResult({
          relative_path: path,
          status: "error",
          error: (
            "El servidor no devolvió un resultado "
            + "para este archivo."
          )
        });
      }
    }

    renderCounters();
  }

  function buildFileMap(state) {
    const fileMap = new Map();

    for (const file of state.selectedFiles) {
      const relativePath =
        api.relativePathForFile(file);

      fileMap.set(
        relativePath,
        file
      );
    }

    return fileMap;
  }

  function buildBatches(
    paths,
    fileMap,
    serverLimit
  ) {
    const maxFiles = Math.max(
      1,
      Math.min(
        Number(serverLimit || 1),
        clientBatchFileLimit
      )
    );

    const batches = [];
    let current = [];
    let currentBytes = 0;

    for (const path of paths) {
      const file = fileMap.get(path);

      if (!file) {
        throw new Error(
          "No se encontró el archivo local: "
          + path
        );
      }

      const size = Number(file.size || 0);

      const exceedsCount =
        current.length >= maxFiles;

      const exceedsBytes =
        current.length > 0
        && currentBytes + size
          > clientBatchByteLimit;

      if (exceedsCount || exceedsBytes) {
        batches.push(current);
        current = [];
        currentBytes = 0;
      }

      current.push(path);
      currentBytes += size;
    }

    if (current.length) {
      batches.push(current);
    }

    return batches;
  }

  function parseResponse(xhr) {
    let data = null;

    try {
      data = JSON.parse(
        xhr.responseText || ""
      );
    } catch (error) {
      const invalid = new Error(
        xhr.responseURL
        && !xhr.responseURL.includes(
          "/folder-upload/execute/"
        )
          ? (
              "La sesión ha caducado o el servidor "
              + "ha redirigido la petición."
            )
          : (
              "El servidor no devolvió una "
              + "respuesta JSON válida."
            )
      );

      invalid.status = xhr.status;
      throw invalid;
    }

    if (
      xhr.status < 200
      || xhr.status >= 300
      || !data
      || data.ok !== true
    ) {
      const message =
        data
        && data.error
        && data.error.message
          ? data.error.message
          : "El servidor rechazó el lote.";

      const failure = new Error(message);

      failure.status = xhr.status;
      failure.code =
        data
        && data.error
          ? data.error.code
          : "";

      failure.data = data;

      throw failure;
    }

    return data;
  }

  function sendMultipart(
    formData,
    progressCallback
  ) {
    return new Promise(
      function (resolve, reject) {
        const xhr = new XMLHttpRequest();

        xhr.open(
          "POST",
          executeUrl,
          true
        );

        xhr.withCredentials = true;

        xhr.setRequestHeader(
          "X-CSRFToken",
          activeState.csrfToken
        );

        xhr.setRequestHeader(
          "X-Requested-With",
          "XMLHttpRequest"
        );

        xhr.upload.addEventListener(
          "progress",
          function (event) {
            if (
              event.lengthComputable
              && progressCallback
            ) {
              progressCallback(
                event.loaded / event.total
              );
            }
          }
        );

        xhr.addEventListener(
          "load",
          function () {
            try {
              resolve(
                parseResponse(xhr)
              );
            } catch (error) {
              reject(error);
            }
          }
        );

        xhr.addEventListener(
          "error",
          function () {
            reject(
              new Error(
                "No se pudo comunicar con el servidor."
              )
            );
          }
        );

        xhr.addEventListener(
          "abort",
          function () {
            reject(
              new Error(
                "La petición fue interrumpida."
              )
            );
          }
        );

        xhr.send(formData);
      }
    );
  }

  function createBatchFormData(
    paths,
    fileMap,
    batchDirectories
  ) {
    const formData = new FormData();

    formData.append(
      "token",
      activeState.preflight.token
    );

    formData.append(
      "manifest",
      JSON.stringify(
        activeState.preflight.manifest
      )
    );

    formData.append(
      "directories",
      JSON.stringify(
        batchDirectories || []
      )
    );

    formData.append(
      "finalize",
      "0"
    );

    for (const path of paths) {
      const file = fileMap.get(path);

      formData.append(
        "files",
        file,
        file.name
      );

      formData.append(
        "relpath",
        path
      );
    }

    return formData;
  }

  function createFinalizeFormData() {
    const formData = new FormData();

    formData.append(
      "token",
      activeState.preflight.token
    );

    formData.append(
      "manifest",
      JSON.stringify(
        activeState.preflight.manifest
      )
    );

    formData.append(
      "directories",
      "[]"
    );

    formData.append(
      "finalize",
      "1"
    );

    formData.append(
      "activity_file_ids",
      JSON.stringify(
        Array.from(activityFileIds)
      )
    );

    formData.append(
      "created_folders_total",
      String(createdFolderPaths.size)
    );

    return formData;
  }

  function initializeOperation(state) {
    activeState = state;
    resultByPath = new Map();
    failedPaths = new Set();
    activityFileIds = new Set();
    createdFolderPaths = new Set();
    operationFinalized = false;
    finalizationPending = false;

    signedFileMap = new Map();

    for (
      const entry
      of state.preflight.manifest.files || []
    ) {
      signedFileMap.set(
        entry.relative_path,
        entry
      );
    }

    for (const descriptor of state.descriptors) {
      api.setFileStatus(
        descriptor.relative_path,
        "En cola",
        "light border text-dark",
        ""
      );
    }

    renderCounters();

    show(progressSection, true);
    show(retryButton, false);
    show(refreshButton, false);
    show(activityWarning, false);

    setText(
      footerMessage,
      (
        "No cierres esta página mientras "
        + "se procesa la carpeta."
      )
    );

    setProgress(
      0,
      0,
      state.descriptors.length,
      "Preparando lotes."
    );
  }

  async function ensureFreshPreflight() {
    let state = api.getState();

    if (
      !state.preflight
      || !state.preflight.can_execute
      || !state.preflight.token
      || !state.preflight.manifest
    ) {
      throw new Error(
        "La carpeta debe validarse antes de subirla."
      );
    }

    const maxAgeMilliseconds =
      Number(
        state.preflight
          .token_max_age_seconds || 0
      ) * 1000;

    const currentAge =
      Date.now()
      - Number(
          state.preflightValidatedAt || 0
        );

    if (
      maxAgeMilliseconds > 0
      && currentAge
        > maxAgeMilliseconds - 60000
    ) {
      api.setStatus(
        "La autorización está próxima a caducar. "
        + "Revalidando la carpeta…",
        "info",
        true
      );

      await api.refreshValidation();

      state = api.getState();
    }

    if (
      !state.preflight
      || !state.preflight.can_execute
      || !state.preflight.token
    ) {
      throw new Error(
        "La carpeta no dispone de una "
        + "prevalidación ejecutable."
      );
    }

    if (
      state.selectedFiles.length
      !== state.descriptors.length
    ) {
      throw new Error(
        "La selección local ha cambiado."
      );
    }

    return state;
  }

  async function finalizeOperation() {
    finalizationPending = true;

    setText(
      progressTitle,
      "Finalizando operación"
    );

    setProgress(
      1,
      activeState.descriptors.length,
      activeState.descriptors.length,
      "Registrando referencias y actividad."
    );

    try {
      const data = await sendMultipart(
        createFinalizeFormData()
      );

      finalizationPending = false;
      operationFinalized = true;

      const counts = renderCounters();

      progressBar.classList.remove(
        "progress-bar-animated"
      );

      api.setStatus(
        (
          "Carpeta procesada correctamente. "
          + "Subidos: "
          + counts.uploaded
          + ", renombrados: "
          + counts.renamed
          + ", reemplazados: "
          + counts.replaced
          + ", omitidos: "
          + counts.skipped
          + "."
        ),
        "success",
        false
      );

      if (data.activity_error) {
        activityWarning.textContent =
          (
            "Los documentos se procesaron, pero "
            + "falló el registro de actividad: "
            + data.activity_error
          );

        show(activityWarning, true);
      } else {
        const changed =
          counts.uploaded
          + counts.renamed
          + counts.replaced;

        if (
          changed > 0
          && !data.activity_registered
        ) {
          activityWarning.textContent =
            (
              "Los documentos se procesaron, pero "
              + "no se confirmó el registro "
              + "de actividad."
            );

          show(activityWarning, true);
        }
      }

      setText(
        footerMessage,
        (
          "La operación terminó. Actualiza el "
          + "explorador para ver la carpeta."
        )
      );

      show(retryButton, false);
      show(refreshButton, true);

    } catch (error) {
      finalizationPending = true;

      api.setStatus(
        (
          "Los lotes terminaron, pero no se pudo "
          + "cerrar la operación: "
          + errorMessage(error)
        ),
        "warning",
        false
      );

      retryButton.textContent =
        "Reintentar cierre";

      show(retryButton, true);
      show(refreshButton, true);

      setText(
        footerMessage,
        (
          "No cambies la selección. Reintenta "
          + "el cierre de la operación."
        )
      );
    }
  }

  async function runPaths(
    paths,
    isRetry
  ) {
    const fileMap = buildFileMap(
      activeState
    );

    const batches = buildBatches(
      paths,
      fileMap,
      activeState.preflight.batch_file_limit
    );

    let completedInRun = 0;
    let fatalFailure = null;

    setText(
      progressTitle,
      isRetry
        ? "Reintentando archivos"
        : "Subiendo carpeta"
    );

    show(retryButton, false);
    show(refreshButton, false);

    for (
      let index = 0;
      index < batches.length;
      index += 1
    ) {
      const batch = batches[index];

      setText(
        batchProgress,
        (
          "Lote "
          + (index + 1).toLocaleString("es-ES")
          + " de "
          + batches.length.toLocaleString("es-ES")
          + " · "
          + batch.length.toLocaleString("es-ES")
          + " archivo(s)"
        )
      );

      for (const path of batch) {
        api.setFileStatus(
          path,
          "Subiendo",
          "info",
          ""
        );
      }

      const directoriesForBatch =
        !isRetry && index === 0
          ? activeState.directories
          : [];

      try {
        const data = await sendMultipart(
          createBatchFormData(
            batch,
            fileMap,
            directoriesForBatch
          ),
          function (batchFraction) {
            const fraction =
              (
                completedInRun
                + batch.length * batchFraction
              )
              / paths.length;

            setProgress(
              fraction,
              completedInRun,
              paths.length,
              (
                "Transmitiendo lote "
                + (index + 1)
                + " de "
                + batches.length
              )
            );
          }
        );

        mergeResponse(
          data,
          batch
        );

      } catch (error) {
        markRequestFailure(
          batch,
          error
        );

        if (
          error
          && fatalCodes.has(error.code)
        ) {
          fatalFailure = error;

          const remaining = batches
            .slice(index + 1)
            .flat();

          markRequestFailure(
            remaining,
            new Error(
              "No procesado porque la autorización "
              + "de la operación dejó de ser válida."
            )
          );

          break;
        }
      }

      completedInRun += batch.length;

      setProgress(
        completedInRun / paths.length,
        completedInRun,
        paths.length,
        (
          "Lote "
          + (index + 1)
          + " completado."
        )
      );
    }

    if (failedPaths.size === 0) {
      await finalizeOperation();
      return;
    }

    const failureText = fatalFailure
      ? errorMessage(fatalFailure)
      : (
          failedPaths.size.toLocaleString("es-ES")
          + " archivo(s) requieren reintento."
        );

    api.setStatus(
      (
        "La operación quedó incompleta. "
        + failureText
      ),
      "warning",
      false
    );

    retryButton.textContent =
      "Reintentar fallidos";

    show(retryButton, true);
    show(refreshButton, true);

    setText(
      footerMessage,
      (
        "No cambies la selección ni la política. "
        + "Reintenta los archivos fallidos."
      )
    );
  }

  async function startOperation() {
    if (uploadActive) {
      return;
    }

    uploadActive = true;

    try {
      const state =
        await ensureFreshPreflight();

      initializeOperation(state);

      api.setInteractionLocked(true);
      api.setExecuteEnabled(false);

      const paths = state.descriptors.map(
        function (item) {
          return item.relative_path;
        }
      );

      await runPaths(
        paths,
        false
      );

    } catch (error) {
      api.setStatus(
        errorMessage(error),
        "danger",
        false
      );

      if (!activeState) {
        api.setInteractionLocked(false);
      }

    } finally {
      uploadActive = false;
      api.setExecuteEnabled(false);
    }
  }

  async function retryOperation() {
    if (uploadActive || operationFinalized) {
      return;
    }

    uploadActive = true;
    retryButton.disabled = true;

    try {
      if (finalizationPending) {
        await finalizeOperation();
      } else {
        const retryPaths =
          Array.from(failedPaths);

        if (!retryPaths.length) {
          await finalizeOperation();
        } else {
          await runPaths(
            retryPaths,
            true
          );
        }
      }
    } finally {
      uploadActive = false;
      retryButton.disabled = false;
      api.setExecuteEnabled(false);
    }
  }

  executeButton.addEventListener(
    "click",
    startOperation
  );

  retryButton.addEventListener(
    "click",
    retryOperation
  );

  refreshButton.addEventListener(
    "click",
    function () {
      window.location.reload();
    }
  );

  window.addEventListener(
    "beforeunload",
    function (event) {
      if (!uploadActive) {
        return;
      }

      event.preventDefault();
      event.returnValue = "";
    }
  );
})();
