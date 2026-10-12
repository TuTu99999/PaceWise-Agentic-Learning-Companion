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
