import { test, expect } from '@playwright/test';

test.describe('Track Management', () => {
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
    
    // Navigate to Tracks
    await page.locator('[data-view="tracks"]').click();
  });

  test('Track List Actions - Set Active', async ({ page }) => {
    // Wait for tracks to load
    await page.waitForSelector('.track-card');
    
    const trackItem = page.locator('.track-card').first();
    await expect(trackItem).toBeVisible();

    // Check if it's already active
    const activeBadge = trackItem.locator('.badge:has-text("ACTIVE")');
    if (await activeBadge.isHidden()) {
        const setActiveBtn = trackItem.locator('button:has-text("Set Active")');
        await setActiveBtn.click();

        const toast = page.locator('#toast');
        await expect(toast).toBeVisible();
        await expect(toast).toHaveText(/Track set as active|Pushing track data|Device not connected/i);
    }
  });

  test('Track List Actions - Rename', async ({ page }) => {
    await page.waitForSelector('.track-card');
    const trackItem = page.locator('.track-card').first();
    
    // Click edit button
    await trackItem.locator('.fa-edit').click();

    const renameModal = page.locator('#renameModal');
    await expect(renameModal).toBeVisible();

    const newName = 'New_Track_Name_' + Date.now();
    await page.fill('#renameInput', newName);
    await page.locator('button:has-text("Rename")').click();

    await expect(renameModal).toBeHidden();
    
    const sanitizedName = newName.toLowerCase().replace(/[^a-z0-9]+/g, '_');
    await expect(trackItem.locator('.track-name')).toHaveText(sanitizedName);
  });

  test('Track List Actions - Delete', async ({ page }) => {
    await page.waitForSelector('.track-card');
    const trackCount = await page.locator('.track-card').count();
    if (trackCount > 1) {
        const trackItem = page.locator('.track-card').last();
        const trackName = await trackItem.locator('.track-name').innerText();

        // Setup dialog listener for confirm()
        page.on('dialog', dialog => dialog.accept());
        
        await trackItem.locator('.fa-trash').click();

        // Verify it's gone from the list
        await expect(page.locator('.track-card', { hasText: trackName })).toBeHidden();
    }
  });

  test('Track Detail View', async ({ page }) => {
    await page.waitForSelector('.track-card');
    const trackItem = page.locator('.track-card').first();
    await trackItem.click(); // Click the card to view details

    await expect(page.locator('#trackDetailContent')).toBeVisible();
    await expect(page.locator('.quick-stats')).toBeVisible();
    
    // Test Mark Pit Lane
    const markPitBtn = page.locator('button:has-text("Mark Pit Lane")');
    await expect(markPitBtn).toBeVisible();
    await markPitBtn.click();
    
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
    await expect(toast).toHaveText(/Pit Lane marked|Device not connected/i); 
  });
});
