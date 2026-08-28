import React from "react";
import { CloudOff, X } from "lucide-react";
import type { AnswerMode } from "../api";

export function MetricItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function UsageBars({ title, data, color }: { title: string; data: Record<string, number> | undefined; color: string }) {
  const entries = Object.entries(data ?? {})
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="usage-block">
      <span className="usage-title">{title}</span>
      <ul className="usage-list">
        {entries.map(([key, value]) => (
          <li key={key}>
            <div className="usage-row">
              <span className="usage-label">{key}</span>
              <span className="usage-value">{value} · {Math.round((value / total) * 100)}%</span>
            </div>
            <div className="usage-track">
              <div className="usage-fill" style={{ width: `${(value / total) * 100}%`, background: color }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StatusItem({ label, value, ok }: { label: string; value: string | number; ok?: boolean }) {
  return (
    <div className="status-item">
      <span>{label}</span>
      <span className={ok === true ? "status-ok" : ok === false ? "status-err" : ""}>{value}</span>
    </div>
  );
}

export type ApiFailureNotice = {
  reason: string;
  requestedMode: AnswerMode;
};

export function ApiFailureDialog({ notice, onClose }: { notice: ApiFailureNotice; onClose: () => void }) {
  const closeButtonRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    const previousActiveElement = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previousActiveElement?.focus();
    };
  }, [onClose]);

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="api-failure-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="api-failure-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-heading">
          <span className="dialog-icon"><CloudOff size={22} /></span>
          <div>
            <h2 id="api-failure-title">模型 API 调用失败</h2>
            <p>DeepSeek 没有返回可用结果，本次回答已自动降级为本地 RAG。</p>
          </div>
          <button ref={closeButtonRef} className="icon-button" type="button" onClick={onClose} aria-label="关闭提示">
            <X size={17} />
          </button>
        </div>
        <div className="dialog-reason">
          <strong>检测结果</strong>
          <span>{notice.reason}</span>
        </div>
        <p className="dialog-guidance">
          请检查 API Key、模型名、账户余额和网络连接。修复后选择 api 模式再次提问，并确认执行轨迹显示 answer · api。
        </p>
        <div className="dialog-actions">
          <span>请求模式：{notice.requestedMode}</span>
          <button className="button" type="button" onClick={onClose}>知道了</button>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

export function getErrorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "发生未知错误。";
}

export function getApiFailureReason(detail: string): string {
  const normalized = detail.toLowerCase();
  if (normalized.includes("401") || normalized.includes("authentication") || normalized.includes("invalid key")) {
    return "鉴权失败：当前 API Key 无效或已经失效。";
  }
  if (normalized.includes("402") || normalized.includes("balance") || normalized.includes("quota")) {
    return "账户额度不足或调用配额已经用完。";
  }
  if (normalized.includes("model") && (normalized.includes("404") || normalized.includes("not found"))) {
    return "模型不可用：请检查 DEEPSEEK_MODEL 配置。";
  }
  if (normalized.includes("timeout") || normalized.includes("network") || normalized.includes("connection")) {
    return "网络连接失败或请求超时。";
  }
  if (normalized.includes("未配置") || normalized.includes("api key")) {
    return "没有检测到可用的 API Key。";
  }
  return "模型服务暂时不可用，详细原因可在执行轨迹中查看。";
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatExpiry(value: string): string {
  const expiresAt = new Date(value).getTime();
  if (!Number.isFinite(expiresAt)) return "有效期未知";
  const minutes = Math.max(0, Math.ceil((expiresAt - Date.now()) / 60_000));
  return minutes > 0 ? `${minutes} 分钟后过期` : "已过期";
}

export function formatCoverage(value: number | undefined): string {
  if (typeof value !== "number") {
    return "0%";
  }

  return `${Math.round(value * 100)}%`;
}

export function formatPercent(value: number | undefined): string {
  return `${Math.round((value ?? 0) * 100)}%`;
}

export function formatMilliseconds(value: number | undefined): string {
  return `${Math.round(value ?? 0)} ms`;
}

export function formatDecimal(value: number | undefined): string {
  return (value ?? 0).toFixed(1);
}

export function formatUsd(value: number | undefined): string {
  const amount = value ?? 0;
  if (amount === 0) return "$0";
  return amount < 0.01 ? `$${amount.toFixed(5)}` : `$${amount.toFixed(2)}`;
}
