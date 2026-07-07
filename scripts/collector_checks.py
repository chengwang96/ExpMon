import tempfile
from pathlib import Path

import local_collector


def main() -> None:
    original_config = local_collector.CONFIG
    original_ssh_path = local_collector.SSH_SERVERS_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
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

            dataset_root = workspace / "Dataset"
            ards_root = dataset_root / "ARDS"
            ards_cwd = ards_root / "expmon-frontend"
            ards_cwd.mkdir(parents=True)
            local_collector.CONFIG = {
                **local_collector.CONFIG,
                "experiment_roots": [str(dataset_root)],
            }
            ards_projects = local_collector.projects_from_runs([
                {
                    "id": "ards-run-1",
                    "project": "ARDS",
                    "cwd": str(ards_cwd),
                    "status": "running",
                    "rootCreateTime": "2026-01-01 00:00:00",
                    "summary": {"gpuHours": 0, "avgGpuUtil": 0},
                }
            ])
            assert len(ards_projects) == 1, ards_projects
            assert ards_projects[0]["name"] == "ARDS", ards_projects[0]
            assert Path(ards_projects[0]["path"]) == ards_root.resolve(), ards_projects[0]

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


if __name__ == "__main__":
    main()
