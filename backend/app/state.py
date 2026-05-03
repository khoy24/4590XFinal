from typing import Any

# Per logged-in user: staged writes/plans only (lost on backend restart — by design prototype)
user_workspace: dict[int, dict[str, Any]] = {}


def workspace_for_user(user_id: int) -> dict[str, Any]:
    if user_id not in user_workspace:
        user_workspace[user_id] = {"pending_actions": {}, "pending_plans": {}}
    return user_workspace[user_id]


def clear_user_workspace(user_id: int) -> None:
    user_workspace.pop(user_id, None)
