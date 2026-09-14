"""[Sol] Simule les pannes de déploiement, vérifie refus et restauration du proxy."""

import os
from pathlib import Path
import subprocess

import pytest

RELEASE = "a" * 12


@pytest.fixture()
def deployment(tmp_path):
    root = tmp_path / "server"
    (root / "proxy").mkdir(parents=True)
    (root / "proxy/Caddyfile").write_text("OLD CONFIG\n")
    (root / "current").write_text("trackmystart-previous\n")
    (root / "schema").write_text("schema-v1\n")
    config = tmp_path / "config"
    config.mkdir()
    (config / "app.env").touch()
    (config / "db_password").touch()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text("""#!/usr/bin/env python3
import os,sys
from pathlib import Path
args=' '.join(sys.argv[1:])
with open(os.environ['DOCKER_LOG'],'a') as f:f.write(args+'\\n')
mode=os.environ['FAILURE']
if 'image inspect' in args:print('sha256:immutable')
elif 'scripts/quality-gate' in args and mode=='tests':sys.exit(1)
elif 'ops/schema.py' in args:print('schema-v2' if mode=='schema' else 'schema-v1')
elif 'pg_dump' in args:
 if mode=='backup':sys.exit(1)
 print('FAKE BACKUP')
elif 'ops/smoke.py' in args:
 if mode=='candidate':sys.exit(1)
 if mode=='public' and '--url' in args:sys.exit(1)
""")
    docker.chmod(0o755)
    # [Sol] Le serveur réel est root ; la simulation CI ne change aucun propriétaire.
    install = binaries / "install"
    install.write_text("""#!/usr/bin/env python3
import os,sys
from pathlib import Path
assert sys.argv[1:-1] == ['-d','-m','700','-o','10001','-g','10001']
if os.environ['FAILURE']=='advertising_storage':sys.exit(1)
Path(sys.argv[-1]).mkdir(parents=True,exist_ok=True)
""")
    install.chmod(0o755)
    sleep = binaries / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(binaries) + ":" + os.environ["PATH"],
        "TRACKMYSTART_ROOT": str(root),
        "TRACKMYSTART_CONFIG": str(config),
        "DOCKER_LOG": str(tmp_path / "docker.log"),
    }
    return root, env


@pytest.mark.parametrize(
    "failure",
    ["tests", "schema", "backup", "advertising_storage", "candidate", "public"],
)
def test_failed_release_does_not_replace_previous(deployment, failure):
    root, env = deployment
    result = subprocess.run(
        ["bash", "ops/deploy-server", "image:test", RELEASE],
        env={**env, "FAILURE": failure},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, result.stdout
    assert (root / "current").read_text() == "trackmystart-previous\n"
    assert (root / "proxy/Caddyfile").read_text() == "OLD CONFIG\n"
    log = Path(env["DOCKER_LOG"]).read_text()
    if failure in {"tests", "schema", "backup", "advertising_storage"}:
        assert "run -d --name" not in log
    if failure == "public":
        assert log.count("caddy reload") >= 2, "Proxy précédent non restauré"


def test_valid_release_is_accepted(deployment):
    root, env = deployment
    result = subprocess.run(
        ["bash", "ops/deploy-server", "image:test", RELEASE],
        env={**env, "FAILURE": "none"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (root / "current").read_text().strip() == "trackmystart-" + RELEASE
    assert (
        root / "releases" / (RELEASE + ".image")
    ).read_text().strip() == "sha256:immutable"


def test_campaign_backup_and_persistent_mount(deployment):
    root, env = deployment
    store = root / "data/advertising"
    store.mkdir(parents=True)
    (store / "advertising.json").write_text('{"enabled":false}')
    result = subprocess.run(
        ["bash", "ops/deploy-server", "image:test", RELEASE],
        env={**env, "FAILURE": "none"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (
        root / f"backups/advertising-before-{RELEASE}.json"
    ).read_text() == '{"enabled":false}'
    log = Path(env["DOCKER_LOG"]).read_text()
    assert f"type=bind,src={store},dst=/var/lib/trackmystart" in log
    assert "ADS_CONFIG_PATH=/var/lib/trackmystart/advertising.json" in log
