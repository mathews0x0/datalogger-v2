import { test, expect } from '@playwright/test';

test.describe('Admin Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    const loginEmail = page.locator('#loginEmail');
    if (await loginEmail.isHidden()) {
        await page.locator('#loginBtn').click({ force: true });
    }
    await expect(loginEmail).toBeVisible();
    await loginEmail.fill('admin');
    await page.fill('#loginPassword', 'admin123');
    await page.locator('#loginForm button:has-text("Login")').click();
    await expect(page.locator('#userProfileHeader')).toBeVisible();
    
    // Navigate to Admin Panel
    const adminNav = page.locator('#adminNavBtn');
    await expect(adminNav).toBeVisible();
    await adminNav.click();
    await expect(page.locator('#adminView')).toBeVisible();
  });

  test('User Management Table', async ({ page }) => {
    await expect(page.locator('#adminUsersBody')).toBeVisible();
    
    // Search for a user
    const searchInput = page.locator('#adminSearchInput');
    await searchInput.fill('admin');
    await page.locator('button:has-text("Search")').click();
    
    // Verify results
    const rows = page.locator('#adminUsersBody tr');
    await expect(rows.first()).toBeVisible();
  });

  test('Tier Control', async ({ page }) => {
    await page.locator('[data-view="settings"]').click();
    
    const adminTools = page.locator('#adminToolsCard');
    await expect(adminTools).toBeVisible();
    
    await page.fill('#adminUserId', '3'); 
    await page.selectOption('#adminTierSelect', 'pro');
    await page.locator('button:has-text("Set Tier")').click();
    
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
    await expect(toast).toHaveText(/tier set to pro|User 3 tier set to pro/i);
  });
});
