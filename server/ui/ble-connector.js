/**
 * ble-connector.js
 * Web Bluetooth module for communicating with the ESP32 Datalogger.
 * Handles discovery, connection, WiFi configuration, and status monitoring.
 */

class DataloggerBLE {
    constructor() {
        this.device = null;
        this.server = null;
        this.service = null;
        this.characteristics = new Map();

        this.connected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;

        // Service and Characteristic UUIDs (must match ESP32)
        this.SERVICE_UUID = '12345678-1234-5678-1234-567812345678';
        this.CHAR_NETWORKS_UUID = '12345678-1234-5678-1234-567812345001';
        this.CHAR_STATUS_UUID = '12345678-1234-5678-1234-567812345002';
        this.CHAR_CONFIGURE_UUID = '12345678-1234-5678-1234-567812345003';
        this.CHAR_DEVICE_INFO_UUID = '12345678-1234-5678-1234-567812345004';

        // Event Callbacks
        this.onConnect = null;
        this.onDisconnect = null;
        this.onStatusChange = null;
        this.onDeviceInfoChange = null;
    }

    /**
     * Check if Web Bluetooth is supported by the browser.
     * @returns {boolean}
     */
    static isSupported() {
        return 'bluetooth' in navigator;
    }

    /**
     * Scan for and connect to a Racesense Core BLE device.
     */
    async connect() {
        if (!DataloggerBLE.isSupported()) {
            throw new Error('Web Bluetooth is not supported in this browser.');
        }

        try {
            console.log('Requesting BLE device with service filtering...');
            // Explicitly filter by Service UUID - CRITICAL for macOS/iOS visibility
            this.device = await navigator.bluetooth.requestDevice({
                filters: [
                    { services: [this.SERVICE_UUID] },
                    { namePrefix: 'Racesense' },
                    { namePrefix: 'Datalogger' }
                ],
                optionalServices: [this.SERVICE_UUID]
            });

            this.device.addEventListener('gattserverdisconnected', (event) => this._onDisconnected(event));

            return await this._establishGATT();
        } catch (error) {
            console.error('BLE connection failed:', error);
            throw error;
        }
    }

    async _establishGATT() {
        console.log('Connecting to GATT server...');
        this.server = await this.device.gatt.connect();

        console.log('Fetching service...');
        this.service = await this.server.getPrimaryService(this.SERVICE_UUID);

        // Map all characteristics
        const uuids = [
            this.CHAR_NETWORKS_UUID,
            this.CHAR_STATUS_UUID,
            this.CHAR_CONFIGURE_UUID,
            this.CHAR_DEVICE_INFO_UUID
        ];

        for (const uuid of uuids) {
            const characteristic = await this.service.getCharacteristic(uuid);
            this.characteristics.set(uuid, characteristic);
        }

        // Subscribe to notifications
        await this._setupNotifications();

        this.connected = true;
        this.reconnectAttempts = 0;

        if (this.onConnect) this.onConnect();
        return true;
    }

    async _setupNotifications() {
        // Status updates
        const statusChar = this.characteristics.get(this.CHAR_STATUS_UUID);
        await statusChar.startNotifications();
        statusChar.addEventListener('characteristicvaluechanged', (event) => {
            const data = this._decodeJSON(event.target.value);
            if (this.onStatusChange) this.onStatusChange(data);
        });

        // Device Info updates (if ESP32 supports notify on this char)
        const infoChar = this.characteristics.get(this.CHAR_DEVICE_INFO_UUID);
        // We only subscribe if the char exists and properties allow logic
        // For now subscribe to both matching firmware implementation if needed
        // but firmware currently only notifies on Status.
    }

    async disconnect() {
        if (this.device && this.device.gatt.connected) {
            await this.device.gatt.disconnect();
        }
    }

    isConnected() {
        return this.connected && this.device && this.device.gatt.connected;
    }

    async _onDisconnected(event) {
        console.warn('BLE Disconnected');
        this.connected = false;
        if (this.onDisconnect) this.onDisconnect();

        // Attempt reconnection
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts}...`);
            setTimeout(async () => {
                try {
                    await this._establishGATT();
                } catch (e) {
                    console.error('Reconnection failed', e);
                }
            }, 2000);
        }
    }

    /**
     * WiFi Operations
     */

    async scanNetworks() {
        // First send "SCAN" command to trigger ESP32 refresh
        await this._writeCommand("SCAN");

        // Brief delay for ESP32 to scan
        await new Promise(r => setTimeout(r, 2000));

        const char = this.characteristics.get(this.CHAR_NETWORKS_UUID);
        const value = await char.readValue();
        return this._decodeJSON(value);
    }

    async getWifiStatus() {
        const char = this.characteristics.get(this.CHAR_STATUS_UUID);
        const value = await char.readValue();
        return this._decodeJSON(value);
    }

    async configureWifi(ssid, password, apiUrl = null) {
        const payload = { ssid, password };
        if (apiUrl) payload.api_url = apiUrl;
        return await this._writeCommand(JSON.stringify(payload));
    }

    async triggerSync() {
        return await this._writeCommand("SYNC");
    }

    async startAPMode() {
        return await this._writeCommand("START_AP");
    }

    async getDeviceInfo() {
        const char = this.characteristics.get(this.CHAR_DEVICE_INFO_UUID);
        const value = await char.readValue();
        return this._decodeJSON(value);
    }

    /**
     * Helpers
     */

    async _writeCommand(value) {
        const char = this.characteristics.get(this.CHAR_CONFIGURE_UUID);
        const encoder = new TextEncoder();
        await char.writeValue(encoder.encode(value));
    }

    _decodeJSON(dataView) {
        const decoder = new TextDecoder();
        const str = decoder.decode(dataView);
        try {
            return JSON.parse(str);
        } catch (e) {
            return str;
        }
    }
}

// Export for use in app.js
window.DataloggerBLE = DataloggerBLE;
