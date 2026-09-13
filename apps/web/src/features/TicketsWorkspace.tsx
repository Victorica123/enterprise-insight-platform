import { TicketsView } from "./TicketsView";
import type { useTicketsWorkspace } from "../hooks/useTicketsWorkspace";
import type { ActorRole } from "../apiClient";

const statusTag = { draft: "草稿", pending: "待处理", open: "打开", in_progress: "处理中", resolved: "已解决", closed: "已关闭" };
const priorityTag = { low: "低", medium: "中", high: "高", critical: "紧急" };

export function TicketsWorkspace({ controller, actorRole }: {
  controller: ReturnType<typeof useTicketsWorkspace>; actorRole: ActorRole;
}) {
  return <TicketsView {...controller} actorRole={actorRole} permissionHint={controller.ticketsPermissionHint}
    statusTag={statusTag} priorityTag={priorityTag} />;
}
