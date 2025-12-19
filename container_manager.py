import atexit
import time
import json
import random
import socket

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers import SchedulerNotRunningError

import docker
import paramiko.ssh_exception
import requests

from CTFd.models import db
from .models import ContainerInfoModel


class ContainerException(Exception):
    pass


class ContainerManager:
    def __init__(self, settings: dict, app: Flask):
        self.settings = settings
        self.app = app
        self.client: dict[str, docker.DockerClient] = {}
        self.expiration_scheduler = None
        self.expiration_seconds = 0

        docker_servers_raw = settings.get("docker_servers")
        if not docker_servers_raw:
            return

        try:
            self._initialize_connections()
            self._initialize_expiration_scheduler()
        except ContainerException as e:
            print(f"[ContainerManager] Initialization failed: {e}")
            self.client = {}

    # ------------------------------------------------------------------
    # Docker connection handling
    # ------------------------------------------------------------------

    def _initialize_connections(self) -> None:
        servers = json.loads(self.settings.get("docker_servers", "{}"))

        if not isinstance(servers, dict) or not servers:
            raise ContainerException("docker_servers must be a non-empty JSON object")

        for name, server_url in servers.items():
            try:
                print(f"[ContainerManager] Connecting to Docker server '{name}': {server_url}")
                client = docker.DockerClient(base_url=server_url)
                client.ping()
                self.client[name] = client
                print(f"[ContainerManager] Connected to '{name}'")
            except Exception as e:
                raise ContainerException(f"Failed to connect to Docker server '{name}': {e}")

    def get_client_for_server(self, server: str) -> docker.DockerClient:
        if not self.client:
            raise ContainerException("Docker is not connected")

        if server not in self.client:
            raise ContainerException(f"Unknown Docker server '{server}'")

        client = self.client[server]
        try:
            client.ping()
        except Exception:
            raise ContainerException(f"Docker server '{server}' is not reachable")

        return client

    def is_connected(self) -> bool:
        try:
            for client in self.client.values():
                client.ping()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Expiration scheduler
    # ------------------------------------------------------------------

    def _initialize_expiration_scheduler(self) -> None:
        try:
            self.expiration_seconds = int(self.settings.get("container_expiration", 0)) * 60
        except (ValueError, TypeError):
            self.expiration_seconds = 0

        if self.expiration_seconds <= 0:
            return

        self.expiration_scheduler = BackgroundScheduler()
        self.expiration_scheduler.add_job(
            func=self.kill_expired_containers,
            trigger="interval",
            seconds=5,
        )
        self.expiration_scheduler.start()

        atexit.register(self._shutdown_scheduler)

    def _shutdown_scheduler(self):
        try:
            if self.expiration_scheduler:
                self.expiration_scheduler.shutdown()
        except SchedulerNotRunningError:
            pass

    def kill_expired_containers(self):
        with self.app.app_context():
            now = int(time.time())
            containers = ContainerInfoModel.query.all()

            for container in containers:
                if container.expires < now:
                    try:
                        self.kill_container(container.container_id)
                    except ContainerException:
                        pass

                    db.session.delete(container)

            db.session.commit()

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def create_container(
        self,
        chal_id: str,
        team_id: str,
        user_id: str,
        image: str,
        internal_port: int,
        command: str,
        volumes: str | None,
        server: str,
    ):
        client = self.get_client_for_server(server)

        kwargs = {}

        # ------------------ Resource limits ------------------
        if self.settings.get("container_maxmemory"):
            mem = int(self.settings["container_maxmemory"])
            if mem > 0:
                kwargs["mem_limit"] = f"{mem}m"

        if self.settings.get("container_maxcpu"):
            cpu = float(self.settings["container_maxcpu"])
            if cpu > 0:
                kwargs["cpu_quota"] = int(cpu * 100000)
                kwargs["cpu_period"] = 100000

        # ------------------ Volumes ------------------
        if volumes:
            try:
                volumes_dict = json.loads(volumes)
                kwargs["volumes"] = volumes_dict
            except json.JSONDecodeError:
                raise ContainerException("Volumes must be valid JSON")

        # ------------------ HARDENING DEFAULTS ------------------
        kwargs.setdefault("privileged", False)
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("cap_drop", ["ALL"])
        kwargs.setdefault("security_opt", ["no-new-privileges:true"])
        kwargs.setdefault("pids_limit", 256)
        kwargs.setdefault("init", True)
        kwargs.setdefault("tmpfs", {"/tmp": "", "/run": ""})

        # ------------------ Run container ------------------
        try:
            return client.containers.run(
                image=image,
                command=command,
                detach=True,
                auto_remove=False,
                ports={str(internal_port): None},  # Docker assigns host port safely
                environment={
                    "CHALLENGE_ID": chal_id,
                    "TEAM_ID": team_id,
                    "USER_ID": user_id,
                },
                **kwargs,
            )
        except docker.errors.ImageNotFound:
            raise ContainerException("Docker image not found")
        except docker.errors.APIError as e:
            raise ContainerException(str(e))

    def get_container_port(self, container_id: str, server: str) -> str | None:
        client = self.get_client_for_server(server)

        try:
            container = client.containers.get(container_id)
            ports = container.attrs["NetworkSettings"]["Ports"]
            for mappings in ports.values():
                if mappings:
                    return mappings[0]["HostPort"]
        except Exception:
            return None

        return None

    def is_container_running(self, container_id: str) -> bool:
        for client in self.client.values():
            try:
                container = client.containers.get(container_id)
                return container.status == "running"
            except docker.errors.NotFound:
                continue
        return False

    def kill_container(self, container_id: str):
        for client in self.client.values():
            try:
                c = client.containers.get(container_id)
                c.kill()
                c.remove(force=True)
                return
            except docker.errors.NotFound:
                continue
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Admin helpers
    # ------------------------------------------------------------------

    def get_images(self) -> list[str]:
        images = []
        for name, client in self.client.items():
            try:
                for img in client.images.list():
                    if img.tags:
                        images.append(img.tags[0])
            except Exception:
                continue
        return images

    def get_running_servers(self) -> list[str]:
        return list(self.client.keys())
