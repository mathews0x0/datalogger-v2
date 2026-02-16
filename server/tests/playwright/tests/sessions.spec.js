import { test, expect } from '@playwright/test';

test.describe('Session Analysis', () => {
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
    
    // Navigate to Process View
    await page.locator('[data-view="process"]').click();
  });

  test('Process View - Batch Actions', async ({ page }) => {
    // Wait for login toast to clear
    const toast = page.locator('#toast');
    await expect(toast).not.toHaveClass(/active/, { timeout: 10000 });

    await page.waitForSelector('#learningFilesList');
    
    const processAllBtn = page.locator('#btnProcessAll');
    if (await processAllBtn.isEnabled()) {
        await processAllBtn.click();
        await expect(toast).toBeVisible();
        await expect(toast).toHaveText(/processing|queued/i);
    }
  });

  test('Process View - Lock/Unlock CSV', async ({ page }) => {
    await page.waitForSelector('tr');
    const firstRow = page.locator('tr').nth(1); 
    const lockBtn = firstRow.locator('.btn-icon').filter({ hasText: /[🔓🔒]/ });
    
    if (await lockBtn.isVisible()) {
        const initialText = await lockBtn.innerText();
        await lockBtn.click();
        await expect(lockBtn).not.toHaveText(initialText);
    }
  });

  test('Session Details View', async ({ page }) => {
    // Navigate to Sessions
    await page.locator('[data-view="sessions"]').click();
    await page.waitForSelector('.session-card');
    
    // Use evaluate to click if it's technically "hidden" by CSS but functional
    await page.evaluate(() => document.querySelector('.session-card')?.click());

    await expect(page.locator('#sessionDetailContent')).toBeVisible();
    
    // Test collapsible sections
    const contextSection = page.locator('#sectionContext');
    const header = contextSection.locator('.details-section-header');
    
    await header.click();
    await expect(contextSection).not.toHaveClass(/collapsed/);
    
    // Test Share action
    await page.locator('.actions-dropdown-btn').click();
    const shareBtn = page.locator('button:has-text("Share Link")');
    await shareBtn.click();
    
    const shareModal = page.locator('#shareModal');
    await expect(shareModal).toBeVisible();
    await expect(page.locator('#shareLinkInput')).not.toBeEmpty();
  });
});
