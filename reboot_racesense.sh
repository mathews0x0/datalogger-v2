#!/bin/bash
# Datalogger V2 - Remote Startup/Restart Script
# This script restarts the backend python service and Nginx on the Utho server.

echo "⚠️ NOTE: If the Utho server is completely POWERED OFF, this script will timeout."
echo "⚠️ You must first click 'Start' in the Utho Web Dashboard to boot up the Linux OS."
echo ""
echo "Attempting to connect to 103.189.89.142 and restart Racesense services..."

ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -i ~/.ssh/utho_racesense root@103.189.89.142 \
  "systemctl restart racesense && systemctl restart nginx && echo '✅ Services Restarted Successfully!' && systemctl status racesense --no-pager | grep Active"
