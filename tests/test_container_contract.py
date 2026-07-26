from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_demo_container_extends_rehearsed_core_and_runs_non_root() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG ORBIT_CORE_IMAGE=orbit-core:demo-443123d" in dockerfile
    assert "FROM ${ORBIT_CORE_IMAGE} AS runtime" in dockerfile
    assert "USER orbit" in dockerfile
    assert "customer_support_assistant.api:create_app" in dockerfile
    assert "/health/ready" in dockerfile
    assert "COPY . ." not in dockerfile


def test_demo_container_excludes_local_credentials_and_outputs() -> None:
    ignored = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert ".env" in ignored
    assert ".venv" in ignored
    assert ".git" in ignored
    assert "logs" in ignored
    assert "tests" in ignored


def test_usecase_manifest_is_packaged_with_native_workflow_metadata() -> None:
    import yaml

    manifest_path = (
        REPOSITORY_ROOT
        / "customer_support_assistant"
        / "usecase-manifest.yaml"
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert manifest["id"] == "customer-support-assistant"
    assert manifest["workflows"][0]["name"] == "customer_support_triage"
    assert manifest["workflows"][0]["execution_adapter"] == "native"
    assert [tool["name"] for tool in manifest["tools"]] == [
        "support_knowledge",
        "case_persistence",
    ]
