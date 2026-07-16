import argparse
import os
import tempfile
from pathlib import Path

import expmon
import local_collector


def main() -> None:
    original_config = local_collector.CONFIG
    original_ssh_path = local_collector.SSH_SERVERS_PATH
    original_snapshot = local_collector.LATEST_SNAPSHOT
    original_event_accumulator = local_collector.EventAccumulator
    original_api_token = local_collector.API_TOKEN
    original_snapshot_fixture_path = local_collector.SNAPSHOT_FIXTURE_PATH
    try:
        local_collector.API_TOKEN = ""
        assert local_collector.api_request_authorized(None)
        local_collector.API_TOKEN = "desktop-secret"
        assert local_collector.api_request_authorized("desktop-secret")
        assert not local_collector.api_request_authorized(None)
        assert not local_collector.api_request_authorized("wrong-secret")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            fixture_path = workspace / "snapshot.json"
            fixture_path.write_text(
                '{"hosts":[{"id":"ssh:demo"}],"runs":[{"id":"run-1","hostId":"ssh:demo"}],'
                '"sshServers":[{"id":"demo","name":"Demo"}]}',
                encoding="utf-8",
            )
            local_collector.SNAPSHOT_FIXTURE_PATH = fixture_path
            fixture_snapshot = local_collector.snapshot()
            assert fixture_snapshot["hosts"][0]["id"] == "ssh:demo", fixture_snapshot
            fixture_remote = local_collector.fixture_remote_resource_payload("demo")
            assert fixture_remote and fixture_remote["source"] == "agent-tunnel", fixture_remote
            assert fixture_remote["runs"][0]["id"] == "run-1", fixture_remote
            local_collector.SNAPSHOT_FIXTURE_PATH = original_snapshot_fixture_path

            project_root = workspace / "ExperimentA"
            run_cwd = project_root / "scripts" / "train"
            run_cwd.mkdir(parents=True)
            local_collector.SSH_SERVERS_PATH = workspace / "ssh-servers.json"

            local_collector.CONFIG = {
                **original_config,
                "experiment_roots": [str(project_root)],
                "run_discovery": {
                    **original_config.get("run_discovery", {}),
                    "explicit_rules": [],
                },
            }

            project = local_collector.detect_project("python train.py", str(run_cwd))
            assert project == "ExperimentA", project

            project_path = local_collector.project_path_for_cwd(str(run_cwd))
            assert project_path == project_root.resolve(), project_path

            projects = local_collector.projects_from_runs([
                {
                    "id": "run-1",
                    "project": project,
                    "cwd": str(run_cwd),
                    "status": "running",
                    "rootCreateTime": "2026-01-01 00:00:00",
                    "summary": {"gpuHours": 0, "avgGpuUtil": 0},
                }
            ])
            assert len(projects) == 1, projects
            assert projects[0]["name"] == "ExperimentA", projects[0]
            assert Path(projects[0]["path"]) == project_root.resolve(), projects[0]

            workspace_root = workspace / "WorkspaceRoot"
            nested_project_root = workspace_root / "NestedProject"
            nested_project_cwd = nested_project_root / "expmon-frontend"
            nested_project_cwd.mkdir(parents=True)
            local_collector.CONFIG = {
                **local_collector.CONFIG,
                "experiment_roots": [str(workspace_root)],
            }
            nested_projects = local_collector.projects_from_runs([
                {
                    "id": "nested-run-1",
                    "project": "NestedProject",
                    "cwd": str(nested_project_cwd),
                    "status": "running",
                    "rootCreateTime": "2026-01-01 00:00:00",
                    "summary": {"gpuHours": 0, "avgGpuUtil": 0},
                }
            ])
            assert len(nested_projects) == 1, nested_projects
            assert nested_projects[0]["name"] == "NestedProject", nested_projects[0]
            assert Path(nested_projects[0]["path"]) == nested_project_root.resolve(), nested_projects[0]

            local_collector.CONFIG = {
                **local_collector.CONFIG,
                "experiment_roots": [str(project_root)],
                "run_discovery": {
                    **local_collector.CONFIG.get("run_discovery", {}),
                    "explicit_rules": [
                        {"project": "ExplicitProject", "command_regex": "special_train"}
                    ],
                },
            }
            explicit = local_collector.detect_project("python special_train.py", str(run_cwd))
            assert explicit == "ExplicitProject", explicit

            stale_run_dir = workspace / "expmon-runs" / "ExperimentA" / "stale-running"
            stale_run_dir.mkdir(parents=True)
            local_collector.write_yaml(stale_run_dir / "manifest.yaml", {
                "schema_version": "expmon.v1",
                "run": {"run_id": "stale-running", "project": "ExperimentA", "name": "stale-running"},
                "host": {"host_id": "local"},
                "entrypoint": {"command": "python train.py", "cwd": str(run_cwd)},
                "process": {"root_pid": 999999999, "root_create_time": 1.0},
                "time": {"started_at": "2026-01-01T00:00:00"},
            })
            local_collector.write_json(stale_run_dir / "status.json", {
                "status": "running",
                "pid": 999999999,
                "started_at": "2026-01-01T00:00:00",
            })
            stale_run = local_collector.run_from_manifest(stale_run_dir, [])
            assert stale_run and stale_run["status"] == "finished", stale_run
            persisted_status = local_collector.read_json(stale_run_dir / "status.json")
            persisted_manifest = local_collector.read_yaml(stale_run_dir / "manifest.yaml")
            assert persisted_status["status"] == "finished", persisted_status
            assert persisted_status["ended_at"], persisted_status
            assert persisted_status["exit_code"] is None, persisted_status
            assert persisted_status["exit_code_known"] is False, persisted_status
            assert persisted_manifest["run"]["status"] == "finished", persisted_manifest
            assert persisted_manifest["time"]["ended_at"] == persisted_status["ended_at"], persisted_manifest

            tensorboard_run_dir = workspace / "expmon-runs" / "ExperimentA" / "tensorboard-run"
            tensorboard_output = workspace / "training-output" / "lightning_logs" / "version_0"
            tensorboard_run_dir.mkdir(parents=True)
            tensorboard_output.mkdir(parents=True)
            (tensorboard_run_dir / "metrics.jsonl").touch()
            event_file = tensorboard_output / "events.out.tfevents.test"
            event_file.touch()
            unrelated_events = workspace / "logs" / "other-run"
            unrelated_events.mkdir(parents=True)
            (unrelated_events / "events.out.tfevents.unrelated").touch()

            class FakeScalarEvent:
                def __init__(self, wall_time: float, step: int, value: float) -> None:
                    self.wall_time = wall_time
                    self.step = step
                    self.value = value

            class FakeEventAccumulator:
                def __init__(self, _path: str, size_guidance: dict[str, int]) -> None:
                    assert size_guidance == {"scalars": 0}

                def Reload(self) -> None:
                    return None

                def Tags(self) -> dict[str, list[str]]:
                    return {"scalars": ["train_loss", "val_loss", "test/loss", "epoch"]}

                def Scalars(self, tag: str) -> list[FakeScalarEvent]:
                    rows = {
                        "train_loss": [FakeScalarEvent(1_700_000_001, 10, 0.8)],
                        "val_loss": [FakeScalarEvent(1_700_000_002, 10, 0.7)],
                        "test/loss": [FakeScalarEvent(1_700_000_003, 10, 0.6)],
                        "epoch": [FakeScalarEvent(1_700_000_003, 10, 1.0)],
                    }
                    return rows[tag]

            local_collector.EventAccumulator = FakeEventAccumulator
            imported = local_collector.import_tensorboard_metrics(
                tensorboard_run_dir,
                f"python train.py --output_dir {tensorboard_output.parent.parent}",
                str(workspace),
            )
            assert imported["imported"] == 3, imported
            assert imported["eventFiles"] == 1, imported
            imported_metrics = local_collector.read_metrics(tensorboard_run_dir)
            imported_keys = {key for row in imported_metrics for key in row}
            assert {"train_loss", "valid_loss", "test_loss"}.issubset(imported_keys), imported_metrics
            repeated = local_collector.import_tensorboard_metrics(
                tensorboard_run_dir,
                f"python train.py --output_dir {tensorboard_output.parent.parent}",
                str(workspace),
            )
            assert repeated["imported"] == 0, repeated
            local_collector.EventAccumulator = original_event_accumulator

            adopted_logdir = workspace / "adopted-runs"
            adopted_args = argparse.Namespace(
                pid=os.getpid(),
                project="AdoptedProject",
                name="existing-training",
                logdir=str(adopted_logdir),
                cwd=str(run_cwd),
                host_id="remote-host",
                resource_type="gpu",
                hparams=None,
                tag=[],
                command_text="python train.py",
                log_file=None,
            )
            assert expmon.adopt(adopted_args) == 0
            adopted_dirs = list((adopted_logdir / "AdoptedProject").iterdir())
            assert len(adopted_dirs) == 1, adopted_dirs
            adopted_manifest = local_collector.read_yaml(adopted_dirs[0] / "manifest.yaml")
            adopted_status = local_collector.read_json(adopted_dirs[0] / "status.json")
            assert adopted_manifest["process"]["root_pid"] == os.getpid(), adopted_manifest
            assert adopted_manifest["process"]["adopted"] is True, adopted_manifest
            assert adopted_status["launcher"] == "expmon-adopt", adopted_status
            adopted_run = local_collector.run_from_manifest(adopted_dirs[0], [])
            assert adopted_run and adopted_run["accessLevel"] == "B", adopted_run

            remote_payload = local_collector.remote_host_payload(
                "remote-1",
                {"name": "H200", "host": "192.0.2.20", "username": "tester"},
                {
                    "host": {
                        "hostname": "h200",
                        "os": "Linux",
                        "cpuUsage": 10,
                        "memoryUsedGb": 8,
                        "memoryTotalGb": 80,
                    },
                    "runs": [adopted_run],
                },
                sampled_at="2026-01-01T00:00:00",
                latency_ms=1,
                remote_os="linux",
                source="agent-tunnel",
            )
            assert remote_payload["host"]["id"] == "ssh:remote-1", remote_payload
            assert remote_payload["host"]["runningRuns"] == 1, remote_payload
            assert remote_payload["runs"][0]["remote"] is True, remote_payload
            assert remote_payload["runs"][0]["hostId"] == "ssh:remote-1", remote_payload
            remote_projects = local_collector.projects_from_runs(remote_payload["runs"])
            assert len(remote_projects) == 1, remote_projects
            assert remote_projects[0]["name"] == "AdoptedProject", remote_projects
            assert remote_projects[0]["isGit"] is False, remote_projects

            local_collector.LATEST_SNAPSHOT = {"runs": remote_payload["runs"]}
            kill_status, kill_payload = local_collector.kill_run(adopted_run["id"])
            assert kill_status == 409, kill_payload
            assert "remote" in kill_payload["error"], kill_payload

            bundle_bytes = local_collector.base64.b64decode(local_collector.remote_agent_bundle_text())
            with local_collector.zipfile.ZipFile(local_collector.io.BytesIO(bundle_bytes)) as archive:
                assert set(archive.namelist()) == set(local_collector.REMOTE_AGENT_BUNDLE_FILES)
            python_path, install_root = local_collector.parse_remote_agent_prepare_output(
                "noise\nEXPMON_PYTHON=/opt/expmon/bin/python\nEXPMON_ROOT=/home/test/.local/share/expmon\n"
            )
            assert python_path == "/opt/expmon/bin/python", python_path
            assert install_root == "/home/test/.local/share/expmon", install_root
            assert local_collector.remote_agent_cli_path(install_root) == "/home/test/.local/share/expmon/scripts/expmon.py"
            prepare_command = local_collector.remote_agent_prepare_python_command()
            assert "psutil" in prepare_command and ".venv" in prepare_command, prepare_command

            assert local_collector.safe_git_relative_path("src/App.tsx")
            assert local_collector.safe_git_relative_path("docs/run protocol.md")
            assert not local_collector.safe_git_relative_path("")
            assert not local_collector.safe_git_relative_path("../outside.txt")
            assert not local_collector.safe_git_relative_path("/tmp/outside.txt")
            assert not local_collector.safe_git_relative_path(r"Z:\absolute\outside.txt")
            assert not local_collector.safe_git_relative_path("src/../outside.txt")

            status, payload = local_collector.save_ssh_server({
                "name": "remote-test",
                "host": "127.0.0.1",
                "port": 22,
                "username": "tester",
                "authType": "password",
                "password": "secret",
            })
            assert status == 200, payload
            server_id = payload["server"]["id"]
            status, payload = local_collector.test_ssh_server(server_id)
            assert status == 200, payload
            assert payload["ok"] is False, payload
            if not local_collector.shutil.which("sshpass"):
                assert payload["supported"] is False, payload
                assert "password" in payload["message"].lower(), payload

                status, payload = local_collector.ssh_remote_resource_snapshot(server_id)
                assert status == 200, payload
                assert payload["ok"] is False, payload
                assert payload["supported"] is False, payload

            status, payload = local_collector.validate_and_save_ssh_server({
                "name": "offline-remote",
                "host": "192.0.2.10",
                "port": 22,
                "username": "tester",
                "authType": "password",
                "password": "secret",
            })
            assert status == 200, payload
            assert payload["ok"] is True, payload
            assert payload["test"]["ok"] is False, payload
            assert any(server["name"] == "offline-remote" for server in local_collector.read_ssh_servers_raw())

            status, payload = local_collector.clear_ssh_servers()
            assert status == 200, payload
            assert local_collector.read_ssh_servers_raw() == []

        print("PASS: collector project root checks")
    finally:
        local_collector.CONFIG = original_config
        local_collector.SSH_SERVERS_PATH = original_ssh_path
        local_collector.LATEST_SNAPSHOT = original_snapshot
        local_collector.EventAccumulator = original_event_accumulator
        local_collector.API_TOKEN = original_api_token
        local_collector.SNAPSHOT_FIXTURE_PATH = original_snapshot_fixture_path


if __name__ == "__main__":
    main()
