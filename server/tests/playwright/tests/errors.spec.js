import { test, expect } from '@playwright/test';

test.describe('Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('Invalid Credentials', async ({ page }) => {
    const authModal = page.locator('#authModal');
    if (await authModal.isHidden()) {
        await page.locator('#loginBtn').click();
    }
    
    await page.fill('#loginEmail', 'nonexistent@example.com');
    await page.fill('#loginPassword', 'wrongpassword');
    await page.locator('#loginForm button:has-text("Login")').click();

    await expect(page.locator('#authModal')).toBeVisible();
    
    const errorMsg = page.locator('#loginError');
    await expect(errorMsg).toBeVisible();
    await expect(errorMsg).not.toBeEmpty();
  });

  test('Upgrade Required Modal', async ({ page }) => {
    const loginEmail = page.locator('#loginEmail');
    if (await loginEmail.isHidden()) {
        await page.locator('#loginBtn').click({ force: true });
    }
    await expect(loginEmail).toBeVisible();
    await loginEmail.fill('admin');
    await page.fill('#loginPassword', 'admin123');
    await page.locator('#loginForm button:has-text("Login")').click();
    await expect(page.locator('#userProfileHeader')).toBeVisible();
    
    // Set tier to free
    const settingsNav = page.locator('.nav-btn[data-view="settings"]');
    await settingsNav.click();
    await expect(page.locator('#settingsView')).toBeVisible();

    await page.fill('#adminUserId', '3');
    await page.selectOption('#adminTierSelect', 'free');
    await page.locator('button:has-text("Set Tier")').click();
    await page.reload();

    const sessionsNav = page.locator('.nav-btn[data-view="sessions"]');
    await sessionsNav.click();
    await expect(page.locator('#sessionsView')).toBeVisible();

    // Since it's a new DB, we might need to wait for the seeded session to load
    const sessionCard = page.locator('.session-card').first();
    await sessionCard.waitFor({ state: 'attached' });
    // Use evaluate to click if it's technically "hidden" by CSS but functional
    await page.evaluate(() => document.querySelector('.session-card')?.click());
    
    await page.locator('.actions-dropdown-btn').click();
    
    const exportBtn = page.locator('.dropdown-item:has-text("Export ZIP")');
    await exportBtn.click();
    
    const upgradeModal = page.locator('#upgradeModal');
    await expect(upgradeModal).toBeVisible();
    await expect(upgradeModal).toContainText(/Upgrade to Pro/i);
  });

  test('Connection Timeout / Server Down', async ({ page }) => {
    // Wait for any initial login toast to clear
    const toast = page.locator('#toast');
    await expect(toast).not.toHaveClass(/active/, { timeout: 10000 });

    await page.route('**/api/health', route => route.abort('failed'));
    await page.reload();
    await expect(toast).toContainText(/Connection error/i, { timeout: 15000 });
  });
});
