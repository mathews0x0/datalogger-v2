import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    const loginEmail = page.locator('#loginEmail');
    if (await loginEmail.isHidden()) {
        await page.locator('#loginBtn').click({ force: true });
    }
    await expect(loginEmail).toBeVisible();
  });

  test('User Registration Flow', async ({ page }) => {
    // Switch to Register tab/form
    await page.locator('a:has-text("Register")').click();

    // Fill registration details
    await page.fill('#regName', 'Test User');
    const email = `testuser_${Date.now()}@example.com`;
    await page.fill('#regEmail', email);
    await page.fill('#regPassword', 'password123');

    // Click Register
    await page.locator('#registerForm button:has-text("Register")').click();

    // Verify success toast
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible({ timeout: 10000 });
    await expect(toast).toHaveText(/Registered! Please login/i);

    // Verify switch back to login form
    await expect(page.locator('#loginForm')).toBeVisible();
  });

  test('User Login Flow', async ({ page }) => {
    // Ensure we are on login form
    if (await page.locator('#loginForm').isHidden()) {
        await page.locator('a:has-text("Login")').click();
    }

    // Enter credentials
    await page.fill('#loginEmail', 'admin');
    await page.fill('#loginPassword', 'admin123');

    // Click Login
    await page.locator('#loginForm button:has-text("Login")').click();

    // Verify success
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible({ timeout: 10000 });
    await expect(toast).toHaveText(/Logged in successfully/i);

    // Verify header update
    await expect(page.locator('#userProfileHeader')).toBeVisible();
    await expect(page.locator('#loginBtn')).toBeHidden();
  });

  test('Duplicate Registration', async ({ page }) => {
    // Switch to Register tab
    await page.locator('a:has-text("Register")').click();

    // Fill existing email (admin)
    await page.fill('#regName', 'Existing User');
    await page.fill('#regEmail', 'admin@example.com'); 
    await page.fill('#regPassword', 'ValidPass123!');

    // Submit
    await page.locator('#registerForm button:has-text("Register")').click();

    // Expect error
    const errorMsg = page.locator('#regError');
    await expect(errorMsg).toBeVisible();
    await expect(errorMsg).toContainText(/Email already exists/i);
  });

  test('Weak Password', async ({ page }) => {
    // Switch to Register tab
    await page.locator('a:has-text("Register")').click();

    // Fill weak password
    await page.fill('#regName', 'Weak User');
    const email = `weak_${Date.now()}@test.com`;
    await page.fill('#regEmail', email);
    await page.fill('#regPassword', '123');

    // Submit
    await page.locator('#registerForm button:has-text("Register")').click();

    // Expect error
    const errorMsg = page.locator('#regError');
    // If validation is client-side HTML5, check that first
    const validationMessage = await page.locator('#regPassword').evaluate(el => el.validationMessage);
    
    if (validationMessage) {
        expect(validationMessage).toBeTruthy();
    } else {
        await expect(errorMsg).toBeVisible();
    }
  });

  test('Logout Flow', async ({ page }) => {
    // Login first
    await page.fill('#loginEmail', 'admin');
    await page.fill('#loginPassword', 'admin123');
    await page.locator('#loginForm button:has-text("Login")').click();

    // Verify login success
    await expect(page.locator('#userProfileHeader')).toBeVisible();

    // Click Logout
    await page.locator('#userProfileHeader button[onclick="logout()"]').click();

    // Verify logged out state
    await expect(page.locator('#loginBtn')).toBeVisible();
    await expect(page.locator('#userProfileHeader')).toBeHidden();
    
    // Toast check
    await expect(page.locator('#toast')).toHaveText(/Logged out/i);
  });
});

test.describe('Profile Management', () => {
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
    
    // Wait for login toast to clear
    const toast = page.locator('#toast');
    await expect(toast).not.toHaveClass(/active/, { timeout: 10000 });
    
    await expect(page.locator('#userProfileHeader')).toBeVisible();
  });

  test('Update Profile Details', async ({ page }) => {
    // Navigate to Settings
    await page.locator('[data-view="settings"]').click();

    // Find User Profile card
    const profileCard = page.locator('#userProfileCard');
    await expect(profileCard).toBeVisible();

    // Update details
    await page.fill('#profileName', 'Admin Updated');
    await page.fill('#profileBike', 'BMW S1000RR');
    await page.fill('#profileHomeTrack', 'Nurburgring');

    // Save changes
    await page.locator('button:has-text("Update Profile")').click();

    // Verify success toast
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
    await expect(toast).toHaveText(/Profile updated/i);

    // Reload and verify persistence
    await page.reload();
    await expect(page.locator('#profileName')).toHaveValue('Admin Updated');
    await expect(page.locator('#profileBike')).toHaveValue('BMW S1000RR');
    await expect(page.locator('#profileHomeTrack')).toHaveValue('Nurburgring');
  });
});
