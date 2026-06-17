"""API-facing labels shared by routes and tests."""

from __future__ import annotations

from backend.db.constants import TARGET_STAGE_LABELS

CASE_TYPE_LABELS = {
    "TYPE_A": "思政课教学案例",
    "TYPE_B": "课程思政共享资源案例",
    "TYPE_C": "实践育人案例",
}

THEME_LABELS = ["强国建设", "实践育人", "数字赋能", "铸魂育人"]

CASE_STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审核",
    "approved": "已通过",
    "needs_revision": "退回修改",
}


def get_api_constants_payload() -> dict:
    """Return the stable `/api/constants` data payload."""
    return {
        "case_types": dict(CASE_TYPE_LABELS),
        "themes": list(THEME_LABELS),
        "target_stages": dict(TARGET_STAGE_LABELS),
        "statuses": dict(CASE_STATUS_LABELS),
    }


__all__ = [
    "CASE_STATUS_LABELS",
    "CASE_TYPE_LABELS",
    "THEME_LABELS",
    "get_api_constants_payload",
]
