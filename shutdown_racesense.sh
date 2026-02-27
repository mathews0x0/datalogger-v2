#!/bin/bash
# Datalogger V2 - Remote Shutdown Script
# This script securely connects to the Utho Cloud server and shuts down the entire Linux OS.

echo "Initiating shutdown sequence for remote Utho Cloud Server (103.189.89.142)..."

# Send the shutdown command via SSH
ssh -o StrictHostKeyChecking=no -i ~/.ssh/utho_racesense root@103.189.89.142 "shutdown -h now"

echo ""
echo "✅ Shutdown command sent."
echo "⚠️ IMPORTANT: The server is now powered off. You cannot turn it back on via SSH."
echo "⚠️ To start the server again, you MUST log in to your Utho Dashboard and click 'Start Instance'."
