from fastapi import APIRouter, Header, HTTPException

from app.auth import (
    normalize_actor_user,
    require_operator_role,
    require_write_role,
    validate_actor_role,
)
from app.models import (
    ApprovalRequest,
    ApprovalResponse,
    PendingActionResponse,
    TicketCreateRequest,
    TicketListResponse,
    TicketResponse,
    TicketStatusDraftRequest,
)
from app.ticket_store import (
    create_ticket,
    delete_ticket,
    get_pending_action,
    get_ticket,
    get_ticket_summary,
    list_pending_actions,
    list_tickets,
)
from app.tools import execute_tool, resolve_tool_action


router = APIRouter(tags=["tickets"])


@router.get("/tickets", response_model=TicketListResponse, summary="工单列表（状态/优先级/关键词过滤）")
def get_tickets(
    status: str | None = None,
    priority: str | None = None,
    keyword: str = "",
) -> TicketListResponse:
    tickets = list_tickets(status=status, priority=priority, keyword=keyword)
    return TicketListResponse(
        tickets=[TicketResponse(**ticket.to_dict()) for ticket in tickets],
        total=len(tickets),
        summary=get_ticket_summary(),
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse, summary="工单详情")
def get_ticket_by_id(ticket_id: str) -> TicketResponse:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return TicketResponse(**ticket.to_dict())


@router.post("/tickets", response_model=TicketResponse, summary="手动创建工单（operator+）",
             responses={403: {"description": "viewer 无写权限"}})
def create_ticket_manual(
    request: TicketCreateRequest,
    x_user_role: str = Header(default="viewer"),
) -> TicketResponse:
    require_write_role(validate_actor_role(x_user_role))
    ticket = create_ticket(
        title=request.title,
        description=request.description,
        status="open",
        priority=request.priority,
        assignee=request.assignee,
        risk_level=request.risk_level,
        source_document_ids=request.source_document_ids,
    )
    return TicketResponse(**ticket.to_dict())


@router.post("/tickets/{ticket_id}/status-draft", response_model=PendingActionResponse, summary="生成状态变更草稿（进入审批）")
def create_ticket_status_draft(
    ticket_id: str,
    request: TicketStatusDraftRequest,
    x_user_role: str = Header(default="viewer"),
    x_user_id: str = Header(default=""),
) -> PendingActionResponse:
    result = execute_tool(
        "update_ticket_status",
        {"ticket_id": ticket_id, "new_status": request.new_status, "assignee": request.assignee},
        actor_role=validate_actor_role(x_user_role),
        actor_user=normalize_actor_user(x_user_id),
    )
    if not result.success:
        status_code = 403 if result.status == "denied" else 400
        raise HTTPException(status_code=status_code, detail=result.result.get("error", "Draft failed."))
    action = get_pending_action(result.pending_action_id)
    if action is None:
        raise HTTPException(status_code=500, detail="Pending action was not persisted.")
    return PendingActionResponse(**action.to_dict())


@router.delete("/tickets/{ticket_id}", summary="删除工单（operator+）",
             responses={403: {"description": "viewer 无写权限"}, 404: {"description": "工单不存在"}})
def remove_ticket(ticket_id: str, x_user_role: str = Header(default="viewer")) -> dict[str, str]:
    require_write_role(validate_actor_role(x_user_role))
    if not delete_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return {"status": "deleted", "ticket_id": ticket_id}


@router.get("/pending-actions", response_model=list[PendingActionResponse], summary="待审批操作队列（operator+）")
def get_pending_actions(
    status: str = "pending",
    x_user_role: str = Header(default="viewer"),
) -> list[PendingActionResponse]:
    require_operator_role(validate_actor_role(x_user_role))
    actions = list_pending_actions(status=None if status == "all" else status)
    return [PendingActionResponse(**action.to_dict()) for action in actions]


@router.post("/pending-actions/{action_id}/approve", response_model=ApprovalResponse,
             summary="批准/拒绝待审批操作（发起人不能自批）",
             responses={403: {"description": "无审批权限或触发职责分离"}, 404: {"description": "操作不存在"}})
def approve_action(
    action_id: str,
    request: ApprovalRequest,
    x_user_role: str = Header(default="viewer"),
    x_user_id: str = Header(default=""),
) -> ApprovalResponse:
    resolution = resolve_tool_action(
        action_id,
        request.approved,
        actor_role=validate_actor_role(x_user_role),
        actor_user=normalize_actor_user(x_user_id),
    )
    if resolution.status == "not_found":
        raise HTTPException(status_code=404, detail=resolution.message)
    if resolution.status == "denied":
        raise HTTPException(status_code=403, detail=resolution.message)
    return ApprovalResponse(**resolution.__dict__)
