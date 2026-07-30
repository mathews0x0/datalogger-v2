# Gunicorn configuration for RaceSense production server

import os

# Server socket
bind = '127.0.0.1:6969'

# Workers — 2 is enough for a low-traffic app on a 1-vCPU VPS
workers = 2
worker_class = 'sync'

# Timeout — analysis subprocess can take up to 120s per attempt
timeout = 120
graceful_timeout = 30

# Logging
accesslog = '/var/log/racesense/access.log'
errorlog = '/var/log/racesense/error.log'
loglevel = 'info'

# Process naming
proc_name = 'racesense'

# Reload on HUP signal (used by systemctl reload)
reload = False  # Don't auto-reload; use HUP signal via systemd

# Python path — ensure all modules are importable
pythonpath = ','.join([
    '/var/www/racesense/server/api',
    '/var/www/racesense/src',
    '/var/www/racesense/server',
])

# Preload app for faster worker spawns
preload_app = True
