"""Static contracts: separate projects, private LMS, stable data volumes."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_app_entry_html_is_not_cached_across_frontend_deploys():
    config = (ROOT / "frontend/pacewise/nginx.conf").read_text(encoding="utf-8")
    for entry in ("/app", "/index.html"):
        block = re.search(r"location\s*=\s*" + re.escape(entry) + r"\s*\{([^}]+)\}", config)
        assert block is not None
        assert 'add_header Cache-Control "no-store" always;' in block.group(1)
        assert 'add_header Referrer-Policy "no-referrer" always;' in block.group(1)


def test_frontend_preserves_the_original_https_scheme_from_caddy():
    config = (ROOT / "frontend/pacewise/nginx.conf").read_text(encoding="utf-8")
    assert "map $http_x_forwarded_proto $pacewise_forwarded_proto" in config
    assert config.count("proxy_set_header X-Forwarded-Proto $pacewise_forwarded_proto;") == 3
    assert "proxy_set_header X-Forwarded-Proto $scheme;" not in config

    deploy_script = (ROOT / "deploy/deploy-ec2.sh").read_text(encoding="utf-8")
    assert '"https://${pacewise_domain}/api/v1/status"' in deploy_script


def compose(path):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_pacewise_and_lms_have_separate_service_and_volume_ownership():
    pacewise = compose("docker-compose.yml")
    lms = compose("lms-simulator/docker-compose.yml")
    assert pacewise["name"] != lms["name"]
    assert set(lms["services"]) == {"lms-postgres", "lms-simulator"}
    assert not set(lms["services"]) & set(pacewise["services"])
    assert "lms_postgres_data" not in pacewise["volumes"]
    assert "pacewise_lms_postgres_data" in lms["volumes"]["lms_postgres_data"]["name"]
    assert "pacewise_lms_uploads" in lms["volumes"]["lms_uploads"]["name"]
    assert all(volume["external"] for volume in lms["volumes"].values())


def test_lms_has_no_published_ports_and_database_isolated():
    lms = compose("lms-simulator/docker-compose.yml")
    assert all(not service.get("ports") for service in lms["services"].values())
    assert lms["services"]["lms-simulator"]["environment"]["LMS_WEB_ENABLED"] == "false"
    assert lms["services"]["lms-postgres"]["networks"] == ["database"]
    assert all(network["internal"] for network in lms["networks"].values())
    build = lms["services"]["lms-simulator"]["build"]
    context = (ROOT / "lms-simulator" / build["context"]).resolve()
    assert context == ROOT
    assert (context / build["dockerfile"]).is_file()


def test_pacewise_standalone_has_no_lms_network_or_service_dependency():
    pacewise = compose("docker-compose.yml")
    assert "lms-service" not in pacewise.get("networks", {})
    for name, service in pacewise["services"].items():
        assert set(service.get("depends_on", [])) <= set(pacewise["services"])
        if name in {"backend", "worker"}:
            assert "lms-service" not in service.get("networks", [])
            assert service["environment"]["COURSE_SOURCE_MODE"] == "standalone"
            assert "LMS_BASE_URL" not in service["environment"]
        else:
            assert "lms-service" not in service.get("networks", [])
    assert pacewise["services"]["frontend"]["build"]["args"]["VITE_LMS_WEB_ENABLED"] == "false"
    assert pacewise["services"]["frontend"]["build"]["args"]["VITE_COURSE_SOURCE_MODE"] == "standalone"


def test_web_can_be_restored_explicitly_without_moving_database():
    web = compose("lms-simulator/docker-compose.web.yml")["services"]
    assert set(web) == {"lms-simulator"}
    assert web["lms-simulator"]["ports"] == ["127.0.0.1:8010:8010"]
    assert web["lms-simulator"]["environment"]["LMS_WEB_ENABLED"] == "true"
    navigation = compose("docker-compose.lms-web.yml")["services"]["frontend"]["build"]["args"]
    assert navigation["VITE_LMS_WEB_ENABLED"] == "true"


def test_backend_image_refreshes_fixable_os_vulnerabilities():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "apt-get update" in dockerfile
    assert "apt-get upgrade -y" in dockerfile

    ci = compose(".github/workflows/ci.yml")
    image_build = next(
        step
        for step in ci["jobs"]["container-scan"]["steps"]
        if step.get("name") == "Build image"
    )
    assert "docker build --pull" in image_build["run"]

    deploy = compose(".github/workflows/deploy.yml")
    backend_build = next(
        step
        for step in deploy["jobs"]["build-and-push"]["steps"]
        if step.get("name") == "Build and push backend"
    )
    assert backend_build["with"]["pull"] is True


def test_cd_pushes_only_commit_scoped_immutable_tags():
    deploy = compose(".github/workflows/deploy.yml")
    steps = deploy["jobs"]["build-and-push"]["steps"]
    for name, output, existence_output in (
        ("Build and push backend", "${{ steps.images.outputs.backend_image }}", "backend_exists"),
        ("Build and push frontend", "${{ steps.images.outputs.frontend_image }}", "frontend_exists"),
    ):
        build = next(step for step in steps if step.get("name") == name)
        tags = str(build["with"]["tags"])
        assert tags.strip() == output
        assert ":latest" not in tags
        assert existence_output in build["if"]
    existing = next(step for step in steps if step.get("name") == "Check immutable images already exist")
    assert "describe-images" in existing["run"]
    assert "ImageNotFoundException" in existing["run"]
    assert '$ErrorActionPreference = "Continue"' in existing["run"]
    assert "$exitCode = $LASTEXITCODE" in existing["run"]
    assert "$global:LASTEXITCODE = 0" in existing["run"]
    assert "--no-cli-pager" in existing["run"]


def test_frontend_production_build_has_enough_heap_for_typescript_and_vite():
    ci = compose(".github/workflows/ci.yml")
    build = next(
        step
        for step in ci["jobs"]["lint-and-test"]["steps"]
        if step.get("name") == "Build frontend production bundle"
    )
    assert build["env"]["NODE_OPTIONS"] == "--max-old-space-size=4096"


def test_ec2_release_restores_https_and_loads_provider_key_from_secrets_manager():
    deploy = compose(".github/workflows/deploy.yml")
    validate = deploy["jobs"]["validate-release"]["steps"][0]
    assert "OPENAI_SECRET_ID" in validate["env"]
    assert "OPENAI_SECRET_ID" in validate["run"]

    send = next(
        step for step in deploy["jobs"]["deploy"]["steps"] if step.get("name") == "Send release to EC2"
    )
    assert "deploy/Caddyfile" in send["run"]
    assert "OPENAI_SECRET_ID" in send["env"]
    assert "OPENAI_SECRET_ID=" in send["run"]

    script = (ROOT / "deploy/deploy-ec2.sh").read_text(encoding="utf-8")
    assert "aws secretsmanager get-secret-value" in script
    assert 'readonly SECRETS_ENV="$DEPLOY_DIR/secrets.env"' in script
    assert "print_diagnostics" in script
    assert "Previous image set restored and verified healthy." in script
    assert "Rollback image set is not healthy." in script

    production = compose("deploy/docker-compose.ec2.yml")
    assert production["services"]["caddy"]["ports"] == ["80:80", "443:443"]
    assert production["services"]["frontend"]["expose"] == ["80"]
    for service in ("migrate", "backend", "worker", "notification-worker"):
        assert any("secrets.env" in item for item in production["services"][service]["env_file"])


def test_ec2_schema_revision_matches_the_application_image():
    schema_source = (ROOT / "src/schema.py").read_text(encoding="utf-8")
    expected = re.search(r'^SCHEMA_REVISION = "([^"]+)"$', schema_source, re.MULTILINE)
    assert expected is not None
    production = compose("deploy/docker-compose.ec2.yml")
    assert production["x-backend-environment"]["DATABASE_SCHEMA_REVISION"] == expected.group(1)


def test_runtime_example_does_not_store_the_provider_secret():
    runtime_example = (ROOT / "deploy/runtime.env.example").read_text(encoding="utf-8")
    assert not re.search(r"^OPENAI_API_KEY=", runtime_example, re.MULTILINE)
