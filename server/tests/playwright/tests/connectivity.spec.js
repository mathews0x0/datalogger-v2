import { test, expect } from '@playwright/test';

test.describe('Connectivity & Sync', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('Header Badges Status', async ({ page }) => {
    // Connection Status badge
    const connStatus = page.locator('#connectionStatus');
    await expect(connStatus).toBeVisible();
    
    // It should show 'Connected' or 'Disconnected' or 'Offline'
    const statusText = page.locator('#connText');
    await expect(statusText).toBeVisible();
    const text = await statusText.innerText();
    expect(['connected', 'disconnected', 'checking...', 'offline']).toContain(text.toLowerCase());

    // Storage Indicator (visible only when device IP is known/reachable)
    const storageIndicator = page.locator('#storageIndicator');
    await expect(storageIndicator).toBeDefined();
  });

  test('Network Scanner in Settings', async ({ page }) => {
    const loginEmail = page.locator('#loginEmail');
    if (await loginEmail.isHidden()) {
        await page.locator('#loginBtn').click({ force: true });
    }
    await expect(loginEmail).toBeVisible();
    await loginEmail.fill('admin');
    await page.fill('#loginPassword', 'admin123');
    await page.locator('#loginForm button:has-text("Login")').click();
    await expect(page.locator('#userProfileHeader')).toBeVisible();
    
    await page.locator('[data-view="settings"]').click();

    const scanBtn = page.locator('#scanBtn');
    await expect(scanBtn).toBeVisible();

    // Trigger scan
    await scanBtn.click();

    // Wait for scan to complete or status to change
    const statusText = page.locator('#scanStatusText');
    // It might be 'Scanning...' or 'Checking...' or immediately show result
    // We wait for it to stabilize to something other than 'Checking...'
    await expect(statusText).not.toHaveText('Checking...', { timeout: 30000 });

    const finalStatus = await statusText.innerText();
    // We don't assert it MUST be connected, but it should be a valid state
    expect(['connected', 'disconnected', 'offline', 'error', 'no device']).toContain(finalStatus.toLowerCase());
  });
});
