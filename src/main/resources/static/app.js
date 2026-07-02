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
const messagesArea = document.getElementById("messages");
const statusPill = document.getElementById("statusPill");
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
    chunkCompare: document.getElementById("chunkCompare")
};

const CHUNK_SIZE = 2 * 1024 * 1024;
const CHUNK_CONCURRENCY = 4;
const PIPELINE_ORDER = ["UPLOADING", "QUEUED", "TRANSCRIBING", "SUMMARIZING", "COMPLETED"];
const MODE_LABELS = {
    single: "普通上传",
    chunk: "Redis 并发分片"
};

let token = localStorage.getItem("vp_token") || "";
let pollingTimer = null;
let currentFile = null;
let uploadMode = localStorage.getItem("vp_upload_mode") || "single";
let activeMetrics = null;
let lastMetrics = {
    single: null,
    chunk: null
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
    dropzone.style.borderStyle = "solid";
    dropzone.style.borderColor = "#84bcb6";
    uploadButton.disabled = !token;
    resetActiveMetrics();
});

dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.style.borderStyle = "solid";
    dropzone.style.borderColor = "#156f68";
});

dropzone.addEventListener("dragleave", () => {
    if (!currentFile) {
        dropzone.style.borderStyle = "dashed";
        dropzone.style.borderColor = "";
    }
});

dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    videoFileInput.files = event.dataTransfer.files;
    videoFileInput.dispatchEvent(new Event("change"));
});

document.getElementById("registerButton").addEventListener("click", async () => {
    await authenticate("/api/auth/register");
});

document.getElementById("loginButton").addEventListener("click", async () => {
    await authenticate("/api/auth/login");
});

uploadButton.addEventListener("click", async () => {
    if (uploadMode === "single") {
        await uploadSingleFile();
    } else {
        await uploadFileChunked();
    }
});

refreshButton.addEventListener("click", async () => {
    await fetchTask();
});

loadMyVideosButton.addEventListener("click", loadMyVideos);

function setUploadMode(mode) {
    uploadMode = mode === "chunk" ? "chunk" : "single";
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
    dropzone.style.borderStyle = "dashed";
    dropzone.style.borderColor = "";
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
    uploadButton.disabled = !currentFile;
}

function clearAuthState(message = "登录已过期，请重新登录") {
    token = "";
    localStorage.removeItem("vp_token");
    tokenBar.style.display = "none";
    tokenText.textContent = "";
    myVideosCard.style.display = "none";
    uploadButton.disabled = true;
    refreshButton.disabled = true;
    stopPolling();
    writeMessage(message, true);
}

function handleAuthFailure(response) {
    if (response.status === 401 || response.status === 403) {
        clearAuthState();
        return true;
    }
    return false;
}

async function authenticate(path) {
    try {
        const isRegister = path.includes("register");
        writeMessage(isRegister ? "正在注册账号..." : "正在登录...");
        const response = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: usernameInput.value.trim(),
                password: passwordInput.value
            })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "认证失败");
        }

        token = result.data.token;
        localStorage.setItem("vp_token", token);
        showLoggedIn(`已登录：${result.data.username}`);
        writeMessage(`${isRegister ? "注册" : "登录"}成功，用户：${result.data.username}`);
        loadMyVideos();
    } catch (error) {
        writeMessage(error.message, true);
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

        const response = await fetch("/api/media/upload/file", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData
        });
        if (handleAuthFailure(response)) return;
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "上传失败");
        }

        setProgress(100, "普通上传完成");
        finishMetrics(metrics);
        writeMessage(`普通上传完成，总耗时 ${formatDuration(metrics.totalMs)}，吞吐 ${formatSpeed(metrics.fileSize, metrics.totalMs)}`);
        handleUploadSuccess(result.data.taskId, result.data.status);
    } catch (error) {
        setProgress(0, "上传失败");
        setStatus("上传失败", "error");
        writeMessage(error.message, true);
        uploadButton.disabled = false;
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
            const initResponse = await fetch("/api/media/upload/init", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify({
                    fileName: currentFile.name,
                    fileSize: currentFile.size,
                    totalChunks: metrics.totalChunks,
                    chunkSize: CHUNK_SIZE,
                    fileMd5: fileMd5
                })
            });
            metrics.initMs = performance.now() - initStartedAt;
            renderLiveMetrics(metrics);

            if (initResponse.status === 503) {
                throw new Error("Redis 分片上传未启用。请用 Redis 模式启动后再测试分片上传。");
            }

            if (handleAuthFailure(initResponse)) return;
            const initResult = await initResponse.json();
            if (!initResponse.ok || !initResult.success) {
                throw new Error(initResult.message || "初始化上传失败");
            }

            if (initResult.data.exists) {
                clearResume(currentFile);
                taskIdInput.value = initResult.data.uploadId;
                taskField.style.display = "grid";
                setProgress(100, "文件已存在");
                setStatus("已完成", "success");
                finishMetrics(metrics);
                writeMessage(`文件已存在，触发秒传，总耗时 ${formatDuration(metrics.totalMs)}`);
                refreshButton.disabled = false;
                startPolling();
                return;
            }

            uploadId = initResult.data.uploadId;
            uploadedSet = new Set(initResult.data.uploadedChunks || []);
            saveResume(currentFile, uploadId);
        }

        await uploadChunksConcurrently(uploadId, metrics, uploadedSet);

        setProgress(95, "合并文件");
        setStatus("合并中", "running");
        const mergeStartedAt = performance.now();
        const mergeResponse = await fetch("/api/media/upload/merge", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`
            },
            body: JSON.stringify({ uploadId: uploadId })
        });
        metrics.mergeMs = performance.now() - mergeStartedAt;
        renderLiveMetrics(metrics);

        if (handleAuthFailure(mergeResponse)) return;
        const mergeResult = await mergeResponse.json();
        if (!mergeResponse.ok || !mergeResult.success) {
            throw new Error(mergeResult.message || "合并失败");
        }

        clearResume(currentFile);
        setProgress(100, "Redis 并发分片上传完成");
        finishMetrics(metrics);
        writeMessage(`Redis 并发分片上传完成，总耗时 ${formatDuration(metrics.totalMs)}，平均分片 ${formatDuration(average(metrics.chunkDurations))}`);
        handleUploadSuccess(mergeResult.data.taskId, mergeResult.data.status);
    } catch (error) {
        setProgress(0, "上传失败");
        setStatus("上传失败", "error");
        writeMessage(error.message, true);
        uploadButton.disabled = false;
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
    try {
        const response = await fetch(`/api/media/upload/status?uploadId=${encodeURIComponent(uploadId)}`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (!response.ok) return null;
        const result = await response.json();
        return result.success ? result.data : null;
    } catch (error) {
        return null;
    }
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
    const chunkResponse = await fetch(`/api/media/upload/chunk?uploadId=${uploadId}&chunkIndex=${chunkIndex}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData
    });
    metrics.chunkDurations.push(performance.now() - chunkStartedAt);
    renderLiveMetrics(metrics);

    if (handleAuthFailure(chunkResponse)) return;
    const chunkResult = await chunkResponse.json();
    if (!chunkResponse.ok || !chunkResult.success) {
        throw new Error(chunkResult.message || `分片 ${chunkIndex + 1} 上传失败`);
    }
}

