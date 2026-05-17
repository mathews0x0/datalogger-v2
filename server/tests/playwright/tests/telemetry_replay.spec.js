import { test, expect } from '@playwright/test';

test.describe('Telemetry Replay', () => {

  // Shared mock setup if needed, or keep inside tests
  
  test('Playback Controls', async ({ page }) => {
    // Mock the sessions API
    await page.route('**/api/sessions', async route => {
      const json = [{
        id: 1,
        name: 'Test Session',
        date: '2023-01-01',
        track: 'Test Track',
        laps: 5,
        best_lap: '1:30.000',
        meta: { session_id: '1' }
      }];
      await route.fulfill({ json });
    });

    // Mock session detail
    await page.route('**/api/sessions/1', async route => {
        const json = {
            id: 1,
            name: 'Test Session',
            meta: { session_id: '1', date: '2023-01-01' },
            laps: []
        };
        await route.fulfill({ json });
    });

    await page.route('**/api/sessions/1/playback', async route => {
      const json = {
        meta: { gps_lag_ms_applied: 175 },
        laps: [],
        rows: [
          { time: 0, lat: 10.0, lon: 77.0, speed_kmh: 80, heading_deg: 180, lean_deg: 5, long_g: 0.1, lat_g: 0.2, accel_g: 0.1, brake_g: 0, lap_number: null, lap_start: false, lap_end: false, sector_index: null, sector_start: false, sector_end: false, gps_is_fix: true, gps_is_valid: true },
          { time: 1, lat: 10.0001, lon: 77.0001, speed_kmh: 82, heading_deg: 182, lean_deg: 6, long_g: 0.2, lat_g: 0.25, accel_g: 0.2, brake_g: 0, lap_number: null, lap_start: false, lap_end: false, sector_index: null, sector_start: false, sector_end: false, gps_is_fix: false, gps_is_valid: true }
        ]
      };
      await route.fulfill({ json });
    });

    // Navigate to Home
    await page.goto('/');

    // Click on a session card
    const sessionCard = page.locator('.session-card').first();
    await expect(sessionCard).toBeVisible({ timeout: 10000 });
    await sessionCard.click();

    // Click 'Playback' button
    const replayButton = page.locator('button.btn-playback');
    await expect(replayButton).toBeVisible();
    await replayButton.click();

    // Verify #playbackModal
    const modal = page.locator('#playbackModal');
    await expect(modal).toBeVisible();

    // Verify Play/Pause button (#pbPlayPause)
    const playPauseBtn = page.locator('#pbPlayPause');
    await expect(playPauseBtn).toBeVisible();
    await playPauseBtn.click();

    // Verify Seek Slider (#pbSeek)
    const seekSlider = page.locator('#pbSeek');
    await expect(seekSlider).toBeVisible();
    await seekSlider.fill('50');

    // Verify Map Mode Radios
    const mapModeRadios = page.locator('input[name="pbMapMode"]');
    const firstRadio = mapModeRadios.first();
    await expect(firstRadio).toBeVisible();
    await firstRadio.check();
    await expect(firstRadio).toBeChecked();

    // Verify Lap Selector
    const lapSelect = page.locator('#pbLapSelect');
    await expect(lapSelect).toBeVisible();
    await expect(lapSelect).toBeEnabled();

    // Click 'Next Lap'
    const nextLapBtn = page.locator('button:has-text("Next Lap")');
    await expect(nextLapBtn).toBeVisible();
    await nextLapBtn.click();
  });

  test('Add Session Note', async ({ page }) => {
    // Reuse mock logic (can refactor to beforeEach later)
    await page.route('**/api/sessions', async route => {
        const json = [{
          id: 1,
          name: 'Test Session',
          date: '2023-01-01',
          track: 'Test Track',
          laps: 5,
          best_lap: '1:30.000',
          meta: { session_id: '1' }
        }];
        await route.fulfill({ json });
      });
  
      await page.route('**/api/sessions/1', async route => {
          const json = {
              id: 1,
              name: 'Test Session',
              meta: { session_id: '1', date: '2023-01-01' },
              laps: []
          };
          await route.fulfill({ json });
      });

      await page.route('**/api/sessions/1/playback', async route => {
          const json = {
              meta: { gps_lag_ms_applied: 175 },
              laps: [],
              rows: [
                  { time: 0, lat: 10.0, lon: 77.0, speed_kmh: 80, heading_deg: 180, lean_deg: 5, long_g: 0.1, lat_g: 0.2, accel_g: 0.1, brake_g: 0, lap_number: null, lap_start: false, lap_end: false, sector_index: null, sector_start: false, sector_end: false, gps_is_fix: true, gps_is_valid: true },
                  { time: 1, lat: 10.0001, lon: 77.0001, speed_kmh: 82, heading_deg: 182, lean_deg: 6, long_g: 0.2, lat_g: 0.25, accel_g: 0.2, brake_g: 0, lap_number: null, lap_start: false, lap_end: false, sector_index: null, sector_start: false, sector_end: false, gps_is_fix: false, gps_is_valid: true }
              ]
          };
          await route.fulfill({ json });
      });

    // Navigate to Home
    await page.goto('/');

    // Click on a session card
    const sessionCard = page.locator('.session-card').first();
    await expect(sessionCard).toBeVisible({ timeout: 10000 });
    await sessionCard.click();

    // Click 'Playback' button
    const replayButton = page.locator('button.btn-playback');
    await expect(replayButton).toBeVisible();
    await replayButton.click();

    // Verify #playbackModal
    const modal = page.locator('#playbackModal');
    await expect(modal).toBeVisible();

    // Click 'Add Note' button
    // It's likely an icon button with title="Add Note"
    const addNoteBtn = page.locator('button[onclick="showAddAnnotationModal()"]');
    await expect(addNoteBtn).toBeVisible();
    await addNoteBtn.click();

    // Verify #annotationModal becomes visible
    const annotationModal = page.locator('#annotationModal');
    await expect(annotationModal).toBeVisible();

    // Fill #annotationTextInput
    await page.fill('#annotationTextInput', 'Test Annotation 123');

    // Click 'Save Note'
    await page.locator('button:has-text("Save Note")').click();

    // Verify #annotationModal closes
    await expect(annotationModal).toBeHidden();

    // Verify note appears in list
    // The list is #pbAnnotationsList
    const annotationsList = page.locator('#pbAnnotationsList');
    await expect(annotationsList).toContainText('Test Annotation 123');
  });

});
