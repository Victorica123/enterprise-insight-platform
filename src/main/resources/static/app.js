const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const tokenBar = document.getElementById("tokenBar");
const tokenText = document.getElementById("tokenText");
const taskIdInput = document.getElementById("taskId");
const taskField = document.getElementById("taskField");
const videoFileInput = document.getElementById("videoFile");
const dropzone = document.getElementById("dropzone");
const dropzoneEmpty = document.getElementById("dropzoneEmpty");
const dropzoneFile = document.getElementById("dropzoneFile");
const fileNameEl = document.getElementById("fileName");
const fileSizeEl = document.getElementById("fileSize");
const progressFill = document.getElementById("progressFill");
const progressText = document.getElementById("progressText");
const progressPercent = document.getElementById("progressPercent");
const transcriptArea = document.getElementById("transcript");
const summaryArea = document.getElementById("summary");
const copyResultButton = document.getElementById("copyResult");
const downloadResultButton = document.getElementById("downloadResult");
const messagesArea = document.getElementById("messages");
const statusPill = document.getElementById("statusPill");
const quotaPill = document.getElementById("quotaPill");
const labRuntimeMode = document.getElementById("labRuntimeMode");
const labRuntimeMeta = document.getElementById("labRuntimeMeta");
const labTaskCount = document.getElementById("labTaskCount");
const runAsyncLabButton = document.getElementById("runAsyncLab");
const cleanupAsyncLabButton = document.getElementById("cleanupAsyncLab");
const labEls = {
    accepted: document.getElementById("labAccepted"),
    rejected: document.getElementById("labRejected"),
    backend: document.getElementById("labBackend"),
    active: document.getElementById("labActive"),
    completed: document.getElementById("labCompleted"),
    elapsed: document.getElementById("labElapsed"),
    progress: document.getElementById("labProgress"),
    localResult: document.getElementById("labLocalResult"),
    mqResult: document.getElementById("labMqResult")
};
const loginButton = document.getElementById("loginButton");
const registerButton = document.getElementById("registerButton");
const uploadButton = document.getElementById("uploadButton");
const refreshButton = document.getElementById("refreshButton");
const myVideosCard = document.getElementById("myVideosCard");
const loadMyVideosButton = document.getElementById("loadMyVideos");
const videoList = document.getElementById("videoList");
const videoPreview = document.getElementById("videoPreview");
const videoPlayer = document.getElementById("videoPlayer");
const pipelineSteps = Array.from(document.querySelectorAll(".pipeline-step"));
const strategyOptions = Array.from(document.querySelectorAll(".strategy-option"));

const metricEls = {
    mode: document.getElementById("metricMode"),
    total: document.getElementById("metricTotal"),
    size: document.getElementById("metricSize"),
    speed: document.getElementById("metricSpeed"),
    chunks: document.getElementById("metricChunks"),
    avgChunk: document.getElementById("metricAvgChunk"),
    init: document.getElementById("metricInit"),
    merge: document.getElementById("metricMerge"),
    singleCompare: document.getElementById("singleCompare"),
    chunkCompare: document.getElementById("chunkCompare"),
    directCompare: document.getElementById("directCompare")
};

const CHUNK_SIZE = 2 * 1024 * 1024;
const CHUNK_CONCURRENCY = 4;
const PIPELINE_ORDER = ["UPLOADING", "QUEUED", "TRANSCRIBING", "SUMMARIZING", "COMPLETED"];
const MODE_LABELS = {
    single: "普通上传",
    chunk: "Redis 并发分片",
    direct: "对象存储直传"
};

let token = localStorage.getItem("vp_token") || "";
let pollingTimer = null;
let currentFile = null;
let uploadMode = localStorage.getItem("vp_upload_mode") || "single";
let activeMetrics = null;
let currentTask = null;
let taskQuota = { limited: false, remainingSlots: -1 };
let runtimeInfo = null;
let labRun = null;
let labPollingTimer = null;
let lastMetrics = {
    single: null,
    chunk: null,
    direct: null
};

document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        const targetId = tab.dataset.target;
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach((pane) => pane.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(targetId).classList.add("active");
    });
});

strategyOptions.forEach((option) => {
    option.addEventListener("click", () => {
        setUploadMode(option.dataset.uploadMode);
    });
});

setUploadMode(uploadMode);
resetActiveMetrics();
renderSavedLabResults();

if (token) {
    showLoggedIn("已恢复登录状态");
    loadMyVideos();
}

videoFileInput.addEventListener("change", () => {
    const file = videoFileInput.files?.[0];
    if (!file) {
        resetDropzone();
        return;
    }

    currentFile = file;
    fileNameEl.textContent = file.name;
    fileSizeEl.textContent = formatSize(file.size);
    dropzoneEmpty.style.display = "none";
    dropzoneFile.style.display = "block";
    dropzone.classList.add("has-file");
    dropzone.classList.remove("is-dragover");
    updateUploadButtonState();
    resetActiveMetrics();
});

dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragover");
});

dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-dragover");
});

dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragover");
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    videoFileInput.files = event.dataTransfer.files;
    videoFileInput.dispatchEvent(new Event("change"));
});

registerButton.addEventListener("click", async () => {
    await authenticate("/api/auth/register", registerButton);
});

loginButton.addEventListener("click", async () => {
    await authenticate("/api/auth/login", loginButton);
});

uploadButton.addEventListener("click", async () => {
    if (uploadMode === "single") {
        await uploadSingleFile();
    } else if (uploadMode === "chunk") {
        await uploadFileChunked();
    } else {
        await uploadFileDirect();
    }
});

refreshButton.addEventListener("click", async () => {
    await fetchTask();
});