function handleUploadSuccess(taskId, status) {
    taskIdInput.value = taskId;
    taskField.style.display = "grid";
    transcriptArea.value = "";
    summaryArea.value = "";
    hideVideoPlayer();
    setStatus(status || "处理中", "running");
    refreshButton.disabled = false;
    uploadButton.disabled = !currentFile;
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
    try {
        const response = await fetch(`/api/media/video/${taskId}/playback-token`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (!response.ok) {
            hideVideoPlayer();
            return;
        }
        const result = await response.json();
        if (!result.success || !result.data?.streamUrl) {
            hideVideoPlayer();
            return;
        }
        videoPlayer.src = result.data.streamUrl;
        videoPreview.style.display = "block";
    } catch (error) {
        hideVideoPlayer();
    }
}

async function fetchTask() {
    const taskId = taskIdInput.value.trim();
    if (!token || !taskId) return;

    try {
        const response = await fetch(`/api/workflow/tasks/${taskId}`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (handleAuthFailure(response)) return;
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "查询任务失败");
        }

        const task = result.data;
        transcriptArea.value = task.transcript || "";
        summaryArea.value = task.summary || "";

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
        setStatus("查询失败", "error");
        writeMessage(error.message, true);
        stopPolling();
    }
}

async function deleteTask(taskId) {
    if (!token || !taskId) return;
    try {
        const response = await fetch(`/api/workflow/tasks/${taskId}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` }
        });
        if (handleAuthFailure(response)) return;
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "删除任务失败");
        }
        if (taskIdInput.value === taskId) {
            taskIdInput.value = "";
            taskField.style.display = "none";
            transcriptArea.value = "";
            summaryArea.value = "";
            refreshButton.disabled = true;
            setStatus("未开始", "idle");
            stopPolling();
            hideVideoPlayer();
        }
        writeMessage(`已删除任务：${taskId}`);
        loadMyVideos();
    } catch (error) {
        writeMessage(error.message, true);
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
        const response = await fetch("/api/workflow/tasks", {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (handleAuthFailure(response)) return;
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "获取视频列表失败");
        }
        renderVideoList(result.data || []);
    } catch (error) {
        writeMessage(error.message, true);
    }
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
        return `
            <div class="video-item" data-task-id="${escapeHtml(task.taskId)}">
                <button class="video-main" type="button" data-action="select">
                    <span class="video-item-info">
                        <span class="video-item-name">${escapeHtml(task.fileName)}</span>
                        <span class="video-item-time">${formatDate(task.createdAt)}</span>
                    </span>
                    <span class="video-item-status ${status.cls}">${status.text}</span>
                </button>
                <button class="delete-task" type="button" data-action="delete" aria-label="删除任务 ${escapeHtml(task.fileName)}">删除</button>
            </div>
        `;
    }).join("");

    videoList.querySelectorAll(".video-item").forEach((item) => {
        const taskId = item.dataset.taskId;
        item.querySelector('[data-action="select"]').addEventListener("click", () => {
            taskIdInput.value = taskId;
            taskField.style.display = "grid";
            transcriptArea.value = "";
            summaryArea.value = "";
            refreshButton.disabled = false;
            writeMessage(`已选择历史任务：${taskId}`);
            startPolling();
        });
        item.querySelector('[data-action="delete"]').addEventListener("click", async () => {
            await deleteTask(taskId);
        });
    });
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
