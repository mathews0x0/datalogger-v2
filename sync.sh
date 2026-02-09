#!/bin/bash
# Sync web assets to iOS/Android native projects

cd "$(dirname "$0")/server/ui"

echo "🔄 Syncing Capacitor..."
npm run sync

echo ""
echo "✅ Sync complete!"
echo ""
echo "Next steps:"
echo "  • Rebuild in Xcode: ⌘R"
echo "  • Or run: ./sync.sh run"

# Optional: Run on simulator if 'run' argument passed
if [ "$1" = "run" ]; then
    echo ""
    echo "🚀 Building and deploying to iOS simulator..."
    npx cap run ios --target "2DD97E31-F681-41D0-8453-3984DABAA57D"
fi
