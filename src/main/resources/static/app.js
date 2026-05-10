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

const CHUNK_SIZE = 2 * 1024 * 1024; // 2MB

let token = "";
let pollingTimer = null;
let currentFile = null;

// Tab switching
// 新的tab使用 data-target 指向 pane 的 id
document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
        const targetId = tab.dataset.target;
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(targetId).classList.add("active");
    });
});

// File selection
videoFileInput.addEventListener("change", () => {
    const file = videoFileInput.files?.[0];
    if (file) {
        currentFile = file;
        fileNameEl.textContent = file.name;
        fileSizeEl.textContent = formatSize(file.size);
        dropzoneEmpty.style.display = "none";
        dropzoneFile.style.display = "block";
        dropzone.style.borderStyle = "solid";
        dropzone.style.borderColor = "var(--primary-light)";
        uploadButton.disabled = !token;
    } else {
        resetDropzone();
    }
});

function resetDropzone() {
    currentFile = null;
    dropzoneEmpty.style.display = "block";
    dropzoneFile.style.display = "none";
    dropzone.style.borderStyle = "dashed";
    dropzone.style.borderColor = "var(--border)";
    progressFill.style.width = "0%";
    progressText.textContent = "准备上传";
    progressPercent.textContent = "0%";
    uploadButton.disabled = true;
}

// Auth buttons
document.getElementById("registerButton").addEventListener("click", async () => {
    await authenticate("/api/auth/register");
});

document.getElementById("loginButton").addEventListener("click", async () => {
    await authenticate("/api/auth/login");
});

document.getElementById("uploadButton").addEventListener("click", async () => {
    await uploadFileChunked();
});

document.getElementById("refreshButton").addEventListener("click", async () => {
    await fetchTask();
});

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

function setProgress(percent, text) {
    progressFill.style.width = percent + "%";
    progressPercent.textContent = Math.round(percent) + "%";
    progressText.textContent = text || (Math.round(percent) + "%");
}

async function authenticate(path) {
    try {
        writeMessage(path.includes("register") ? "正在注册..." : "正在登录...");
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
        tokenBar.style.display = "flex";
        tokenText.textContent = `已获取 Token（${result.data.username}）`;
        writeMessage(`✅ ${path.includes("register") ? "注册" : "登录"}成功，用户 ${result.data.username}`);
        uploadButton.disabled = !currentFile;
    } catch (error) {
        writeMessage(error.message, true);
    }
}

async function uploadFileChunked() {
    if (!token) {
        writeMessage("请先注册或登录", true);
        return;
    }
    if (!currentFile) {
        writeMessage("请先选择视频文件", true);
        return;
    }

    const totalChunks = Math.ceil(currentFile.size / CHUNK_SIZE);
    writeMessage(`开始分片上传: ${currentFile.name} (${formatSize(currentFile.size)}, ${totalChunks} 个分片)`);
    setStatus("初始化...", "running");
    uploadButton.disabled = true;
    refreshButton.disabled = true;

    try {
        // Step 1: init
        setProgress(5, "初始化...");
        const initResponse = await fetch("/api/media/upload/init", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`
            },
            body: JSON.stringify({
                fileName: currentFile.name,
                fileSize: currentFile.size,
                totalChunks: totalChunks,
                chunkSize: CHUNK_SIZE,
                fileMd5: ""
            })
        });
        const initResult = await initResponse.json();
        if (!initResponse.ok || !initResult.success) {
            throw new Error(initResult.message || "初始化失败");
        }

        if (initResult.data.exists) {
            writeMessage("⚡ 秒传成功！文件已存在");
            taskIdInput.value = initResult.data.uploadId;
            taskField.style.display = "block";
            setStatus("秒传成功", "success");
            refreshButton.disabled = false;
            startPolling();
            return;
        }

        const uploadId = initResult.data.uploadId;

        // Step 2: upload chunks
        for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, currentFile.size);
            const chunk = currentFile.slice(start, end);

            const formData = new FormData();
            formData.append("file", chunk, currentFile.name);

            const pct = Math.round(((i + 0.5) / totalChunks) * 80) + 10;
            setProgress(pct, `上传分片 ${i + 1}/${totalChunks}`);
            setStatus(`上传中 ${i + 1}/${totalChunks}`, "running");

            const chunkResponse = await fetch(`/api/media/upload/chunk?uploadId=${uploadId}&chunkIndex=${i}`, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
                body: formData
            });
            const chunkResult = await chunkResponse.json();
            if (!chunkResponse.ok || !chunkResult.success) {
                throw new Error(chunkResult.message || `分片 ${i} 上传失败`);
            }
        }

        // Step 3: merge
        setProgress(95, "合并中...");
        setStatus("合并中...", "running");
        const mergeResponse = await fetch("/api/media/upload/merge", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`
            },
            body: JSON.stringify({ uploadId: uploadId })
        });
        const mergeResult = await mergeResponse.json();
        if (!mergeResponse.ok || !mergeResult.success) {
            throw new Error(mergeResult.message || "合并失败");
        }

        taskIdInput.value = mergeResult.data.taskId;
        taskField.style.display = "block";
        transcriptArea.value = "";
        summaryArea.value = "";
        setProgress(100, "完成");
        writeMessage(`✅ 上传完成，taskId = ${mergeResult.data.taskId}`);
        setStatus(mergeResult.data.status || "处理中", "running");
        refreshButton.disabled = false;
        startPolling();
    } catch (error) {
        setProgress(0, "失败");
        setStatus("上传失败", "error");
        writeMessage(error.message, true);
        uploadButton.disabled = false;
    }
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

async function fetchTask() {
    const taskId = taskIdInput.value.trim();
    if (!token || !taskId) return;

    try {
        const response = await fetch(`/api/workflow/tasks/${taskId}`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "查询失败");
        }
        const task = result.data;
        transcriptArea.value = task.transcript || "";
        summaryArea.value = task.summary || "";

        if (task.status === "COMPLETED") {
            setStatus("已完成", "success");
            writeMessage("✅ 任务完成！转写和总结已生成");
            stopPolling();
            return;
        }
        if (task.status === "FAILED") {
            setStatus("失败", "error");
            writeMessage(`❌ 任务失败: ${task.errorMessage}`);
            stopPolling();
            return;
        }
        setStatus(task.status, "running");
    } catch (error) {
        setStatus("查询失败", "error");
        writeMessage(error.message, true);
        stopPolling();
    }
}

function setStatus(text, mode) {
    statusPill.textContent = text;
    statusPill.className = `status-pill ${mode}`;
}

function writeMessage(message, isError = false) {
    const timestamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const prefix = isError ? "❌" : "ℹ️";
    messagesArea.value = `[${timestamp}] ${prefix} ${message}\n` + messagesArea.value;
}
