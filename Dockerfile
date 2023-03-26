FROM registry.access.redhat.com/ubi9/ubi:latest

COPY requirements.txt /tmp/requirements.txt
COPY quay-demo-publisher.py /usr/local/bin/quay-demo-publisher.py
COPY quay-demo-readonly-mirror.py  /usr/local/bin/quay-demo-readonly-mirror.py
COPY quay-demo-stage-mirror.py /usr/local/bin/quay-demo-stage-mirror.py
COPY quay-demo-vulscore-images.py /usr/local/bin/quay-demo-vulscore-images.py
COPY quay-superuser-token.py /usr/local/bin/quay-superuser-token.py
COPY entrypoint.sh /entrypoint.sh
RUN dnf install -y pip skopeo ; pip install -r /tmp/requirements.txt ; rm -fR /root/.cache /var/cache/dnf

ENTRYPOINT ["/entrypoint.sh"]


