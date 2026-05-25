from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_check_module():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "agent_control_plane_check.py"
    spec = spec_from_file_location("agent_control_plane_check", script)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_control_plane_check_passes_for_repo_root() -> None:
    root = Path(__file__).resolve().parents[2]
    agent_control_plane_check = _load_check_module()

    assert agent_control_plane_check.run(root) == []


def test_agent_control_plane_check_reports_missing_doc(tmp_path: Path) -> None:
    agent_control_plane_check = _load_check_module()

    failures = agent_control_plane_check.run(tmp_path)

    assert failures == [
        "missing required operating-model doc: docs/agent-control-plane-operating-model.md"
    ]
