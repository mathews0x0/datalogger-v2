# Racesense Playwright Test Suite

This directory contains automated browser tests for the Racesense Companion App.

## Prerequisites

- Node.js (v16+)
- Playwright dependencies

## Installation

Navigate to this directory and install dependencies:

```bash
cd server/tests/playwright
npm install
npx playwright install chromium
```

## Running Tests

To run all tests:

```bash
npx playwright test
```

To run with UI mode:

```bash
npx playwright test --ui
```

To run a specific test:

```bash
npx playwright test tests/auth.spec.js
```

## Configuration

The suite is configured in `playwright.config.js`. By default, it expects the app to be running at `http://localhost:5000`.

## Test Scenarios

### 1. User Login Flow (`tests/auth.spec.js`)
- Verifies that a user can open the login modal.
- Verifies that entering valid credentials (default: `admin`/`admin123`) successfully logs the user in.
- Checks for the success toast and header UI update.
