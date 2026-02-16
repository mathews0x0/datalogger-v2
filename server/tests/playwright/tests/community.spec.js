import { test, expect } from '@playwright/test';

test.describe('Community & Social', () => {
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
    
    // Navigate to Community
    await page.locator('[data-view="community"]').click();
  });

  test('Community Feeds', async ({ page }) => {
    // Explore Feed
    await page.locator('[data-comm-tab="explore"]').click();
    await page.waitForSelector('#communitySessionsList');
    const items = page.locator('#communitySessionsList .session-card');
    if (await items.count() > 0) {
        await expect(items.first()).toBeVisible();
    } else {
        await expect(page.locator('#explorePanel .empty-state')).toBeVisible();
    }

    // Following Feed
    await page.locator('[data-comm-tab="following"]').click();
    await expect(page.locator('#followingPanel')).toBeVisible();
  });

  test('Leaderboards', async ({ page }) => {
    await page.locator('[data-comm-tab="leaderboards"]').click();
    const select = page.locator('#lbTrackSelect');
    await expect(select).toBeVisible();
    
    if (await select.locator('option').count() > 1) {
        await select.selectOption({ index: 1 });
        await expect(page.locator('.data-table')).toBeVisible();
    }
  });

  test('User Profiles & Follow', async ({ page }) => {
    await page.locator('[data-comm-tab="explore"]').click();
    await page.waitForSelector('#communitySessionsList');
    
    const userLink = page.locator('.rider-name, [onclick*="showUserProfile"]').first();
    if (await userLink.isVisible()) {
        const userName = await userLink.innerText();
        await userLink.click();

        await expect(page.locator('#userProfileContent')).toBeVisible();
        await expect(page.locator('#userProfileContent h2')).not.toBeEmpty();

        const followBtn = page.locator('#followBtn');
        if (await followBtn.isVisible()) {
            const initialText = await followBtn.innerText();
            await followBtn.click();
            await expect(followBtn).not.toHaveText(initialText);
        }
    }
  });
});
