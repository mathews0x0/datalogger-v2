#!/bin/bash
# ==============================================================================
# RaceSense — Fast Sync Deployment to Utho Cloud
# This script intelligently pushes only changed files from your local Mac 
# to the live Utho server and instantly restarts the backend.
# ==============================================================================

# Exit immediately on failure, pipe failure, or unset variable usage
set -euo pipefail

SERVER_IP="103.189.89.142"
SSH_KEY="~/.ssh/utho_racesense"
REMOTE_PATH="/var/www/racesense/"

# Ensure we are running from the project root reliably
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "server" ] || [ ! -d "src" ]; then
    echo "❌ Error: Could not find 'server/' or 'src/' directories."
    echo "Make sure you are running this script somewhere within the datalogger-v2 root."
    exit 1
fi

echo "=========================================================="
echo " 🚀 Deploying RaceSense to Utho Cloud ($SERVER_IP)"
echo "=========================================================="

echo "[1/3] Analyzing changes..."

# Define rsync arguments
RSYNC_ARGS=(
  -avzC --delete
  --exclude='__pycache__'
  --exclude='.DS_Store'
  --exclude='node_modules'
  --exclude='data/'
  --exclude='*.db'
  --exclude='*.log'
  --exclude='ios/'
  --exclude='DerivedData/'
  --exclude='venv/'
  --exclude='.venv/'
  --exclude='*.pyc'
  -e "ssh -o StrictHostKeyChecking=no -i $SSH_KEY"
)

# Run a dry-run to get statistics
DRY_RUN_OUTPUT=$(rsync "${RSYNC_ARGS[@]}" --dry-run --itemize-changes ./server ./src root@$SERVER_IP:$REMOTE_PATH)

# Calculate counts
# Count total files evaluated (this involves looking at the directory structure locally, but rsync itemize only shows changes and directories). 
# A simple way to get 'evaluated': find ./server ./src -type f | wc -l
EVALUATED=$(find ./server ./src -type f \
  -not -path "*/__pycache__/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/ios/*" \
  -not -path "*/DerivedData/*" \
  -not -path "*/venv/*" \
  -not -path "*/.venv/*" \
  -not -name "*.pyc" \
  -not -name ".DS_Store" \
  -not -name "*.db" \
  -not -name "*.log" | wc -l | tr -d ' ')

# Count changed files (lines from itemize that don't start with '.' or 'c' for creation might be files, but usually files show as >f.. etc)
# We can just count lines that represent file transfers/deletions.
CHANGED=$(echo "$DRY_RUN_OUTPUT" | (grep -E '^>|^c|^<|^\*' || true) | wc -l | tr -d ' ')

echo "Evaluated - $EVALUATED files"
echo "Changed - $CHANGED files"
echo ""

if [ "$CHANGED" -gt 0 ]; then
    echo "Syncing changed files:"
    # Extract just file names from the dry run output
    echo "$DRY_RUN_OUTPUT" | (grep -E '^>|^c|^<|^\*' || true) | awk '{print $2}'
    echo ""
    
    # Actually run the sync (suppress standard verbose output to keep it clean)
    rsync "${RSYNC_ARGS[@]}" --quiet ./server ./src root@$SERVER_IP:$REMOTE_PATH
else
    echo "No files need syncing."
fi

echo ""
echo "[2/3] Verifying and updating Python dependencies..."
# Automatically ensure the cloud server installs any new libraries you added to requirements.txt
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" root@$SERVER_IP \
  "cd /var/www/racesense/server && source venv/bin/activate && pip install -r requirements.txt --quiet"

echo "[3/3] Restarting backend & web services..."
# Issue the daemon restart command
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" root@$SERVER_IP \
  "systemctl restart racesense && systemctl restart nginx && echo '   -> Systemctl reload complete!' "

echo "=========================================================="
echo " ✅ Deployment completed successfully at $(date)"
echo " 🌐 Your changes are now LIVE at https://racesense.in"
echo "=========================================================="