loadMyVideosButton.addEventListener("click", loadMyVideos);
copyResultButton.addEventListener("click", copyTaskResult);
downloadResultButton.addEventListener("click", downloadTaskResult);
runAsyncLabButton.addEventListener("click", runAsyncLab);
cleanupAsyncLabButton.addEventListener("click", cleanupAsyncLab);

// 历史列表用事件委托：无论重渲染多少次都只在容器上绑定一次，避免逐项重复绑定与监听泄漏。
videoList.addEventListener("click", (event) => {
    const actionEl = event.target.closest("[data-action]");
    if (!actionEl) return;
    const item = actionEl.closest(".video-item");
    if (!item) return;
    const taskId = item.dataset.taskId;
    switch (actionEl.dataset.action) {
        case "select":
            selectTask(taskId);
            break;
        case "delete":
            deleteTask(taskId, actionEl);
            break;
        case "retry":
            retryTask(taskId, actionEl);
            break;
        default:
            break;
    }
});

function setUploadMode(mode) {
    uploadMode = ["single", "chunk", "direct"].includes(mode) ? mode : "single";
    localStorage.setItem("vp_upload_mode", uploadMode);
    strategyOptions.forEach((option) => {
        const active = option.dataset.uploadMode === uploadMode;
        option.classList.toggle("active", active);
        option.setAttribute("aria-pressed", active ? "true" : "false");
    });
}

function resetDropzone() {
    currentFile = null;
    dropzoneEmpty.style.display = "grid";
    dropzoneFile.style.display = "none";
    dropzone.classList.remove("has-file", "is-dragover");
    setProgress(0, "准备上传");
    uploadButton.disabled = true;
    resetActiveMetrics();
}

function resetActiveMetrics() {
    activeMetrics = null;
    metricEls.mode.textContent = "尚未上传";
    metricEls.total.textContent = "-";
    metricEls.size.textContent = currentFile ? formatSize(currentFile.size) : "-";
    metricEls.speed.textContent = "-";
    metricEls.chunks.textContent = "-";
    metricEls.avgChunk.textContent = "-";
    metricEls.init.textContent = "-";
    metricEls.merge.textContent = "-";
    renderMetricCompare();
}

function renderLiveMetrics(metrics) {
    activeMetrics = metrics;
    metricEls.mode.textContent = MODE_LABELS[metrics.mode];
    metricEls.total.textContent = metrics.totalMs ? formatDuration(metrics.totalMs) : "进行中";
    metricEls.size.textContent = formatSize(metrics.fileSize);
    metricEls.speed.textContent = metrics.totalMs ? formatSpeed(metrics.fileSize, metrics.totalMs) : "-";
    metricEls.chunks.textContent = metrics.totalChunks ? `${metrics.totalChunks} 个` : "1 个";
    metricEls.avgChunk.textContent = metrics.chunkDurations.length ? formatDuration(average(metrics.chunkDurations)) : "-";
    metricEls.init.textContent = metrics.initMs ? formatDuration(metrics.initMs) : "-";
    metricEls.merge.textContent = metrics.mergeMs ? formatDuration(metrics.mergeMs) : "-";
}

function finishMetrics(metrics) {
    metrics.totalMs = performance.now() - metrics.startedAt;
    renderLiveMetrics(metrics);
    lastMetrics[metrics.mode] = snapshotMetrics(metrics);
    renderMetricCompare();
}

function snapshotMetrics(metrics) {
    return {
        mode: metrics.mode,
        fileSize: metrics.fileSize,
        totalChunks: metrics.totalChunks,
        totalMs: metrics.totalMs,
        chunkDurations: [...metrics.chunkDurations],
        initMs: metrics.initMs,
        mergeMs: metrics.mergeMs
    };
}

function renderMetricCompare() {
    metricEls.singleCompare.textContent = lastMetrics.single
        ? `${formatDuration(lastMetrics.single.totalMs)} / ${formatSpeed(lastMetrics.single.fileSize, lastMetrics.single.totalMs)}`
        : "尚未测试";
    metricEls.chunkCompare.textContent = lastMetrics.chunk
        ? `${formatDuration(lastMetrics.chunk.totalMs)} / ${lastMetrics.chunk.totalChunks} 片 / 并发 ${CHUNK_CONCURRENCY}`
        : "尚未测试";
    if (metricEls.directCompare) {
        metricEls.directCompare.textContent = lastMetrics.direct
            ? `${formatDuration(lastMetrics.direct.totalMs)} / ${formatSpeed(lastMetrics.direct.fileSize, lastMetrics.direct.totalMs)}`
            : "尚未测试";
    }
}

