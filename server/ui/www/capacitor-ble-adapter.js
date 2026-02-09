import { BleClient, numbersToDataView } from '@capacitor-community/bluetooth-le';

const SERVICE_UUID = '12345678-1234-5678-1234-567812345678';
const CHAR_STATUS_UUID = '12345678-1234-5678-1234-567812345002';
const CHAR_CONFIGURE_UUID = '12345678-1234-5678-1234-567812345003';
const CHAR_DEVICE_INFO_UUID = '12345678-1234-5678-1234-567812345004';
const CHAR_CONFIG_DATA_UUID = '12345678-1234-5678-1234-567812345005';

/**
 * RacesenseBLE - Hybrid Burst Control Layer
 * Manages BLE connection and command channel to ESP32
 */
export class RacesenseBLE {
  constructor() {
    this.device = null;
  }
  
  async initialize() {
    await BleClient.initialize();
  }
  
  async connect() {
    this.device = await BleClient.requestDevice({
      namePrefix: 'Racesense',
      optionalServices: [SERVICE_UUID],
    });
    
    await BleClient.connect(this.device.deviceId, () => {
      console.log('Racesense device disconnected');
      this.device = null;
    });
    
    return this.device;
  }
  
  async sendCommand(command) {
    if (!this.device) throw new Error('Not connected');
    
    const encoder = new TextEncoder();
    await BleClient.write(
      this.device.deviceId,
      SERVICE_UUID,
      CHAR_CONFIGURE_UUID,
      numbersToDataView(Array.from(encoder.encode(command)))
    );
  }
  
  async pushConfig(config) {
    if (!this.device) throw new Error('Not connected');
    
    const payload = JSON.stringify(config);
    const encoder = new TextEncoder();
    const bytes = encoder.encode(payload);
    
    // Chunk if needed (BLE MTU ~512 bytes typical)
    const chunkSize = 500;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const chunk = bytes.slice(i, i + chunkSize);
      await BleClient.write(
        this.device.deviceId,
        SERVICE_UUID,
        CHAR_CONFIG_DATA_UUID,
        numbersToDataView(Array.from(chunk))
      );
    }
  }
  
  async subscribeToStatus(callback) {
    if (!this.device) throw new Error('Not connected');
    
    await BleClient.startNotifications(
      this.device.deviceId,
      SERVICE_UUID,
      CHAR_STATUS_UUID,
      (value) => {
        const decoder = new TextDecoder();
        const str = decoder.decode(value);
        try {
          callback(JSON.parse(str));
        } catch {
          callback({ raw: str });
        }
      }
    );
  }
}
