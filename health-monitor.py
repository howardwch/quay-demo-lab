#!/opt/app-root/bin/python3 -Wignore

import requests
from time import sleep, time
from socket import gethostname
from datetime import datetime
import os

from prometheus_client import (
    multiprocess,
    push_to_gateway,
    Gauge,
    CollectorRegistry,
    REGISTRY,
    PROCESS_COLLECTOR,
    PLATFORM_COLLECTOR,
)

QUAY_HEALTH_STATUS = Gauge(
    "quay_health_status",
    "quay_health_status health endpoint responses",
    [
        "auth",
        "database",
        "deadtime",
        "disk_space",
        "registry_gunicorn",
        "service_key",
        "web_gunicorn",
        "redis",
        "storage",
        "status_code",
    ],
)
[
    REGISTRY.unregister(c)
    for c in [
        PROCESS_COLLECTOR,
        PLATFORM_COLLECTOR,
        REGISTRY._names_to_collectors["python_gc_objects_collected_total"],
    ]
]
registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)


def fetch_states(URI):
    data = dict()
    for endpoint in ("instance", "endtoend"):
        try:
            rsp = requests.get(
                f"{URI}/health/{endpoint}", verify=os.environ.get("CA", False)
            )
        except Exception as e:
            return data
        services = rsp.json().get("data").get("services")
        data.update(dict(map(lambda x: (x, int(services[x])), services)))
        data["status_code"] = rsp.status_code
        if rsp.status_code >= 300:
            data["deadtime"] = int(time())
            print(f"response {rsp.status_code} {rsp.reason}")
        else:
            data["deadtime"] = 0
    return data


def data_to_metrics(data):
    if data['status_code'] >= 300:  value = 0
    else: value = 1
    QUAY_HEALTH_STATUS.labels(**data).set(value)
    return


if __name__ == "__main__":
    print(
        f"starting monitoring {os.environ.get('QUAY_HEALTH_URI', 'http://localhost:8080')}"
        + f" reporting at {os.environ.get('QUAY_PROM_URI', 'http://localhost:9091')}"
    )
    while True:
        try:
            data = data_to_metrics(
                fetch_states(os.environ.get("QUAY_HEALTH_URI", "http://localhost:8080"))
            )
        except Exception as e:
            data = data_to_metrics(
                dict(
                    auth=0,
                    database=0,
                    disk_space=0,
                    registry_gunicorn=0,
                    service_key=0,
                    web_gunicorn=0,
                    redis=0,
                    storage=0,
                    status_code=503,
                    deadtime=int(time()),
                )
            )
        try:
            push_to_gateway(
                f"{os.environ.get('QUAY_PROM_URI', 'http://localhost:9091')}/metrics",
                job="quay",
                registry=registry,
                grouping_key=dict(
                    instance=os.environ.get("QUAY_HOST", gethostname()),
                    host=os.environ.get("QUAY_HOST", gethostname()),
                ),
                timeout=300,
            )
        except Exception as gwerr:
            print(f"PushGateway error: {gwerr}")
        try:
            sleep(int(os.environ.get("INTERVAL", 5)))
        except (KeyboardInterrupt, Exception) as e:
            print(f"shutting down on exception {e}")
            break