function createMetrics(mode) {
    const totalChunks = mode === "chunk" && currentFile ? Math.ceil(currentFile.size / CHUNK_SIZE) : 1;
    return {
        mode,
        fileSize: currentFile?.size || 0,
        totalChunks,
        chunkDurations: [],
        initMs: 0,
        mergeMs: 0,
        totalMs: 0,
        startedAt: performance.now()
    };
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDuration(ms) {
    if (!Number.isFinite(ms)) return "-";
    if (ms < 1000) return `${Math.round(ms)} ms`;
    return `${(ms / 1000).toFixed(2)} s`;
}

function formatSpeed(bytes, ms) {
    if (!bytes || !ms) return "-";
    const mb = bytes / 1024 / 1024;
    const seconds = ms / 1000;
    return `${(mb / seconds).toFixed(2)} MB/s`;
}

function average(values) {
    return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function setProgress(percent, text) {
    progressFill.style.width = `${percent}%`;
    progressPercent.textContent = `${Math.round(percent)}%`;
    progressText.textContent = text || `${Math.round(percent)}%`;
}

function showLoggedIn(message) {
    tokenBar.style.display = "flex";
    tokenText.textContent = message;
    myVideosCard.style.display = "block";
    quotaPill.hidden = false;
    updateUploadButtonState();
    loadRuntimeInfo();
}

function clearAuthState(message = "登录已过期，请重新登录") {
    token = "";
    localStorage.removeItem("vp_token");
    tokenBar.style.display = "none";
    tokenText.textContent = "";
    quotaPill.hidden = true;
    taskQuota = { limited: false, remainingSlots: -1 };
    myVideosCard.style.display = "none";
    uploadButton.disabled = true;
    refreshButton.disabled = true;
    currentTask = null;
    transcriptArea.value = "";
    summaryArea.value = "";
    updateResultActions();
    stopPolling();
    stopLabPolling();
    runAsyncLabButton.disabled = true;
    writeMessage(message, true);
}

class ApiError extends Error {
    constructor(message, status, handled = false) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.handled = handled; // true 表示错误已被上报（如登录过期已提示），调用方不必重复 writeMessage
    }
}

// 统一封装后端 JSON API 调用，收敛「加 token 头 + 解析 ApiResponse 包裹 + 校验 success」这套重复样板。
// - auth:false 用于登录/注册等尚未持有 token 的请求；
// - json 传对象时自动 JSON.stringify 并设置 Content-Type；body 传 FormData 等原始体则原样发送；
// - 401/403 自动清理登录态并抛出 handled 错误；
// - soft:true 时任何失败都静默返回 null（不抛错、不清理登录态），用于播放/状态查询等非关键读取。
// 成功返回 result.data；失败抛 ApiError(message, status)。
async function apiRequest(path, { method = "GET", json, body, headers = {}, auth = true, soft = false } = {}) {
    const finalHeaders = { ...headers };
    if (auth && token) {
        finalHeaders.Authorization = `Bearer ${token}`;
    }
    let finalBody = body;
    if (json !== undefined) {
        finalHeaders["Content-Type"] = "application/json";
        finalBody = JSON.stringify(json);
    }

    let response;
    try {
        response = await fetch(path, { method, headers: finalHeaders, body: finalBody });
    } catch (error) {
        if (soft) return null;
        throw new ApiError("网络请求失败，请检查连接后重试", 0);
    }

    if (!soft && (response.status === 401 || response.status === 403)) {
        clearAuthState();
        throw new ApiError("登录已过期，请重新登录", response.status, true);
    }

    let result = null;
    try {
        result = await response.json();
    } catch (error) {
        result = null;
    }

    if (!response.ok || !result || result.success === false) {
        if (soft) return null;
        throw new ApiError((result && result.message) || `请求失败（HTTP ${response.status}）`, response.status);
    }
    return result ? result.data : null;
}

// 统一错误上报：已被处理过的错误（如登录过期）不再重复写日志。
function reportError(error) {
    if (!error || !error.handled) {
        writeMessage(error?.message || "未知错误", true);
    }
}

async function authenticate(path, triggerButton) {
    const isRegister = path.includes("register");
    if (triggerButton) triggerButton.disabled = true;
    try {
        writeMessage(isRegister ? "正在注册账号..." : "正在登录...");
        const data = await apiRequest(path, {
            method: "POST",
            auth: false,
            json: {
                username: usernameInput.value.trim(),
                password: passwordInput.value
            }
        });

        token = data.token;
        localStorage.setItem("vp_token", token);
        showLoggedIn(`已登录：${data.username}`);
        writeMessage(`${isRegister ? "注册" : "登录"}成功，用户：${data.username}`);
        loadMyVideos();
    } catch (error) {
        reportError(error);
    } finally {
        if (triggerButton) triggerButton.disabled = false;
    }
}

function assertCanUpload() {
    if (!token) {
        writeMessage("请先登录或注册", true);
        return false;
    }
    if (!currentFile) {
        writeMessage("请先选择视频文件", true);
        return false;
    }
    return true;
}

async function uploadSingleFile() {
    if (!assertCanUpload()) return;

    const metrics = createMetrics("single");
    writeMessage(`开始普通上传：${currentFile.name}，大小 ${formatSize(currentFile.size)}`);
    setStatus("上传中", "running");
    setPipelineStatus("UPLOADING");
    setProgress(8, "准备普通上传");
    renderLiveMetrics(metrics);
    uploadButton.disabled = true;
    refreshButton.disabled = true;

    try {
        const formData = new FormData();
        formData.append("file", currentFile, currentFile.name);

        const data = await apiRequest("/api/media/upload/file", {
            method: "POST",
            body: formData
        });

        setProgress(100, "普通上传完成");
        finishMetrics(metrics);
        writeMessage(`普通上传完成，总耗时 ${formatDuration(metrics.totalMs)}，吞吐 ${formatSpeed(metrics.fileSize, metrics.totalMs)}`);
        handleUploadSuccess(data.taskId, data.status);
    } catch (error) {
        setProgress(0, "上传失败");
        setStatus("上传失败", "error");
        reportError(error);
        updateUploadButtonState();
    }
}

async function uploadFileChunked() {
    if (!assertCanUpload()) return;

    const metrics = createMetrics("chunk");
    writeMessage(`开始 Redis 并发分片上传：${currentFile.name}，${metrics.totalChunks} 个分片，并发 ${CHUNK_CONCURRENCY}`);
    setStatus("初始化", "running");
    setPipelineStatus("UPLOADING");
    setProgress(5, "初始化分片会话");
    renderLiveMetrics(metrics);
    uploadButton.disabled = true;
    refreshButton.disabled = true;

    try {
        let uploadId = null;
        let uploadedSet = new Set();

        // 计算内容指纹（秒传 / 去重 / 完整性校验的前提）
        const fileMd5 = await computeFileMd5(currentFile);

        // 断点续传：本地记录了同一文件未完成的会话时，先向服务端确认再续传，跳过已传分片。
        const saved = loadResume(currentFile);
        if (saved && saved.chunkSize === CHUNK_SIZE) {
            const status = await fetchUploadStatus(saved.uploadId);
            if (status && !status.completed && status.totalChunks === metrics.totalChunks) {
                uploadId = saved.uploadId;
                uploadedSet = new Set(status.uploadedChunks || []);
                writeMessage(`检测到未完成的上传，断点续传：已传 ${uploadedSet.size}/${metrics.totalChunks} 个分片`);
            } else {
                clearResume(currentFile);
            }
        }

        if (!uploadId) {
            const initStartedAt = performance.now();
            let initData;
            try {
                initData = await apiRequest("/api/media/upload/init", {
                    method: "POST",
                    json: {
                        fileName: currentFile.name,
                        fileSize: currentFile.size,
                        totalChunks: metrics.totalChunks,
                        chunkSize: CHUNK_SIZE,
                        fileMd5: fileMd5
                    }
                });
            } catch (error) {
                if (error.status === 503) {
                    throw new Error("Redis 分片上传未启用。请用 Redis 模式启动后再测试分片上传。");
                }
                throw error;
            } finally {
                metrics.initMs = performance.now() - initStartedAt;
                renderLiveMetrics(metrics);
            }

            if (initData.exists) {
                clearResume(currentFile);
                taskIdInput.value = initData.uploadId;
                taskField.style.display = "grid";
                setProgress(100, "文件已存在");
                setStatus("已完成", "success");
                finishMetrics(metrics);
                writeMessage(`文件已存在，触发秒传，总耗时 ${formatDuration(metrics.totalMs)}`);
                refreshButton.disabled = false;
                startPolling();
                return;
            }

            uploadId = initData.uploadId;
            uploadedSet = new Set(initData.uploadedChunks || []);
            saveResume(currentFile, uploadId);
        }

        await uploadChunksConcurrently(uploadId, metrics, uploadedSet);

        setProgress(95, "合并文件");
        setStatus("合并中", "running");
        const mergeStartedAt = performance.now();
        const mergeData = await apiRequest("/api/media/upload/merge", {
            method: "POST",
            json: { uploadId: uploadId }
        });
        metrics.mergeMs = performance.now() - mergeStartedAt;
        renderLiveMetrics(metrics);

        clearResume(currentFile);
        setProgress(100, "Redis 并发分片上传完成");
        finishMetrics(metrics);
        writeMessage(`Redis 并发分片上传完成，总耗时 ${formatDuration(metrics.totalMs)}，平均分片 ${formatDuration(average(metrics.chunkDurations))}`);
        handleUploadSuccess(mergeData.taskId, mergeData.status);
    } catch (error) {
        setProgress(0, "上传失败");
        setStatus("上传失败", "error");
        reportError(error);
        updateUploadButtonState();
    }
}

async function uploadChunksConcurrently(uploadId, metrics, uploadedSet = new Set()) {
    let nextIndex = 0;
    let completed = uploadedSet.size;

    async function worker() {
        while (nextIndex < metrics.totalChunks) {
            const chunkIndex = nextIndex;
            nextIndex += 1;
            if (uploadedSet.has(chunkIndex)) {
                continue; // 断点续传：跳过服务端已确认收到的分片
            }
            await uploadOneChunk(uploadId, chunkIndex, metrics);
            completed += 1;
            const percent = Math.round((completed / metrics.totalChunks) * 80) + 10;
            setProgress(percent, `上传分片 ${completed}/${metrics.totalChunks}`);
            setStatus("上传中", "running");
        }
    }

    const workerCount = Math.min(CHUNK_CONCURRENCY, metrics.totalChunks);
    await Promise.all(Array.from({ length: workerCount }, () => worker()));
}

// 对象存储直传：浏览器先向后端换取预签名 PUT 地址，把文件正文直接传到 S3/MinIO（不经应用服务器），
// 再回调后端确认对象已就位并建任务。大文件在此路径下不占用应用服务器带宽与磁盘。
async function uploadFileDirect() {
    if (!assertCanUpload()) return;

    const metrics = createMetrics("direct");
    writeMessage(`开始对象存储直传：${currentFile.name}，大小 ${formatSize(currentFile.size)}`);
    setStatus("初始化", "running");
    setPipelineStatus("UPLOADING");
    setProgress(5, "申请直传地址");
    renderLiveMetrics(metrics);
    uploadButton.disabled = true;
    refreshButton.disabled = true;

    try {
        // 1. 后端签发预签名 PUT 地址 + 绑定 owner 的一次性 uploadToken
        const initStartedAt = performance.now();
        let initData;
        try {
            initData = await apiRequest("/api/media/upload/direct/init", {
                method: "POST",
                json: { fileName: currentFile.name, fileSize: currentFile.size }
            });
        } catch (error) {
            if (error.status === 503) {
                throw new Error("对象存储直传需以 S3/MinIO 模式启动（app.storage.type=s3），请改用普通或分片上传");
            }
            throw error;
        } finally {
            metrics.initMs = performance.now() - initStartedAt;
            renderLiveMetrics(metrics);
        }

        // 2. 浏览器把文件直接 PUT 到对象存储（预签名只签 host，无需鉴权头/匹配 Content-Type）
        setStatus("上传中", "running");
        await putFileWithProgress(initData.uploadUrl, currentFile, (ratio) => {
            const percent = Math.round(ratio * 85) + 10;
            setProgress(percent, `直传对象存储 ${Math.round(ratio * 100)}%`);
        });

        // 3. 通知后端校验对象已存在并创建工作流任务
        setProgress(96, "确认直传结果");
        const completeData = await apiRequest("/api/media/upload/direct/complete", {
            method: "POST",
            json: { uploadToken: initData.uploadToken }
        });

        setProgress(100, "对象存储直传完成");
        finishMetrics(metrics);
        writeMessage(`对象存储直传完成，总耗时 ${formatDuration(metrics.totalMs)}，吞吐 ${formatSpeed(metrics.fileSize, metrics.totalMs)}`);
        handleUploadSuccess(completeData.taskId, completeData.status);
    } catch (error) {
        setProgress(0, "上传失败");
        setStatus("上传失败", "error");
        reportError(error);
        updateUploadButtonState();
    }
}

// 直传 PUT 用 XHR 而非 fetch：fetch 无法上报上传进度，大文件需要 upload.onprogress 驱动进度条。
// 对象存储返回裸 HTTP（无 ApiResponse 包裹），成功判据为 2xx。
function putFileWithProgress(url, file, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", url);
        xhr.upload.addEventListener("progress", (event) => {
            if (event.lengthComputable && onProgress) {
                onProgress(event.loaded / event.total);
            }
        });
        xhr.addEventListener("load", () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve();
            } else {
                reject(new Error(`对象存储拒绝了直传：HTTP ${xhr.status}`));
            }
        });
        xhr.addEventListener("error", () => reject(new Error("直传到对象存储失败，可能是网络或跨域(CORS)未放行")));
        xhr.addEventListener("abort", () => reject(new Error("直传已取消")));
        xhr.send(file);
    });
}

