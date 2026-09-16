import {test, expect} from '@playwright/test';
import {build} from 'esbuild';
import {resolve} from 'node:path';

let javascript;
test.beforeAll(async () => {
  const result = await build({
    entryPoints: [resolve('src/demo.js')], bundle: true, write: false, format: 'esm',
    plugins: [{name:'mock-vapi', setup(builder) {
      builder.onResolve({filter: /^@vapi-ai\/web$/}, () => ({path:'mock-vapi',namespace:'mock'}));
      builder.onLoad({filter:/.*/,namespace:'mock'}, () => ({contents:`
        export default class Vapi {
          constructor() { this.handlers = {}; this.starts = 0; window.mockVapi = this; }
          on(name, handler) { this.handlers[name] = handler; }
          emit(name, value) { this.handlers[name]?.(value); }
          async start() {
            this.starts++;
            if (window.rejectMicrophone) throw new Error('Permission denied');
            if (window.delayStart) await new Promise(resolve => { window.finishStart = resolve; });
            this.emit('call-start'); return {id:'mock-call'};
          }
          stop() { this.emit('call-end'); }
        }
      `}));
    }}],
  });
  javascript = result.outputFiles[0].text;
});

test.beforeEach(async ({page}) => {
  // Intercept the SDK: these UI tests never connect to Vapi or spend credits.
  await page.route('**/assets/demo.js', route => route.fulfill({body:javascript,contentType:'text/javascript'}));
  await page.route('**/demo/config', route => route.fulfill({json:{data:{enabled:true,public_key:'test',assistant_id:'test'}}}));
});

test('explicit start, safe captions, end call, and repeat', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Ready when you are');
  expect(await page.evaluate(() => window.mockVapi.starts)).toBe(0);
  await page.getByRole('button',{name:'Start demo call'}).click();
  await expect(page.getByRole('status')).toHaveText('Connected with Alex');
  await page.evaluate(() => window.mockVapi.emit('message',{
    type:'transcript',transcriptType:'final',role:'assistant',transcript:'<img src=x onerror=alert(1)>'
  }));
  await page.locator('.transcript summary').click();
  await expect(page.locator('#transcript')).toContainText('<img src=x onerror=alert(1)>');
  await expect(page.locator('#transcript img')).toHaveCount(0);
  await page.getByRole('button',{name:'End call'}).click();
  await expect(page.getByRole('status')).toHaveText('Call ended');
  await expect(page.getByRole('button',{name:'Start demo call'})).toBeEnabled();
  await page.getByRole('button',{name:'Start demo call'}).click();
  expect(await page.evaluate(() => window.mockVapi.starts)).toBe(2);
});

test('microphone denial permits retry',async ({page}) => {
  await page.goto('/');
  await page.evaluate(() => { window.rejectMicrophone = true; });
  await page.getByRole('button',{name:'Start demo call'}).click();
  await expect(page.getByRole('status')).toHaveText('Microphone access is needed');
  await expect(page.getByRole('button',{name:'Start demo call'})).toBeEnabled();
});

test('disabled configuration cannot start a call',async ({page}) => {
  await page.route('**/demo/config', route => route.fulfill({json:{data:{enabled:false}}}));
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Browser calling is being set up');
  await expect(page.getByRole('button',{name:'Start demo call'})).toBeDisabled();
});

test('cancelling a pending connection prevents overlapping calls',async ({page}) => {
  await page.goto('/');
  await page.evaluate(() => { window.delayStart = true; });
  await page.getByRole('button',{name:'Start demo call'}).click();
  await page.getByRole('button',{name:'End call'}).click();
  await expect(page.getByRole('button',{name:'Start demo call'})).toBeDisabled();
  await page.evaluate(() => window.finishStart());
  await expect(page.getByRole('status')).toHaveText('Call ended');
  await expect(page.getByRole('button',{name:'Start demo call'})).toBeEnabled();
  expect(await page.evaluate(() => window.mockVapi.starts)).toBe(1);
});

test('mobile page fits viewport',async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Ready when you are');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:'../data/demo-mobile.png',fullPage:true});
});
