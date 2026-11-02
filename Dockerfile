# PVFSS ERP: one image with Frappe, ERPNext and the pvfss app, for local use.
# Run it with `docker compose up` (see docker-compose.yml and docker/README.md).
ARG BASE_IMAGE=frappe/bench:latest
FROM ${BASE_IMAGE}

ARG FRAPPE_VERSION=v16.54.0
ARG ERPNEXT_VERSION=v16.53.0
ARG FRAPPE_REPO=https://github.com/frappe/frappe
ARG ERPNEXT_REPO=https://github.com/frappe/erpnext

WORKDIR /home/frappe
RUN bench init frappe-bench \
        --frappe-path ${FRAPPE_REPO} \
        --frappe-branch ${FRAPPE_VERSION} \
        --python "$(command -v python3.14 || command -v python3)" \
        --skip-redis-config-generation \
        --no-backups \
    && cd frappe-bench \
    && bench get-app --branch ${ERPNEXT_VERSION} erpnext ${ERPNEXT_REPO} \
    && rm -rf apps/*/.git ~/.cache

WORKDIR /home/frappe/frappe-bench
COPY --chown=frappe:frappe . apps/pvfss
RUN env/bin/pip install --no-cache-dir -e apps/pvfss \
    && printf "\npvfss\n" >> sites/apps.txt && sed -i "/^$/d" sites/apps.txt \
    && bench build --app pvfss \
    && cp -a sites /home/frappe/sites-image

COPY --chown=frappe:frappe --chmod=755 docker/entrypoint.sh /home/frappe/entrypoint.sh

EXPOSE 8000 9000
VOLUME /home/frappe/frappe-bench/sites
ENTRYPOINT ["/home/frappe/entrypoint.sh"]
