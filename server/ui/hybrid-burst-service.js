import { RacesenseBLE } from './capacitor-ble-adapter.js';
import { Filesystem, Directory } from '@capacitor/filesystem';

/**
 * HybridBurstService
 * Orchestrates the "Phase 2: WiFi AP Burst" flow
 */
class HybridBurstService {
  constructor() {
    this.ble = new RacesenseBLE();
    this.isSyncing = false;
    this.progressCallback = null;
    this.espIp = '192.168.4.1';
  }

  setProgressCallback(callback) {
    this.progressCallback = callback;
  }

  updateProgress(step, details = '') {
    console.log(`[HybridBurst] ${step}: ${details}`);
    if (this.progressCallback) {
      this.progressCallback({ step, details });
    }
  }

  async startSync() {
    if (this.isSyncing) return;
    this.isSyncing = true;

    try {
      this.updateProgress('BLE_CONNECTING', 'Connecting to Racesense...');
      await this.ble.initialize();
      await this.ble.connect();

      this.updateProgress('STARTING_AP', 'Requesting WiFi Burst mode...');
      await this.ble.sendCommand('START_AP');

      // Listen for AP Ready notification
      let apConfig = await this.waitForAPReady();
      
      this.updateProgress('JOINING_WIFI', `Joining ${apConfig.ssid}...`);
      await this.joinWifi(apConfig.ssid, apConfig.password);

      this.updateProgress('FETCHING_MANIFEST', 'Getting session list...');
      const manifest = await this.fetchManifest();
      
      const pendingSessions = manifest.sessions.filter(s => !s.synced);
      this.updateProgress('DOWNLOADING', `Downloading ${pendingSessions.length} sessions...`);

      for (let i = 0; i < pendingSessions.length; i++) {
        const session = pendingSessions[i];
        this.updateProgress('DOWNLOADING', `Session ${i + 1}/${pendingSessions.length}: ${session.id}`);
        await this.downloadSession(session);
        await this.ackSession(session.id);
      }

      this.updateProgress('AP_STOPPING', 'Finalizing sync...');
      await this.ble.sendCommand('STOP_AP');

      // On some platforms, we might want to disconnect from WiFi to return to LTE faster
      // but usually the OS handles this once the AP is gone.
      
      this.updateProgress('SYNC_COMPLETE', 'All sessions downloaded.');
    } catch (error) {
      console.error('[HybridBurst] Sync failed:', error);
      this.updateProgress('ERROR', error.message);
      throw error;
    } finally {
      this.isSyncing = false;
    }
  }

  async waitForAPReady() {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Timed out waiting for AP Ready notification'));
      }, 30000);

      this.ble.subscribeToStatus((status) => {
        if (status.ap_active && status.ap_ssid) {
          clearTimeout(timeout);
          resolve({
            ssid: status.ap_ssid,
            password: status.ap_password || 'racesense' // Default fallback
          });
        }
      });
    });
  }

  async joinWifi(ssid, password) {
    if (typeof WifiWizard2 === 'undefined') {
      // Fallback for development/non-native
      console.warn('WifiWizard2 not found. Skipping WiFi join.');
      return;
    }

    return new Promise((resolve, reject) => {
      WifiWizard2.formatWifiConfig(ssid, password, 'WPA', (config) => {
        WifiWizard2.addNetwork(config, () => {
          WifiWizard2.connectNetwork(ssid, () => {
            // Verify connection (Wait a bit for IP)
            setTimeout(() => resolve(), 3000);
          }, (err) => reject(new Error('Failed to connect to network: ' + err)));
        }, (err) => reject(new Error('Failed to add network: ' + err)));
      }, (err) => reject(new Error('Failed to format wifi config: ' + err)));
    });
  }

  async fetchManifest() {
    const response = await fetch(`http://${this.espIp}/api/manifest`);
    if (!response.ok) throw new Error('Failed to fetch manifest');
    return await response.json();
  }

  async downloadSession(session) {
    const response = await fetch(`http://${this.espIp}/api/sessions/${session.id}/download`);
    if (!response.ok) throw new Error(`Failed to download session ${session.id}`);
    
    const blob = await response.blob();
    const base64Data = await this.blobToBase64(blob);
    
    const fileName = `sessions/${session.id}.csv`;
    
    await Filesystem.writeFile({
      path: fileName,
      data: base64Data,
      directory: Directory.Data,
      recursive: true
    });
  }

  async ackSession(sessionId) {
    await fetch(`http://${this.espIp}/api/sessions/${sessionId}/ack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ synced: true })
    });
  }

  blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
}

export const hybridBurstService = new HybridBurstService();