// ===== 断点续传本地状态：按 文件名+大小+修改时间 记住未完成的 uploadId =====
const RESUME_STORE_PREFIX = "vp_resume_";

function resumeKey(file) {
    return `${RESUME_STORE_PREFIX}${file.name}_${file.size}_${file.lastModified}`;
}

function saveResume(file, uploadId) {
    try {
        localStorage.setItem(resumeKey(file), JSON.stringify({ uploadId, chunkSize: CHUNK_SIZE }));
    } catch (error) {
        // localStorage 不可用时降级为不续传，不影响正常上传
    }
}

function loadResume(file) {
    try {
        const raw = localStorage.getItem(resumeKey(file));
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        return null;
    }
}

function clearResume(file) {
    try {
        localStorage.removeItem(resumeKey(file));
    } catch (error) {
        // ignore
    }
}

async function fetchUploadStatus(uploadId) {
    // soft：查询失败静默返回 null，退化为「从头上传」，不打断用户也不清登录态。
    return apiRequest(`/api/media/upload/status?uploadId=${encodeURIComponent(uploadId)}`, { soft: true });
}

// 分块增量计算文件 MD5（内容指纹）。用于秒传 / 内容级去重 / 合并完整性校验。
// SparkMD5 缺失（如 CDN 未加载）时优雅降级为空串——上传照常，只是去重/校验休眠。
async function computeFileMd5(file) {
    if (typeof SparkMD5 === "undefined" || !SparkMD5.ArrayBuffer) {
        return "";
    }
    const spark = new SparkMD5.ArrayBuffer();
    const total = Math.ceil(file.size / CHUNK_SIZE);
    for (let i = 0; i < total; i++) {
        const start = i * CHUNK_SIZE;
        const blob = file.slice(start, Math.min(start + CHUNK_SIZE, file.size));
        spark.append(await blob.arrayBuffer());
        // 分块间让出事件循环，避免大文件计算卡住 UI
        const percent = Math.round(((i + 1) / total) * 5);
        setProgress(percent, `校验文件指纹 ${i + 1}/${total}`);
    }
    return spark.end();
}

