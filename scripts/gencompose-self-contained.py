#!/usr/bin/env python

import argparse
import json
import os
import re

import yaml
from decouple import Config, RepositoryEnv


def gen_common_depends_on():
    return {
        "postgresql-local": {"condition": "service_healthy"},
        "redis-local": {"condition": "service_healthy"},
        "dials-init": {"condition": "service_completed_successfully"},
    }


def gen_volumes(paths_to_mount):
    volumes = ["./etl/:/home/app/etl"]

    # One of the paths_to_mount might be the MOUNTED_EOS_PATH,
    # since this can be an sshfs mount we cannot mount the path directly
    # if we don't update fuse.conf to allow_other (sshfs -o allow_other)
    # the mount will fail.
    # But we can mount the path right before the sshfs mount inside the container
    # which will work normally without setting allow_other option.
    mounts = []
    for path in paths_to_mount:
        path_before_mount = "/".join(path.split("/")[:-1])
        mounts.append(path_before_mount)
    mounts = list(set(mounts))
    mounts = sorted(mounts, key=lambda x: len(x))

    # Remove any path that is a subpath among all paths to mount
    filtered_mounts = []
    for mount in mounts:
        is_subpath = False
        for filtered_mount in filtered_mounts:
            if filtered_mount in mount:
                is_subpath = True
                continue
        if is_subpath is False:
            filtered_mounts.append(mount)

    volumes.extend([f"{mount}:{mount}" for mount in filtered_mounts])
    return volumes


def gen_compose_header(postgres_path, paths_to_mount):
    return {
        "services": {
            "postgresql-local": {
                "container_name": "postgresql-local",
                "image": "postgres",
                "restart": "always",
                "volumes": [f"{postgres_path}:/var/lib/postgresql/data"],
                "ports": ["5432:5432"],
                "environment": {"POSTGRES_USER": "postgres", "POSTGRES_PASSWORD": "postgres"},
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U postgres"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 5,
                },
            },
            "redis-local": {
                "container_name": "redis-local",
                "image": "redis",
                "restart": "always",
                "ports": ["6379:6379"],
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "--raw", "incr", "ping"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 5,
                },
            },
            "dials-init": {
                "container_name": "dials-init",
                "image": "dials_etl",
                "build": {
                    "dockerfile": "etl/Dockerfile",
                    "context": ".",
                    "args": ["UID", "GID"],
                },
                "volumes": gen_volumes(paths_to_mount),
                "command": "bash -c 'alembic upgrade head'",
                "depends_on": {
                    "postgresql-local": {"condition": "service_healthy"},
                    "redis-local": {"condition": "service_healthy"},
                },
            },
            "dials-purge": {
                "container_name": "dials-purge",
                "image": "dials_etl",
                "build": {
                    "dockerfile": "etl/Dockerfile",
                    "context": ".",
                    "args": ["UID", "GID"],
                },
                "volumes": gen_volumes(paths_to_mount),
                "command": "bash -c 'alembic downgrade -1'",
                "profiles": ["donotstart"],
                "depends_on": {
                    "postgresql-local": {"condition": "service_healthy"},
                    "redis-local": {"condition": "service_healthy"},
                },
            },
            "dials-beat-scheduler": {
                "container_name": "dials-beat-scheduler",
                "image": "dials_etl",
                "volumes": gen_volumes(paths_to_mount),
                "command": "bash -c 'celery --app=python beat --loglevel=INFO -S redbeat.RedBeatScheduler'",
                "depends_on": gen_common_depends_on(),
            },
            "dials-common-indexer": {
                "container_name": "dials-common-indexer",
                "image": "dials_etl",
                "volumes": gen_volumes(paths_to_mount),
                "command": "bash -c 'celery --app=python worker --loglevel=INFO --concurrency=1 --autoscale=1,0 --max-tasks-per-child=1 --hostname=common-indexer@%h --queues=common-indexer'",
                "depends_on": gen_common_depends_on(),
            },
            "dials-backend": {
                "container_name": "dials-backend",
                "image": "dials_backend",
                "build": {
                    "dockerfile": "backend/Dockerfile",
                    "context": ".",
                    "args": ["UID", "GID"],
                },
                "volumes": ["./backend/:/home/app/backend"],
                "command": "python manage.py runserver 0.0.0.0:8000",
                "depends_on": gen_common_depends_on(),
                "ports": ["8000:8000"],
            },
            "dials-frontend": {
                "container_name": "dials-frontend",
                "image": "dials_frontend",
                "build": {
                    "dockerfile": "frontend/Dockerfile",
                    "context": ".",
                    "args": ["UID", "GID"],
                },
                "volumes": ["./frontend/:/home/app/web/frontend"],
                "depends_on": gen_common_depends_on(),
                "ports": ["3000:3000"],
            },
            "flower": {
                "container_name": "dials-flower",
                "image": "dials_etl",
                "volumes": gen_volumes(paths_to_mount),
                "command": "bash -c 'celery --app=python flower'",
                "depends_on": gen_common_depends_on(),
                "environment": {"FLOWER_BASIC_AUTH": "admin:admin"},
                "ports": ["5555:5555"],
            },
        }
    }


