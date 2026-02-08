# Racesense Mobile App Setup Guide

**For Beginners to Mobile Development**

This guide walks you through setting up **Capacitor** to wrap the existing Racesense web UI into native iOS and Android apps. No prior mobile development experience required!

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Project Initialization](#2-project-initialization)
3. [Adding Platforms](#3-adding-platforms)
4. [Installing Required Plugins](#4-installing-required-plugins)
5. [Development Workflow](#5-development-workflow)
6. [Running on Devices](#6-running-on-devices)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

Before starting, you'll need to install the development tools for your target platforms.

### Required for All Development

| Tool | Version | Installation |
|------|---------|--------------|
| **Node.js** | 18+ LTS | [nodejs.org](https://nodejs.org/) |
| **npm** | 9+ | Comes with Node.js |
| **Git** | Latest | [git-scm.com](https://git-scm.com/) |

Verify your installation:

```bash
node --version    # Should show v18.x or higher
npm --version     # Should show 9.x or higher
git --version     # Any recent version
```

### For iOS Development (Mac Only)

> ⚠️ **iOS development requires a Mac.** There is no workaround.

| Tool | How to Install |
|------|----------------|
| **Xcode** | Mac App Store → Search "Xcode" → Install (large download, ~15GB) |
| **Xcode Command Line Tools** | `xcode-select --install` |
| **CocoaPods** | `sudo gem install cocoapods` |

After installing Xcode:

1. Open Xcode once to accept the license agreement
2. Go to **Xcode → Settings → Platforms** and ensure iOS is downloaded
3. Verify CocoaPods: `pod --version`

### For Android Development (Mac, Windows, or Linux)

| Tool | How to Install |
|------|----------------|
| **Android Studio** | [developer.android.com/studio](https://developer.android.com/studio) |
| **Java JDK** | Bundled with Android Studio (or install JDK 17) |

After installing Android Studio:

1. Open Android Studio and complete the setup wizard
2. Go to **Settings → Languages & Frameworks → Android SDK**
3. Install these SDK components:
   - **SDK Platforms**: Android 14 (API 34), Android 13 (API 33)
   - **SDK Tools**: Android SDK Build-Tools, Android Emulator, Android SDK Platform-Tools

4. Set environment variables (add to your shell profile):

**macOS/Linux** (`~/.zshrc` or `~/.bashrc`):
```bash
export ANDROID_HOME=$HOME/Library/Android/sdk   # macOS
# export ANDROID_HOME=$HOME/Android/Sdk         # Linux
export PATH=$PATH:$ANDROID_HOME/platform-tools
export PATH=$PATH:$ANDROID_HOME/tools
export PATH=$PATH:$ANDROID_HOME/tools/bin
```

**Windows** (System Environment Variables):
```
ANDROID_HOME = C:\Users\<YourName>\AppData\Local\Android\Sdk
PATH += %ANDROID_HOME%\platform-tools
```

Verify: `adb --version`

---

## 2. Project Initialization

Navigate to the Racesense UI directory and initialize Capacitor.

### Step 2.1: Navigate to the UI Directory

```bash
cd /home/mj/datalogger-v2/server/ui
```

### Step 2.2: Initialize npm (if not already done)

If there's no `package.json` in the directory:

```bash
npm init -y
```

### Step 2.3: Install Capacitor Core

```bash
npm install @capacitor/core @capacitor/cli
```

### Step 2.4: Initialize Capacitor

```bash
npx cap init Racesense com.racesense.app --web-dir .
```

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| `Racesense` | App Name | Displayed on the device home screen |
| `com.racesense.app` | App ID | Unique identifier (reverse domain format) |
| `--web-dir .` | Current directory | Where your `index.html` lives |

This creates a `capacitor.config.ts` (or `.json`) file in your project.

### Step 2.5: Update Configuration

Edit `capacitor.config.ts` to match Racesense requirements:

```typescript
import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.racesense.app',
  appName: 'Racesense',
  webDir: '.',
  
  server: {
    // Required: Allow HTTP (not HTTPS) for ESP32 local AP communication
    cleartext: true,
  },
  
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#1a1a2e',
      showSpinner: false,
    },
  },
  
  ios: {
    scheme: 'Racesense',
  },
  
  android: {
    allowMixedContent: true,
  },
};

export default config;
```

---

## 3. Adding Platforms

### Add iOS Platform

```bash
npx cap add ios
```

This creates an `ios/` folder with an Xcode project.

### Add Android Platform

```bash
npx cap add android
```

This creates an `android/` folder with an Android Studio project.

### Verify Both Platforms

```bash
ls -la
# You should see: ios/  android/  capacitor.config.ts  index.html  app.js  styles.css
```

---

## 4. Installing Required Plugins

Based on the Racesense mobile strategy, install these Capacitor plugins:

### Core Plugins (Essential)

```bash
# App lifecycle and core features
npm install @capacitor/app
npm install @capacitor/splash-screen
npm install @capacitor/status-bar

# BLE for ESP32 communication (CRITICAL)
npm install @capacitor-community/bluetooth-le

# File storage for caching downloaded CSVs
npm install @capacitor/filesystem

# Network status detection for cloud sync
npm install @capacitor/network

# User preferences/settings
npm install @capacitor/preferences
```

### Extended Plugins (Recommended)

```bash
# Local database for pending uploads and cached results
npm install @capacitor-community/sqlite

# Native HTTP for ESP32 file transfers
npm install @capacitor/http

# Background task completion (finish upload when app closes)
npm install @capacitor/background-task

# Notify user when sync completes
npm install @capacitor/local-notifications
```

### Sync to Native Projects

After installing plugins, sync them to the native projects:

```bash
npx cap sync
```

This copies your web assets AND updates native project dependencies.

---

## 5. Development Workflow

### The Golden Rule: Write → Copy → Run

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT CYCLE                             │
│                                                                  │
│   1. Edit Web Code              2. Copy to Native                │
│      (app.js, index.html,          npx cap copy                  │
│       styles.css)                                                │
│           │                            │                         │
│           ▼                            ▼                         │
│   ┌───────────────┐            ┌───────────────┐                 │
│   │   Your IDE    │    ───▶    │  ios/android  │                 │
│   │   (VS Code)   │            │  (native)     │                 │
│   └───────────────┘            └───────┬───────┘                 │
│                                        │                         │
│                                        ▼                         │
│                            3. Run in IDE/Device                  │
│                               Xcode / Android Studio             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Commands Cheat Sheet

| Command | What It Does |
|---------|--------------|
| `npx cap copy` | Copies web assets to native projects (fast) |
| `npx cap sync` | Copies assets AND updates native dependencies |
| `npx cap open ios` | Opens iOS project in Xcode |
| `npx cap open android` | Opens Android project in Android Studio |
| `npx cap run ios` | Build and run on iOS device/simulator |
| `npx cap run android` | Build and run on Android device/emulator |

### Typical Development Session

```bash
# 1. Make changes to your web code
#    Edit app.js, styles.css, index.html in your editor

# 2. Copy changes to native projects
npx cap copy

# 3. Run on device (or open in IDE for more control)
npx cap run android --target <device-id>
# or
npx cap open ios   # Then press ▶ in Xcode
```

### Live Reload (Optional but Helpful)

For faster iteration, you can enable live reload:

```bash
# Start a local dev server (you'll need to add one)
npx cap run android --livereload --external
```

> Note: Live reload requires a dev server. For this vanilla JS project, consider adding a simple server like `npx serve .`

---

## 6. Running on Devices

### Running on iOS Simulator

```bash
npx cap open ios
```

In Xcode:
1. Select a simulator from the device dropdown (e.g., "iPhone 15 Pro")
2. Press **▶** (Run) or `Cmd + R`

### Running on Physical iOS Device

1. Connect your iPhone via USB
2. In Xcode, select your device from the dropdown
3. You'll need to configure signing (see [Troubleshooting](#71-ios-signing-certificates))
4. Press **▶** to build and run

### Running on Android Emulator

```bash
npx cap open android
```

In Android Studio:
1. Click **Device Manager** (phone icon in toolbar)
2. Create a Virtual Device if you haven't (e.g., Pixel 7, API 34)
3. Start the emulator
4. Press **▶** (Run) or `Shift + F10`

### Running on Physical Android Device

1. Enable **Developer Options** on your phone:
   - Settings → About Phone → Tap "Build Number" 7 times
2. Enable **USB Debugging**:
   - Settings → Developer Options → USB Debugging → On
3. Connect via USB and accept the debugging prompt
4. In Android Studio, select your device and press **▶**

---

## 7. Troubleshooting

### 7.1 iOS Signing Certificates

**Error:** `Signing for "App" requires a development team`

**Solution:**

1. Open `ios/App/App.xcworkspace` in Xcode
2. Select the **App** project in the navigator (blue icon, top left)
3. Select **App** under "Targets"
4. Go to **Signing & Capabilities** tab
5. Check **Automatically manage signing**
6. Select your **Team**:
   - If you have an Apple Developer account, select it
   - If not, sign in with your personal Apple ID (free, limited to 7-day certs)

**For free Apple ID signing:**
- Apps will expire after 7 days
- Limited to 3 apps at a time
- Cannot distribute via TestFlight

### 7.2 Android SDK Path Issues

**Error:** `SDK location not found` or `ANDROID_HOME not set`

**Solution:**

1. Find your SDK location:
   - Open Android Studio → Settings → Languages & Frameworks → Android SDK
   - Copy the "Android SDK Location" path

2. Set the environment variable (add to `~/.zshrc` or `~/.bashrc`):
   
   ```bash
   export ANDROID_HOME=/path/to/your/Android/Sdk
   export PATH=$PATH:$ANDROID_HOME/platform-tools
   ```

3. Reload your shell:
   ```bash
   source ~/.zshrc  # or ~/.bashrc
   ```

4. Verify:
   ```bash
   echo $ANDROID_HOME
   adb --version
   ```

### 7.3 CocoaPods Issues (iOS)

**Error:** `pod: command not found` or pod install fails

**Solution:**

```bash
# Install CocoaPods
sudo gem install cocoapods

# If that fails (M1/M2 Mac), try:
brew install cocoapods

# Navigate to iOS folder and install pods
cd ios/App
pod install

# Return to project root
cd ../..
```

### 7.4 Gradle Build Failures (Android)

**Error:** `Could not determine the dependencies of task ':app:compileDebugJavaWithJavac'`

**Solution:**

1. Open Android Studio
2. Go to **File → Sync Project with Gradle Files**
3. If that fails, try **File → Invalidate Caches → Invalidate and Restart**

Or from command line:

```bash
cd android
./gradlew clean
./gradlew build
cd ..
```

### 7.5 BLE Permission Errors

**Error:** BLE scanning doesn't find devices

**iOS:**
- Add to `ios/App/App/Info.plist`:
  ```xml
  <key>NSBluetoothAlwaysUsageDescription</key>
  <string>Racesense needs Bluetooth to connect to your datalogger</string>
  <key>NSBluetoothPeripheralUsageDescription</key>
  <string>Racesense needs Bluetooth to connect to your datalogger</string>
  ```

**Android (API 31+):**
- Check that these permissions are in `android/app/src/main/AndroidManifest.xml`:
  ```xml
  <uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
  ```

### 7.6 HTTP Cleartext Traffic Blocked (Android)

**Error:** Network requests to ESP32 (192.168.4.1) fail

**Solution:** Ensure `android/app/src/main/AndroidManifest.xml` has:

```xml
<application
    android:usesCleartextTraffic="true"
    ...>
```

This is needed because the ESP32 AP serves content over HTTP, not HTTPS.

### 7.7 "App Not Installed" on Android

**Error:** App fails to install on device

**Possible causes:**
1. **Previous version conflict** - Uninstall the existing app first
2. **Debug vs Release** - Ensure you're not mixing signed/unsigned builds
3. **Storage full** - Check device storage

```bash
# Uninstall previous version
adb uninstall com.racesense.app

# Try again
npx cap run android
```

### 7.8 Changes Not Appearing in App

**Error:** You edited the web code but the app shows old content

**Solution:** You forgot to copy!

```bash
npx cap copy
```

Then rebuild in Xcode/Android Studio.

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           QUICK REFERENCE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INITIAL SETUP (one time):                                                   │
│  ─────────────────────────                                                   │
│    cd /home/mj/datalogger-v2/server/ui                                       │
│    npm install @capacitor/core @capacitor/cli                                │
│    npx cap init Racesense com.racesense.app --web-dir .                      │
│    npx cap add ios                                                           │
│    npx cap add android                                                       │
│    npm install @capacitor-community/bluetooth-le @capacitor/filesystem ...  │
│    npx cap sync                                                              │
│                                                                              │
│  DAILY WORKFLOW:                                                             │
│  ───────────────                                                             │
│    1. Edit web code (app.js, styles.css, index.html)                         │
│    2. npx cap copy                                                           │
│    3. npx cap open ios  OR  npx cap open android                             │
│    4. Press ▶ in IDE to run                                                  │
│                                                                              │
│  USEFUL COMMANDS:                                                            │
│  ─────────────────                                                           │
│    npx cap sync        # Copy + update native deps                           │
│    npx cap copy        # Copy web assets only (faster)                       │
│    npx cap doctor      # Diagnose common issues                              │
│    npx cap ls          # List installed platforms                            │
│                                                                              │
│  REQUIRED PLUGINS:                                                           │
│  ─────────────────                                                           │
│    @capacitor-community/bluetooth-le   # BLE for ESP32                       │
│    @capacitor/filesystem               # Store downloaded CSVs               │
│    @capacitor/network                  # Detect connectivity                 │
│    @capacitor/preferences              # User settings                       │
│    @capacitor-community/sqlite         # Local cache database                │
│    @capacitor/http                     # ESP32 file transfers                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

Once you have the app running on a device:

1. **Implement BLE scanning** - Use `@capacitor-community/bluetooth-le` to find and connect to your ESP32
2. **Test WiFi AP switching** - Practice the phone joining ESP32's access point
3. **Build the sync flow** - Follow the architecture in `docs/plans/mobile_app_strategy.md`

Good luck, and welcome to mobile development! 🏍️📱

---

*Last updated: 2026-02-09*
*See also: [mobile_app_strategy.md](plans/mobile_app_strategy.md) for architecture details*