async function uploadOneChunk(uploadId, chunkIndex, metrics) {
    const start = chunkIndex * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, currentFile.size);
    const chunk = currentFile.slice(start, end);
    const formData = new FormData();
    formData.append("file", chunk, currentFile.name);

    const chunkStartedAt = performance.now();
    try {
        await apiRequest(`/api/media/upload/chunk?uploadId=${uploadId}&chunkIndex=${chunkIndex}`, {
            method: "POST",
            body: formData
        });
    } finally {
        metrics.chunkDurations.push(performance.now() - chunkStartedAt);
        renderLiveMetrics(metrics);
    }
}

function handleUploadSuccess(taskId, status) {
    taskIdInput.value = taskId;
    taskField.style.display = "grid";
    transcriptArea.value = "";
    summaryArea.value = "";
    currentTask = null;
    updateResultActions();
    hideVideoPlayer();
    setStatus(status || "处理中", "running");
    refreshButton.disabled = false;
    updateUploadButtonState();
    loadMyVideos();
    startPolling();
}

function startPolling() {
    stopPolling();
    pollingTimer = window.setInterval(fetchTask, 1500);
    fetchTask();
}

function stopPolling() {
    if (pollingTimer) {
        window.clearInterval(pollingTimer);
        pollingTimer = null;
    }
}

function hideVideoPlayer() {
    if (!videoPreview) return;
    videoPreview.style.display = "none";
    if (videoPlayer) {
        videoPlayer.pause();
        videoPlayer.removeAttribute("src");
        videoPlayer.load();
    }
}

