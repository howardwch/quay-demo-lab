#!/opt/app-root/bin/python3 -Wignore

import requests
from time import sleep, time
from socket import gethostname
from datetime import datetime
import os
import logging

from prometheus_client import (
    multiprocess,
    push_to_gateway,
    Gauge, Counter,
    CollectorRegistry,
    REGISTRY,
    PROCESS_COLLECTOR,
    PLATFORM_COLLECTOR,
)
registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)

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

def fetch_states(URI):
    data = dict()
    for endpoint in ("instance", "endtoend"):
        try:
            rsp = requests.get(
                f"{URI}/health/{endpoint}", verify=os.environ.get("CA", False)
            )
            logging.debug(f"metrics request {URI}/health/{endpoint} response {rsp.status_code} {rsp.reason}")
        except Exception as e:
            logging.debug(f"metrics request {URI}/health/{endpoint} exception {e}")
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
    logging.debug(f"scratch data: {data}")
    QUAY_HEALTH_STATUS.labels(**data).set_to_current_time()
    return data


if __name__ == "__main__":
    import sys
    HOSTNAME = os.environ.get("QUAY_HOST", gethostname())
    PUSHGW = f"{os.environ.get('QUAY_PROM_URI', 'http://localhost:9091')}"
    HEALTH = os.environ.get("QUAY_HEALTH_URI", "http://localhost:8080")
    if bool(os.environ.get('DEBUG', False)):
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    else: logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    logging.info(f"Starting monitoring {HEALTH}")
    logging.info(f"Reporting at {PUSHGW}"
    )
    try:
        while True:
            try:
                data = data_to_metrics(
                    fetch_states(HEALTH)
                )
            except Exception as e:
                logging.error(f"scraping metrics {e}")
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
                    PUSHGW,
                    job="quay",
                    registry=registry,
                    grouping_key=dict(
                        instance=HOSTNAME,
                        host=HOSTNAME,
                    ),
                )
            except Exception as gwerr:
                logging.error(f"PushGateway error: {gwerr}")
            try:
                sleep(int(os.environ.get("INTERVAL", 5)))
            except (KeyboardInterrupt, Exception) as e:
                logging.info(f"shutting down on exception {e}")
                break
    except (KeyboardInterrupt, Exception) as e:
        logging.info(f"shutting down on exception {e}")