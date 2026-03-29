"""Dynamic control-plane support for agent configuration and orchestration."""

from .bootstrap import apply_runtime_env_from_control_plane
from .manager import ControlPlaneManager, get_control_plane_manager
from .supervisor import ControlPlaneSupervisor

__all__ = [
    "ControlPlaneManager",
    "ControlPlaneSupervisor",
    "apply_runtime_env_from_control_plane",
    "get_control_plane_manager",
]