// 拉取短时效播放令牌，拼出带签名的流地址喂给 <video>，浏览器按 HTTP Range 边下边播。
async function loadVideoPlayer(taskId) {
    if (!videoPreview || !videoPlayer || !token || !taskId) return;
    // soft：拿不到播放令牌就静默隐藏播放器，不影响转写/摘要展示。
    const data = await apiRequest(`/api/media/video/${taskId}/playback-token`, { soft: true });
    if (!data?.streamUrl) {
        hideVideoPlayer();
        return;
    }
    videoPlayer.src = data.streamUrl;
    videoPreview.style.display = "block";
}

async function fetchTask() {
    const taskId = taskIdInput.value.trim();
    if (!token || !taskId) return;

    try {
        const task = await apiRequest(`/api/workflow/tasks/${taskId}`);
        currentTask = task;
        transcriptArea.value = task.transcript || "";
        summaryArea.value = task.summary || "";
        updateResultActions();

        if (task.status === "COMPLETED") {
            setStatus("已完成", "success");
            writeMessage("任务完成，转写和摘要已生成");
            stopPolling();
            loadMyVideos();
            loadVideoPlayer(task.taskId);
            return;
        }

        if (task.status === "FAILED") {
            setStatus("失败", "error");
            writeMessage(`任务失败：${task.errorMessage || "无错误详情"}`, true);
            stopPolling();
            loadMyVideos();
            hideVideoPlayer();
            return;
        }

        setStatus(task.status, "running");
    } catch (error) {
        reportError(error);
        stopPolling();
        // 会话过期属已处理错误，clearAuthState 已在日志说明原因，不再把状态胶囊误标成“查询失败”。
        if (!error?.handled) {
            setStatus("查询失败", "error");
        }
    }
}

async function deleteTask(taskId, triggerButton) {
    if (!token || !taskId) return;
    if (!window.confirm(`确认删除任务 ${taskId}？删除后不可恢复。`)) return;
    if (triggerButton) triggerButton.disabled = true;
    try {
        await apiRequest(`/api/workflow/tasks/${taskId}`, { method: "DELETE" });
        if (taskIdInput.value === taskId) {
            taskIdInput.value = "";
            taskField.style.display = "none";
            transcriptArea.value = "";
            summaryArea.value = "";
            currentTask = null;
            updateResultActions();
            refreshButton.disabled = true;
            setStatus("未开始", "idle");
            stopPolling();
            hideVideoPlayer();
        }
        writeMessage(`已删除任务：${taskId}`);
        loadMyVideos();
    } catch (error) {
        reportError(error);
        if (triggerButton) triggerButton.disabled = false;
    }
}

async function retryTask(taskId, triggerButton) {
    if (!token || !taskId) return;
    if (triggerButton) triggerButton.disabled = true;
    try {
        writeMessage(`正在重试失败任务：${taskId}`);
        const data = await apiRequest(`/api/workflow/tasks/${taskId}/retry`, { method: "POST" });

        taskIdInput.value = taskId;
        taskField.style.display = "grid";
        transcriptArea.value = "";
        summaryArea.value = "";
        hideVideoPlayer();
        setProgress(0, "重新入队");
        resetActiveMetrics();
        refreshButton.disabled = false;
        setStatus(data?.status || "QUEUED", "running");
        writeMessage("任务已重新进入队列");
        loadMyVideos();
        startPolling();
    } catch (error) {
        reportError(error);
        if (triggerButton) triggerButton.disabled = false;
    }
}

function setStatus(text, mode) {
    statusPill.textContent = statusLabel(text);
    statusPill.className = `status-pill ${mode}`;
    setPipelineStatus(text);
}

function statusLabel(status) {
    const labels = {
        UPLOADING: "上传中",
        QUEUED: "排队中",
        TRANSCRIBING: "转写中",
        SUMMARIZING: "总结中",
        COMPLETED: "已完成",
        FAILED: "失败"
    };
    return labels[status] || status;
}

function normalizePipelineStatus(status) {
    if (!status) return "";
    if (status === "FAILED" || status === "失败" || status === "查询失败" || status === "上传失败") {
        return "FAILED";
    }
    if (status === "COMPLETED" || status === "已完成" || status === "文件已存在") {
        return "COMPLETED";
    }
    if (status === "UPLOADING" || status === "初始化" || status === "上传中" || status === "合并中") {
        return "UPLOADING";
    }
    if (status === "处理中") {
        return "QUEUED";
    }
    return status;
}

function setPipelineStatus(status) {
    if (!pipelineSteps.length) return;

    const pipelineStatus = normalizePipelineStatus(status);
    const activeStatus = pipelineStatus === "FAILED" ? "COMPLETED" : pipelineStatus;
    const activeIndex = PIPELINE_ORDER.indexOf(activeStatus);

    pipelineSteps.forEach((step, index) => {
        step.classList.remove("done", "active", "error");
        if (pipelineStatus === "FAILED" && index === PIPELINE_ORDER.length - 1) {
            step.classList.add("error");
            return;
        }
        if (activeIndex < 0) return;
        if (index < activeIndex) {
            step.classList.add("done");
        } else if (index === activeIndex) {
            step.classList.add("active");
        }
    });
}

function writeMessage(message, isError = false) {
    const timestamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const prefix = isError ? "错误" : "信息";
    messagesArea.value = `[${timestamp}] ${prefix}：${message}\n${messagesArea.value}`;
}

async function loadMyVideos() {
    if (!token) return;
    try {
        const data = await apiRequest("/api/workflow/tasks");
        renderVideoList(data || []);
        await loadTaskQuota();
    } catch (error) {
        reportError(error);
    }
}

