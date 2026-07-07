from __future__ import annotations

from typing import Callable

from engine.dashboard.reader import DashboardSnapshot, InstanceDashboardView

MODULE_NAME = "dashboard.console"


def format_position(view: InstanceDashboardView) -> str:
    if view.open_ticket is None:
        return "none"
    side = view.position_side or "-"
    volume = "-" if view.position_volume is None else f"{view.position_volume:.2f}"
    return f"{side} ticket={view.open_ticket} volume={volume}"


def format_instance_view(view: InstanceDashboardView) -> str:
    instance = view.instance
    spread = "-" if view.relative_spread is None else f"{view.relative_spread:.4f}"
    risk = view.risk_result or "-"
    if view.risk_reason:
        risk = f"{risk} ({view.risk_reason})"
    ack = view.last_ack_status or "-"
    if view.last_ack_command_id:
        ack = f"{ack} [{view.last_ack_command_id}]"
    error = "-"
    if view.last_error_message is not None:
        error_type = view.last_error_type or "ERROR"
        error = f"{error_type}: {view.last_error_message}"

    return (
        f"{instance.account_id}/{instance.symbol}/{instance.magic} "
        f"decision={view.last_decision or '-'} "
        f"reason={view.last_reason or '-'} "
        f"risk={risk} "
        f"spread={spread} "
        f"position={format_position(view)} "
        f"ack={ack} "
        f"error={error}"
    )


def format_dashboard(snapshot: DashboardSnapshot) -> str:
    lines = [
        f"SYSTEM dashboard @ {snapshot.generated_at_utc}",
        f"instances={snapshot.instance_count}",
    ]
    if not snapshot.instances:
        lines.append("no active instances")
    else:
        for view in snapshot.instances:
            lines.append(format_instance_view(view))
    return "\n".join(lines)


def render_dashboard(
    snapshot: DashboardSnapshot,
    *,
    output: Callable[[str], None] | None = None,
) -> str:
    rendered = format_dashboard(snapshot)
    if output is not None:
        output(rendered)
    return rendered
