const { test, expect } = require('@playwright/test');

test('Hybrid Sync Flow (Mocked BLE & WiFi)', async ({ page }) => {
  // 1. Mock Network Requests (for when the app connects to the simulated AP)
  await page.route('http://192.168.4.1/manifest.json', async route => {
    console.log('Mocking manifest.json request');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { filename: 'session_123.csv', size: 1024 }
      ])
    });
  });

  await page.route('http://192.168.4.1/session_123.csv', async route => {
    console.log('Mocking session csv request');
    await route.fulfill({
      status: 200,
      contentType: 'text/csv',
      body: 'timestamp,x,y,z\n1000,0.1,0.2,0.9\n1010,0.1,0.2,0.9'
    });
  });

  // 2. Mock Web Bluetooth API
  await page.addInitScript(() => {
    class MockGattCharacteristic {
      constructor(service, uuid) {
        this.service = service;
        this.uuid = uuid;
      }
      async writeValue(value) {
        // Decode value to see if it's the START_AP command
        const decoder = new TextDecoder();
        try {
           const text = decoder.decode(value);
           console.log(`[MockBLE] writeValue to ${this.uuid}:`, text);
        } catch (e) {
           console.log(`[MockBLE] writeValue to ${this.uuid} (binary)`);
        }
        return Promise.resolve();
      }
      async readValue() {
        return Promise.resolve(new DataView(new ArrayBuffer(0)));
      }
    }

    class MockGattService {
      constructor(server, uuid) {
        this.server = server;
        this.uuid = uuid;
      }
      async getCharacteristic(uuid) {
        return new MockGattCharacteristic(this, uuid);
      }
    }

    class MockGattServer {
      constructor(device) {
        this.device = device;
        this.connected = false;
      }
      async connect() {
        this.connected = true;
        console.log('[MockBLE] GATT Server Connected');
        return this;
      }
      async getPrimaryService(uuid) {
        return new MockGattService(this, uuid);
      }
      disconnect() {
        this.connected = false;
        console.log('[MockBLE] GATT Server Disconnected');
      }
    }

    class MockBluetoothDevice {
      constructor() {
        this.id = 'mock-device-id';
        this.name = 'Mock ESP32 Device';
        this.gatt = new MockGattServer(this);
      }
      addEventListener(type, listener) {
        console.log(`[MockBLE] Event listener added: ${type}`);
      }
      removeEventListener(type, listener) {}
    }

    // Replace the real navigator.bluetooth
    navigator.bluetooth = {
      requestDevice: async (options) => {
        console.log('[MockBLE] requestDevice called with:', options);
        // Simulate user selecting the device immediately
        return new MockBluetoothDevice();
      },
      getAvailability: async () => true
    };
  });

  // 3. Navigate to the application
  await page.goto('/');

  // 4. Execute the Sync Flow
  const syncButton = page.locator('button[onclick="startHybridSync()"]');
  
  // Ensure button is ready
  await expect(syncButton).toBeVisible();
  
  // Click 'Sync with Device'
  await syncButton.click();

  // 5. Verify Intermediary State (Connecting Overlay)
  const connectingOverlay = page.locator('text=Connecting...');
  await expect(connectingOverlay).toBeVisible({ timeout: 5000 });

  // 6. Verify Final State (File Downloaded)
  const fileEntry = page.locator('text=session_123.csv');
  await expect(fileEntry).toBeVisible({ timeout: 15000 });
});
