import { test, expect } from '@playwright/test';

test.describe('Team Features', () => {
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
    
    // Ensure Team tier for admin
    await page.locator('[data-view="settings"]').click();
    await page.fill('#adminUserId', '3'); 
    await page.selectOption('#adminTierSelect', 'team');
    await page.locator('button:has-text("Set Tier")').click();

    // Navigate to Teams
    const teamsNav = page.locator('.nav-btn[data-view="teams"]');
    await teamsNav.click();
    await expect(page.locator('#teamsView')).toBeVisible();
  });

  test('Team Dashboard & Invite Flow', async ({ page }) => {
    const teamCards = page.locator('#teamsList .track-card'); 
    if (await teamCards.count() === 0) {
        await page.locator('#createTeamBtn').click();
        await page.fill('#teamNameInput', 'Test Team ' + Date.now());
        await page.locator('#createTeamModal button:has-text("Create Team")').click();
        await page.waitForSelector('#teamsList .track-card');
    }

    await teamCards.first().click();
    await expect(page.locator('#teamDetailContent')).toBeVisible();
    
    const inviteBtn = page.locator('button:has-text("Invite Rider")');
    if (await inviteBtn.isVisible()) {
        await inviteBtn.click();
        await expect(page.locator('#teamInviteModal')).toBeVisible();
        await expect(page.locator('#teamInviteLinkInput')).not.toBeEmpty();
    }
  });

  test('Trackday Aggregation', async ({ page }) => {
    await page.locator('[data-view="sessions"]').click();
    await page.locator('button:has-text("New Trackday")').click();
    
    const trackdayName = `Test Trackday ${Date.now()}`;
    await page.fill('#tdName', trackdayName);
    const trackSelect = page.locator('#tdTrack');
    if (await trackSelect.locator('option').count() > 1) {
        await trackSelect.selectOption({ index: 1 });
    }
    await page.locator('button:has-text("Create Trackday")').click();
    
    await page.locator('.session-tab:has-text("Trackdays")').click();
    await expect(page.locator('.trackday-card', { hasText: trackdayName })).toBeVisible();
  });
});
