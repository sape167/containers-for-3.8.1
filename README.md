# CTFd Containers Plugin (Hardened + Race-Safe)

This is a hardened and reliability-focused fork of the CTFd “containers” plugin.

Key objectives:
- Race-safe spawning under concurrent requests (prevents duplicate containers per challenge/user or challenge/team).
- Database-enforced uniqueness (proper unique constraints).
- More secure Docker defaults (cap drop, no-new-privileges, read-only rootfs, tmpfs, pids limit, etc.).
- Multi-server compatible (`docker_servers` JSON mapping).
- Scheduler cleanup and stable expiry handling.

## Features

### Race-safe container spawn
When multiple requests hit `/containers/api/request` simultaneously, only one container is created and stored. Others return the existing instance.

### Hardening defaults (container runtime)
Defaults applied to `docker.containers.run()`:
- `privileged=False`
- `read_only=True`
- `cap_drop=["ALL"]`
- `security_opt=["no-new-privileges:true"]`
- `pids_limit=256`
- `init=True`
- `tmpfs={"/tmp": "", "/run": ""}`

You can loosen these if your challenge images require additional privileges.

### Docker host port assignment
Host ports are assigned by Docker (`ports={internal_port: None}`), avoiding race-prone port probing.

## Requirements
- CTFd running in Docker (compose recommended)
- Docker Engine reachable from the CTFd container (socket mount or remote endpoint)
- MariaDB/MySQL supported DB (CTFd default)

## Installation

1. Copy the plugin directory into your CTFd instance:

cp -r containers /path/to/CTFd/CTFd/plugins/containers

2. Restart CTFd:

docker compose restart <container name>

3. Configure plugin settings in admin panel:

use: "local": "unix:///var/run/docker.sock" on the first option.

use whatever options you like for the rest of the options



