from __future__ import annotations

from typing import Any

from .release_catalog import DistributionError


PASSING_STATUS_STATES = {"ready", "setup", "installed"}


def require_final_health(
    *, target_release: str, status: dict[str, Any], doctor: dict[str, Any]
) -> dict[str, Any]:
    """Require composed status and doctor to agree on the target release.

    `ready` is preferred. `setup`/`installed` remain accepted because some owner
    adapters expose structurally healthy installs without a separate runtime-ready
    state. Any unhealthy/recovery/setup-required component still fails through the
    aggregate state or doctor result.
    """

    status_release = status.get("release_set_id")
    doctor_release = doctor.get("release_set_id")
    if status_release != target_release:
        raise DistributionError(
            f"post-update status reported {status_release!r}, expected {target_release!r}"
        )
    if doctor_release != target_release:
        raise DistributionError(
            f"post-update doctor reported {doctor_release!r}, expected {target_release!r}"
        )
    state = status.get("state")
    if state not in PASSING_STATUS_STATES:
        raise DistributionError(f"post-update status gate failed with state {state!r}")
    if doctor.get("ok") is not True:
        raise DistributionError("post-update doctor gate failed")
    return {
        "ok": True,
        "status_state": state,
        "status_release": status_release,
        "doctor_ok": True,
        "doctor_release": doctor_release,
    }
