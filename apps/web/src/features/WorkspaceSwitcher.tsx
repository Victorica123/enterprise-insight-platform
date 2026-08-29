import React from "react";
import { createPortal } from "react-dom";
import {
  Building2, Check, Copy, Loader2, Plus, Settings2, ShieldCheck, UserPlus, Users, X,
} from "lucide-react";

import {
  acceptWorkspaceInvitation,
  createWorkspace,
  createWorkspaceInvitation,
  listWorkspaceMembers,
  listWorkspaces,
  switchWorkspace,
  updateWorkspaceMemberRole,
  type WorkspaceInvitation,
  type WorkspaceMember,
  type WorkspaceRole,
  type WorkspaceSummary,
} from "../mediaApi";
import type { WorkspaceSession } from "../session";
import { getErrorMessage } from "./common";
import "../styles/workspace.css";

const ROLE_NAMES: Record<WorkspaceRole, string> = {
  OWNER: "所有者",
  ADMIN: "管理员",
  MEMBER: "成员",
  VIEWER: "只读成员",
};

export function WorkspaceSwitcher(props: {
  session: WorkspaceSession;
  onSwitched: (session: WorkspaceSession) => void;
  onError: (message: string) => void;
}) {
  const [workspaces, setWorkspaces] = React.useState<WorkspaceSummary[]>([]);
  const [selectedTenant, setSelectedTenant] = React.useState(props.session.tenantId);
  const [members, setMembers] = React.useState<WorkspaceMember[]>([]);
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [teamName, setTeamName] = React.useState("");
  const [invitationCode, setInvitationCode] = React.useState("");
  const [issuedInvitation, setIssuedInvitation] = React.useState<WorkspaceInvitation | null>(null);
  const [copied, setCopied] = React.useState(false);

  const selectedWorkspace = workspaces.find((item) => item.tenantId === selectedTenant);

  const refreshWorkspaces = React.useCallback(async () => {
    try {
      const next = await listWorkspaces();
      setWorkspaces(next);
      setSelectedTenant((current) => next.some((item) => item.tenantId === current)
        ? current
        : props.session.tenantId);
    } catch (caught) {
      props.onError(getErrorMessage(caught));
    }
  }, [props.onError, props.session.tenantId]);

  React.useEffect(() => {
    setSelectedTenant(props.session.tenantId);
    void refreshWorkspaces();
  }, [props.session.tenantId, refreshWorkspaces]);

  React.useEffect(() => {
    if (!open || selectedWorkspace?.workspaceType !== "team") {
      setMembers([]);
      return;
    }
    void listWorkspaceMembers(selectedWorkspace.tenantId)
      .then(setMembers)
      .catch((caught) => props.onError(getErrorMessage(caught)));
  }, [open, props.onError, selectedWorkspace?.tenantId, selectedWorkspace?.workspaceType]);

  async function run(label: string, operation: () => Promise<void>) {
    setBusy(label);
    try {
      await operation();
    } catch (caught) {
      props.onError(getErrorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  function handleSwitch() {
    if (!selectedTenant || selectedTenant === props.session.tenantId) return;
    void run("switch", async () => {
      const nextSession = await switchWorkspace(selectedTenant);
      props.onSwitched(nextSession);
      setIssuedInvitation(null);
      setOpen(false);
    });
  }

  function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!teamName.trim()) return;
    void run("create", async () => {
      const created = await createWorkspace(teamName.trim());
      setTeamName("");
      await refreshWorkspaces();
      setSelectedTenant(created.tenantId);
    });
  }

  function handleAccept(event: React.FormEvent) {
    event.preventDefault();
    if (!invitationCode.trim()) return;
    void run("accept", async () => {
      const accepted = await acceptWorkspaceInvitation(invitationCode.trim());
      setInvitationCode("");
      await refreshWorkspaces();
      setSelectedTenant(accepted.tenantId);
    });
  }

  function handleInvite() {
    if (!selectedWorkspace) return;
    void run("invite", async () => {
      setIssuedInvitation(await createWorkspaceInvitation(selectedWorkspace.tenantId));
      setCopied(false);
    });
  }

  function handleRoleChange(member: WorkspaceMember, role: Exclude<WorkspaceRole, "OWNER">) {
    if (!selectedWorkspace) return;
    void run(`role-${member.userId}`, async () => {
      const updated = await updateWorkspaceMemberRole(selectedWorkspace.tenantId, member.userId, role);
      setMembers((current) => current.map((item) => item.userId === updated.userId ? updated : item));
    });
  }

  async function copyInvitation() {
    if (!issuedInvitation) return;
    await navigator.clipboard.writeText(issuedInvitation.invitationCode);
    setCopied(true);
  }

  const active = workspaces.find((item) => item.tenantId === props.session.tenantId);
  const canInvite = selectedWorkspace?.role === "OWNER" || selectedWorkspace?.role === "ADMIN";

  return (
    <>
      <div className="workspace-switcher">
        <Building2 size={16} />
        <select value={selectedTenant} onChange={(event) => setSelectedTenant(event.target.value)}
          aria-label="选择工作区">
          {workspaces.length ? workspaces.map((workspace) => (
            <option key={workspace.tenantId} value={workspace.tenantId}>
              {workspace.workspaceType === "personal" ? "个人 · " : "团队 · "}{workspace.name}
            </option>
          )) : <option value={props.session.tenantId}>当前工作区</option>}
        </select>
        {selectedTenant !== props.session.tenantId ? (
          <button className="button compact" type="button" onClick={handleSwitch} disabled={busy === "switch"}>
            {busy === "switch" ? <Loader2 size={14} className="spin" /> : <Check size={14} />}切换
          </button>
        ) : <span className="workspace-active">当前</span>}
        <button className="icon-button subtle" type="button" onClick={() => setOpen(true)} title="管理工作区">
          <Settings2 size={16} />
        </button>
      </div>

      {open ? createPortal((
        <div className="workspace-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setOpen(false);
        }}>
          <section className="workspace-dialog" role="dialog" aria-modal="true" aria-label="工作区管理">
            <header>
              <div><span className="eyebrow">WORKSPACE</span><h2><Users size={20} />团队协作管理</h2></div>
              <button className="icon-button" type="button" onClick={() => setOpen(false)} aria-label="关闭"><X size={17} /></button>
            </header>
            <div className="workspace-dialog-body">
              <section className="workspace-current">
                <div><strong>{selectedWorkspace?.name ?? active?.name ?? "当前工作区"}</strong>
                  <span>{selectedWorkspace?.workspaceType === "team" ? "团队共享" : "个人私有"}
                    {selectedWorkspace ? ` · ${ROLE_NAMES[selectedWorkspace.role]}` : ""}</span></div>
                {selectedTenant !== props.session.tenantId ? (
                  <button className="button" type="button" onClick={handleSwitch} disabled={busy === "switch"}>切换到此空间</button>
                ) : <span className="safe-chip"><ShieldCheck size={14} />令牌已绑定</span>}
              </section>

              {selectedWorkspace?.workspaceType === "team" ? (
                <section className="workspace-team-section">
                  <div className="workspace-section-title"><div><h3>成员与权限</h3><p>VIEWER 只读，MEMBER 及以上可写；发布仍执行四眼审批。</p></div>
                    {canInvite ? <button className="button secondary" type="button" onClick={handleInvite}
                      disabled={busy === "invite"}><UserPlus size={15} />生成邀请</button> : null}</div>
                  {issuedInvitation?.tenantId === selectedWorkspace.tenantId ? (
                    <div className="invitation-once">
                      <strong>一次性邀请码</strong><p>15 分钟内有效，仅展示本次；请通过可信渠道发送。</p>
                      <div><code>{issuedInvitation.invitationCode}</code>
                        <button className="icon-button" type="button" onClick={() => void copyInvitation()} title="复制邀请码">
                          {copied ? <Check size={16} /> : <Copy size={16} />}
                        </button></div>
                    </div>
                  ) : null}
                  <div className="workspace-members">
                    {members.map((member) => (
                      <div className="workspace-member" key={member.userId}>
                        <div><strong>{member.username}{member.userId === props.session.userId ? "（我）" : ""}</strong>
                          <span>{member.userId}</span></div>
                        {selectedWorkspace.role === "OWNER" && member.role !== "OWNER" ? (
                          <select value={member.role} disabled={busy === `role-${member.userId}`}
                            onChange={(event) => handleRoleChange(member,
                              event.target.value as Exclude<WorkspaceRole, "OWNER">)}>
                            <option value="VIEWER">只读成员</option><option value="MEMBER">成员</option><option value="ADMIN">管理员</option>
                          </select>
                        ) : <span className="role-pill">{ROLE_NAMES[member.role]}</span>}
                      </div>
                    ))}
                  </div>
                </section>
              ) : <div className="personal-boundary"><ShieldCheck size={18} /><div><strong>个人空间严格私有</strong><p>视频、文档、分析、知识与工单都按当前账号隔离。</p></div></div>}

              <div className="workspace-create-grid">
                <form onSubmit={handleCreate}>
                  <h3><Plus size={16} />创建团队空间</h3>
                  <p>你将成为 OWNER，可邀请已注册成员。</p>
                  <div><input value={teamName} onChange={(event) => setTeamName(event.target.value)}
                    placeholder="例如：客户洞察项目组" maxLength={100} />
                    <button className="button" disabled={!teamName.trim() || busy === "create"}>创建</button></div>
                </form>
                <form onSubmit={handleAccept}>
                  <h3><UserPlus size={16} />加入团队空间</h3>
                  <p>粘贴 OWNER 或 ADMIN 发给你的一次性邀请码。</p>
                  <div><input value={invitationCode} onChange={(event) => setInvitationCode(event.target.value)}
                    placeholder="一次性邀请码" minLength={32} maxLength={200} />
                    <button className="button secondary" disabled={invitationCode.trim().length < 32 || busy === "accept"}>加入</button></div>
                </form>
              </div>
            </div>
          </section>
        </div>
      ), document.body) : null}
    </>
  );
}
