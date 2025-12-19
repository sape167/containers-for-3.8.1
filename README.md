# CTFd Containers Plugin (Hardened + Race-Safe)

This is a hardened and reliability-focused fork of the CTFd “containers” plugin.

Key objectives:
- Race-safe spawning under concurrent requests (prevents duplicate containers per challenge/user or challenge/team).
- Database-enforced uniqueness (proper unique constraints).
- Multi-server compatible (`docker_servers` JSON mapping).
- Scheduler cleanup and stable expiry handling.

## Features

### Race-safe container spawn
When multiple requests hit `/containers/api/request` simultaneously, only one container is created and stored. Others return the existing instance.

### Docker host port assignment
Host ports are assigned by Docker (`ports={internal_port: None}`), avoiding race-prone port probing.

## Requirements
- CTFd running in Docker (compose recommended)
- Docker Engine reachable from the CTFd container (socket mount or remote endpoint)

## Installation

1. Copy the plugin directory into your CTFd instance:

cp -r containers /path/to/CTFd/CTFd/plugins/containers

2. Add this to docker-compose.yml:

services:
    ctfd:
        build:
            context:
            dockerfile: Dockerfile.ctfd-local

3. Make a file named Dockerfile.ctfd-local and add this to it:
	
FROM ctfd/ctfd:latest
USER root
RUN pip install --no-cache-dir \
    APScheduler==3.10.4 \
    docker==7.1.0 \
    paramiko==3.4.0
USER 1001


4. Restart CTFd:

docker compose restart <container name>

5. Configure plugin settings in admin panel:

use: "local": "unix:///var/run/docker.sock" on the first option.

use whatever options you like for the rest of the options


