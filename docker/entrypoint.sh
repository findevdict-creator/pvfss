#!/bin/bash
# Starts PVFSS ERP: creates the site on first run, migrates it on later runs,
# then runs the web server, socket.io, the background worker and the scheduler.
set -euo pipefail

SITE="${SITE_NAME:-pvfss.localhost}"
DB_HOST="${DB_HOST:-mariadb}"
DB_PORT="${DB_PORT:-3306}"
REDIS="${REDIS_URL:-redis://redis:6379}"
cd /home/frappe/frappe-bench

# The sites folder is a volume. Refresh the parts that belong to the image
# (built assets and the app list) so a rebuilt image is picked up.
rm -rf sites/assets
cp -a /home/frappe/sites-image/assets sites/assets
cp /home/frappe/sites-image/apps.txt sites/apps.txt
[ -f sites/apps.json ] || cp /home/frappe/sites-image/apps.json sites/apps.json 2>/dev/null || true

bench set-config -g db_host "$DB_HOST"
bench set-config -gp db_port "$DB_PORT"
bench set-config -g redis_cache "$REDIS"
bench set-config -g redis_queue "$REDIS"
bench set-config -g redis_socketio "$REDIS"
bench set-config -gp socketio_port 9000
bench set-config -g default_site "$SITE"

echo "Waiting for MariaDB at $DB_HOST:$DB_PORT ..."
until python3 -c "import socket,sys; socket.create_connection(('$DB_HOST', $DB_PORT), 2)" 2>/dev/null; do
    sleep 2
done

if [ ! -f "sites/$SITE/site_config.json" ]; then
    echo "Creating site $SITE (first run, takes a few minutes) ..."
    bench new-site "$SITE" \
        --mariadb-root-password "${DB_ROOT_PASSWORD:-admin}" \
        --admin-password "${ADMIN_PASSWORD:-admin}" \
        --mariadb-user-host-login-scope='%' \
        --install-app erpnext
    bench --site "$SITE" set-config developer_mode 1
    # Local use only (GEN-63). Must be set before pvfss installs its security defaults.
    bench --site "$SITE" set-config pvfss_skip_2fa 1
    bench --site "$SITE" install-app pvfss
    bench --site "$SITE" set-config host_name "http://localhost:${HTTP_PORT:-8000}"
else
    echo "Migrating site $SITE ..."
    bench --site "$SITE" migrate
fi
bench --site "$SITE" clear-cache

trap 'kill 0' SIGINT SIGTERM
node apps/frappe/socketio.js &
bench worker &
bench schedule &
bench --site "$SITE" serve --port 8000 --noreload &
echo "PVFSS ERP is starting at http://localhost:${HTTP_PORT:-8000} (user Administrator)"
wait -n
exit 1