async function loadTaskQuota() {
    const quota = await apiRequest("/api/workflow/quota", { soft: true });
    if (!quota) return;
    taskQuota = quota;
    if (quota.limited) {
        quotaPill.textContent = `处理中 ${quota.activeTasks}/${quota.maxActiveTasksPerUser}`;
        quotaPill.classList.toggle("full", quota.remainingSlots <= 0);
        quotaPill.title = quota.remainingSlots > 0
            ? `还可提交 ${quota.remainingSlots} 个任务`
            : "任务容量已满，请等待已有任务完成";
    } else {
        quotaPill.textContent = `处理中 ${quota.activeTasks}`;
        quotaPill.classList.remove("full");
        quotaPill.title = "当前未启用单用户任务上限";
    }
    quotaPill.hidden = false;
    updateUploadButtonState();
}

function updateUploadButtonState() {
    const quotaFull = taskQuota.limited && taskQuota.remainingSlots <= 0;
    uploadButton.disabled = !token || !currentFile || quotaFull;
}

async function loadRuntimeInfo() {
    const info = await apiRequest("/api/workflow/runtime", { soft: true });
    if (!info) return;
    runtimeInfo = info;
    labRuntimeMode.textContent = info.mqEnabled ? "RocketMQ" : "本地 @Async";
    labRuntimeMode.classList.toggle("mq", info.mqEnabled);
    const quotaText = info.maxActiveTasksPerUser > 0
        ? `配额 ${info.maxActiveTasksPerUser}`
        : "配额关闭";
    const workerText = info.mqEnabled ? `消费者 ${info.mqConsumerThreads}` : "线程池 2-4";
    labRuntimeMeta.textContent = `Mock ${info.mockDelayMs}ms · ${workerText} · ${quotaText} · ${info.storageType}`;
    runAsyncLabButton.disabled = false;
}

async function runAsyncLab() {
    if (!token || !runtimeInfo || labRun) return;
    const count = Math.max(1, Math.min(100, Number.parseInt(labTaskCount.value, 10) || 1));
    labTaskCount.value = String(count);
    const prefix = `async-lab-${Date.now()}-`;
    labRun = {
        prefix,
        mode: runtimeInfo.mqEnabled ? "mq" : "local",
        requested: count,
        accepted: 0,
        rejected: 0,
        backend: 0,
        active: 0,
        completed: 0,
        failed: 0,
        startedAt: Date.now(),
        submissionMs: 0,
        submissionsDone: false
    };
    runAsyncLabButton.disabled = true;
    cleanupAsyncLabButton.disabled = true;
    renderLabRun();
    writeMessage(`异步实验开始：${labRuntimeMode.textContent}，并发提交 ${count} 个任务`);

    const submissionStarted = performance.now();
    await Promise.all(Array.from({ length: count }, async (_, index) => {
        const formData = new FormData();
        const payload = new File([new Uint8Array(16 * 1024)], `${prefix}${index}.mp4`, { type: "video/mp4" });
        formData.append("file", payload, payload.name);
        try {
            await apiRequest("/api/media/upload/file", { method: "POST", body: formData });
            labRun.accepted += 1;
        } catch (error) {
            labRun.rejected += 1;
        }
        renderLabRun();
    }));
    labRun.submissionMs = performance.now() - submissionStarted;
    labRun.submissionsDone = true;
    writeMessage(`提交完成：HTTP 接收 ${labRun.accepted}，拒绝 ${labRun.rejected}，耗时 ${formatDuration(labRun.submissionMs)}`);
    await refreshLabRun();
    startLabPolling();
}

function startLabPolling() {
    stopLabPolling();
    labPollingTimer = window.setInterval(refreshLabRun, 1000);
}

function stopLabPolling() {
    if (labPollingTimer) {
        window.clearInterval(labPollingTimer);
        labPollingTimer = null;
    }
}

async function refreshLabRun() {
    if (!labRun || !token) return;
    const tasks = await apiRequest("/api/workflow/tasks", { soft: true });
    if (!tasks) return;
    const matching = tasks.filter((task) => task.fileName?.startsWith(labRun.prefix));
    labRun.backend = matching.length;
    labRun.completed = matching.filter((task) => task.status === "COMPLETED").length;
    labRun.failed = matching.filter((task) => task.status === "FAILED").length;
    labRun.active = matching.length - labRun.completed - labRun.failed;
    renderLabRun();
    saveLabResult();
    if (labRun.submissionsDone && labRun.active === 0
            && (labRun.backend > 0 || labRun.accepted === 0)) {
        stopLabPolling();
        cleanupAsyncLabButton.disabled = false;
        writeMessage(`异步实验完成：后台任务 ${labRun.backend}，完成 ${labRun.completed}，失败 ${labRun.failed}`);
        loadMyVideos();
    }
}

function renderLabRun() {
    if (!labRun) {
        labEls.accepted.textContent = "0";
        labEls.rejected.textContent = "0";
        labEls.backend.textContent = "0";
        labEls.active.textContent = "0";
        labEls.completed.textContent = "0";
        labEls.elapsed.textContent = "-";
        labEls.progress.style.width = "0";
        return;
    }
    labEls.accepted.textContent = String(labRun.accepted);
    labEls.rejected.textContent = String(labRun.rejected);
    labEls.backend.textContent = String(labRun.backend);
    labEls.active.textContent = String(labRun.active);
    labEls.completed.textContent = String(labRun.completed);
    labEls.elapsed.textContent = formatDuration(Date.now() - labRun.startedAt);
    const terminal = labRun.completed + labRun.failed;
    const progress = labRun.backend > 0 ? (terminal / labRun.backend) * 100 : 0;
    labEls.progress.style.width = `${Math.min(100, progress)}%`;
}

