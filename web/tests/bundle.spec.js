import {test, expect} from '@playwright/test';

test('actual production bundle initializes the real SDK without starting a call', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  // No SDK mock: this catches CommonJS/ESM interop failures in the shipped bundle.
  // Block external requests and never press Start, so this cannot consume credits.
  await page.route('https://**/*', route => route.abort());
  await page.route('**/demo/config', route => route.fulfill({json:{data:{
    enabled:true,public_key:'test-only-public-key',assistant_id:'test-assistant'
  }}}));
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Ready when you are');
  await expect(page.getByRole('button',{name:'Start demo call'})).toBeEnabled();
  expect(errors).toEqual([]);
});