def gen_compose_workspace_workers(paths_to_mount, db_name):
    return {
        f"dials-{db_name}-bulk": {
            "container_name": f"dials-{db_name}-bulk",
            "image": "dials_etl",
            "volumes": gen_volumes(paths_to_mount),
            "command": f"bash -c 'celery --app=python worker --loglevel=INFO --concurrency=1 --autoscale=1,0 --max-tasks-per-child=1 --hostname={db_name}-bulk@%h --queues={db_name}-bulk'",
            "depends_on": gen_common_depends_on(),
        },
        f"dials-{db_name}-priority": {
            "container_name": f"dials-{db_name}-priority",
            "image": "dials_etl",
            "volumes": gen_volumes(paths_to_mount),
            "command": f"bash -c 'celery --app=python worker --loglevel=INFO --concurrency=1 --autoscale=1,0 --max-tasks-per-child=1 --hostname={db_name}-priority@%h --queues={db_name}-priority'",
            "depends_on": gen_common_depends_on(),
        },
    }


def gen_compose_downloader_workers(paths_to_mount, pd_name):
    return {
        f"dials-{pd_name.lower()}-downloader-bulk": {
            "container_name": f"dials-{pd_name.lower()}-downloader-bulk",
            "image": "dials_etl",
            "volumes": gen_volumes(paths_to_mount),
            "command": f"bash -c 'celery --app=python worker --loglevel=INFO --concurrency=1 --autoscale=1,0 --max-tasks-per-child=1 --hostname={pd_name}-downloader-bulk@%h --queues={pd_name}-downloader-bulk'",
            "depends_on": gen_common_depends_on(),
        },
        f"dials-{pd_name.lower()}-downloader-priority": {
            "container_name": f"dials-{pd_name.lower()}-downloader-priority",
            "image": "dials_etl",
            "volumes": gen_volumes(paths_to_mount),
            "command": f"bash -c 'celery --app=python worker --loglevel=INFO --concurrency=1 --autoscale=1,0 --max-tasks-per-child=1 --hostname={pd_name}-downloader-priority@%h --queues={pd_name}-downloader-priority'",
            "depends_on": gen_common_depends_on(),
        },
    }


if __name__ == "__main__":
    cwd = os.getcwd()
    if os.path.basename(cwd) != "dials":
        raise Exception(f"Expected to be in dials directory, but got {cwd}")

    # CLI
    parser = argparse.ArgumentParser(description="Re-download files script.")
    parser.add_argument("--etl-env-file", help="Path to etl .env file.", default=f"{cwd}/etl/.env")
    parser.add_argument("--pg-persistent-path", help="Path to store postgres files.")
    args = parser.parse_args()

    if args.pg_persistent_path is None:
        raise Exception("You need to specify a persistent path to postgres")

    # Load ETL env variables
    config = Config(RepositoryEnv(args.etl_env_file))

    # Databases configured
    databases = config.get("DATABASES")
    databases = re.sub("\s+", "", databases).split(",")

    # ETL paths to mount in docker
    etl_config_fpath = config.get("ETL_CONFIG_FPATH")
    paths_to_mount = [
        config.get("MOUNTED_EOS_PATH", default=None),
        config.get("CERT_FPATH"),
        config.get("KEY_FPATH"),
        config.get("MOCKED_DBS_FPATH", default=None),
        etl_config_fpath,
    ]
    paths_to_mount = [elem for elem in paths_to_mount if elem is not None]

    # Primary datasets configured
    with open(etl_config_fpath) as f:
        primary_datasets = [elem for ws in json.load(f)["workspaces"] for elem in ws["primary_datasets"]]
        primary_datasets = sorted(set(primary_datasets))

    comments = """# Notes
#
# 1. This docker-compose is not production-ready, you should use it only for development purposes
#    if do not want to run the entire stack natively
"""

    docker_compose = gen_compose_header(args.pg_persistent_path, paths_to_mount)

    for db_name in databases:
        services = gen_compose_workspace_workers(paths_to_mount, db_name)
        docker_compose["services"].update(services)

    for pd_name in primary_datasets:
        services = gen_compose_downloader_workers(paths_to_mount, pd_name)
        docker_compose["services"].update(services)

    with open("docker-compose.yaml", "w") as f:
        f.write(comments + "\n")
        yaml.dump(docker_compose, f)