function saveLabResult() {
    if (!labRun) return;
    const result = {
        requested: labRun.requested,
        accepted: labRun.accepted,
        rejected: labRun.rejected,
        backend: labRun.backend,
        completed: labRun.completed,
        elapsedMs: Date.now() - labRun.startedAt,
        mockDelayMs: runtimeInfo?.mockDelayMs || 0
    };
    localStorage.setItem(`vp_async_lab_${labRun.mode}`, JSON.stringify(result));
    renderSavedLabResults();
}

function renderSavedLabResults() {
    labEls.localResult.textContent = formatSavedLabResult(localStorage.getItem("vp_async_lab_local"));
    labEls.mqResult.textContent = formatSavedLabResult(localStorage.getItem("vp_async_lab_mq"));
}

function formatSavedLabResult(raw) {
    if (!raw) return "暂无";
    try {
        const result = JSON.parse(raw);
        return `接收 ${result.accepted}/${result.requested} · 完成 ${result.completed}/${result.backend} · ${formatDuration(result.elapsedMs)}`;
    } catch (error) {
        return "记录无效";
    }
}

async function cleanupAsyncLab() {
    if (!labRun || labRun.active > 0 || !token) return;
    cleanupAsyncLabButton.disabled = true;
    const tasks = await apiRequest("/api/workflow/tasks", { soft: true });
    const matching = (tasks || []).filter((task) => task.fileName?.startsWith(labRun.prefix));
    for (let index = 0; index < matching.length; index += 10) {
        await Promise.all(matching.slice(index, index + 10).map((task) =>
            apiRequest(`/api/workflow/tasks/${task.taskId}`, { method: "DELETE", soft: true })));
    }
    writeMessage(`已清理本轮 ${matching.length} 条实验任务`);
    labRun = null;
    renderLabRun();
    runAsyncLabButton.disabled = !runtimeInfo;
    loadMyVideos();
}

function renderVideoList(tasks) {
    if (!tasks || tasks.length === 0) {
        videoList.innerHTML = '<p class="empty-state">暂无视频，请先上传</p>';
        return;
    }

    const statusMap = {
        QUEUED: { text: "排队中", cls: "st-queued" },
        TRANSCRIBING: { text: "转写中", cls: "st-running" },
        SUMMARIZING: { text: "总结中", cls: "st-running" },
        COMPLETED: { text: "已完成", cls: "st-success" },
        FAILED: { text: "失败", cls: "st-error" }
    };

    videoList.innerHTML = tasks.map((task) => {
        const status = statusMap[task.status] || { text: task.status, cls: "st-queued" };
        const retryButton = task.status === "FAILED"
            ? `<button class="retry-task" type="button" data-action="retry" aria-label="重试任务 ${escapeHtml(task.fileName)}">重试</button>`
            : "";
        return `
            <div class="video-item" data-task-id="${escapeHtml(task.taskId)}">
                <button class="video-main" type="button" data-action="select">
                    <span class="video-item-info">
                        <span class="video-item-name">${escapeHtml(task.fileName)}</span>
                        <span class="video-item-time">${formatDate(task.createdAt)}</span>
                    </span>
                    <span class="video-item-status ${status.cls}">${status.text}</span>
                </button>
                <span class="video-actions">
                    ${retryButton}
                    <button class="delete-task" type="button" data-action="delete" aria-label="删除任务 ${escapeHtml(task.fileName)}">删除</button>
                </span>
            </div>
        `;
    }).join("");
}

// 历史任务的点击统一走 videoList 上的事件委托（见初始化处），此函数只负责渲染。
function selectTask(taskId) {
    taskIdInput.value = taskId;
    taskField.style.display = "grid";
    transcriptArea.value = "";
    summaryArea.value = "";
    currentTask = null;
    updateResultActions();
    refreshButton.disabled = false;
    writeMessage(`已选择历史任务：${taskId}`);
    startPolling();
}

function updateResultActions() {
    const hasResult = Boolean(transcriptArea.value.trim() || summaryArea.value.trim());
    copyResultButton.disabled = !hasResult;
    downloadResultButton.disabled = !hasResult;
}

function buildTaskMarkdown() {
    const fileName = currentTask?.fileName || "视频理解结果";
    const taskId = currentTask?.taskId || taskIdInput.value.trim() || "-";
    const createdAt = currentTask?.createdAt ? formatDate(currentTask.createdAt) : "-";
    const transcript = transcriptArea.value.trim() || "（暂无转写内容）";
    const summary = summaryArea.value.trim() || "（暂无摘要内容）";
    return [
        `# ${fileName}`,
        "",
        `- 任务 ID：${taskId}`,
        `- 创建时间：${createdAt}`,
        "",
        "## AI 摘要",
        "",
        summary,
        "",
        "## 转写文本",
        "",
        transcript,
        ""
    ].join("\n");
}

async function copyTaskResult() {
    if (copyResultButton.disabled) return;
    const markdown = buildTaskMarkdown();
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(markdown);
        } else {
            const helper = document.createElement("textarea");
            helper.value = markdown;
            helper.style.position = "fixed";
            helper.style.opacity = "0";
            document.body.appendChild(helper);
            helper.select();
            document.execCommand("copy");
            helper.remove();
        }
        writeMessage("已复制完整转写与摘要");
    } catch (error) {
        writeMessage("复制失败，请手动选择结果文本", true);
    }
}

function downloadTaskResult() {
    if (downloadResultButton.disabled) return;
    const markdown = buildTaskMarkdown();
    const originalName = currentTask?.fileName || "video-result";
    const baseName = originalName.replace(/\.[^/.]+$/, "")
        .replace(/[<>:"/\\|?*\u0000-\u001F]/g, "_")
        .slice(0, 80) || "video-result";
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${baseName}-notes.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    writeMessage(`已下载 Markdown：${link.download}`);
}

function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("zh-CN", { hour12: false });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
}
