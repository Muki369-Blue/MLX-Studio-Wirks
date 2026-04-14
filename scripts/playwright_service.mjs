import http from 'node:http';
import process from 'node:process';
import { chromium } from 'playwright';

const HOST = process.env.PLAYWRIGHT_SERVICE_HOST || '127.0.0.1';
const PORT = Number(process.env.PLAYWRIGHT_SERVICE_PORT || 8941);
const HEADLESS = process.env.PLAYWRIGHT_HEADLESS !== '0';
const DEFAULT_MAX_TEXT = Number(process.env.PLAYWRIGHT_SNAPSHOT_TEXT || 7000);
const DEFAULT_MAX_ELEMENTS = Number(process.env.PLAYWRIGHT_SNAPSHOT_ELEMENTS || 24);
const VIEWPORT = { width: 1440, height: 960 };
const SELECT_ALL_SHORTCUT = process.platform === 'darwin' ? 'Meta+A' : 'Control+A';

let browser = null;
let context = null;
let page = null;
let lastSnapshot = null;

function json(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(payload));
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString('utf-8').trim();
  return raw ? JSON.parse(raw) : {};
}

async function ensurePage() {
  if (page && !page.isClosed()) {
    return page;
  }

  if (!browser) {
    browser = await chromium.launch({ headless: HEADLESS });
  }

  if (!context) {
    context = await browser.newContext({
      viewport: VIEWPORT,
      ignoreHTTPSErrors: true,
    });
    context.on('page', (nextPage) => {
      page = nextPage;
    });
  }

  if (!page || page.isClosed()) {
    page = await context.newPage();
  }

  return page;
}

function resolveSelector(body) {
  if (body.selector) {
    return String(body.selector);
  }
  if (body.elementId != null) {
    const targetId = Number(body.elementId);
    const match = lastSnapshot?.elements?.find((element) => element.id === targetId);
    if (!match?.selector) {
      throw new Error(`Unknown snapshot element: ${body.elementId}`);
    }
    return match.selector;
  }
  throw new Error('Missing selector or elementId.');
}

async function handleNavigate(body) {
  const activePage = await ensurePage();
  const url = String(body.url || '').trim();
  if (!url) {
    throw new Error('Missing url.');
  }

  const response = await activePage.goto(url, {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });
  await activePage.waitForTimeout(250);

  return {
    ok: true,
    url: activePage.url(),
    title: await activePage.title().catch(() => ''),
    status: response?.status() ?? null,
    message: 'Navigation completed.',
  };
}

async function handleSnapshot(body) {
  const activePage = await ensurePage();
  const maxText = Math.max(500, Math.min(Number(body.max_text || DEFAULT_MAX_TEXT), 20000));
  const maxElements = Math.max(5, Math.min(Number(body.max_elements || DEFAULT_MAX_ELEMENTS), 64));

  await activePage.waitForTimeout(200);

  const snapshot = await activePage.evaluate(({ maxTextLength, maxElementsLength }) => {
    function normalizeText(value) {
      return String(value || '').replace(/\s+/g, ' ').trim();
    }

    function cssEscape(value) {
      return String(value).replace(/["\\]/g, '\\$&');
    }

    function cssPath(node) {
      if (!(node instanceof Element)) {
        return '';
      }
      if (node.id) {
        return `#${cssEscape(node.id)}`;
      }
      const testId = node.getAttribute('data-testid');
      if (testId) {
        return `[data-testid="${cssEscape(testId)}"]`;
      }
      const segments = [];
      let current = node;
      while (current && current.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
        let segment = current.tagName.toLowerCase();
        const parent = current.parentElement;
        if (parent) {
          const siblings = Array.from(parent.children).filter(
            (child) => child.tagName === current.tagName,
          );
          if (siblings.length > 1) {
            segment += `:nth-of-type(${siblings.indexOf(current) + 1})`;
          }
        }
        segments.unshift(segment);
        current = parent;
      }
      return segments.join(' > ');
    }

    function isVisible(element) {
      if (!(element instanceof HTMLElement)) {
        return false;
      }
      const style = window.getComputedStyle(element);
      if (style.visibility === 'hidden' || style.display === 'none') {
        return false;
      }
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }

    const bodyText = normalizeText(document.body?.innerText || '').slice(0, maxTextLength);
    const selectors = [
      'a',
      'button',
      'input',
      'textarea',
      'select',
      'summary',
      '[role="button"]',
      '[role="link"]',
      '[contenteditable="true"]',
    ];
    const seenSelectors = new Set();
    const elements = [];
    for (const node of document.querySelectorAll(selectors.join(','))) {
      if (!(node instanceof HTMLElement) || !isVisible(node)) {
        continue;
      }
      const selector = cssPath(node);
      if (!selector || seenSelectors.has(selector)) {
        continue;
      }
      seenSelectors.add(selector);
      elements.push({
        id: elements.length + 1,
        selector,
        tag: node.tagName.toLowerCase(),
        role: normalizeText(node.getAttribute('role')),
        text: normalizeText(node.innerText || node.textContent || node.value).slice(0, 160),
        label: normalizeText(node.getAttribute('aria-label')),
        placeholder: normalizeText(node.getAttribute('placeholder')),
        href: normalizeText(node.getAttribute('href')),
        disabled: Boolean(node.disabled),
      });
      if (elements.length >= maxElementsLength) {
        break;
      }
    }

    return {
      textExcerpt: bodyText,
      elements,
    };
  }, { maxTextLength: maxText, maxElementsLength: maxElements });

  lastSnapshot = {
    capturedAt: new Date().toISOString(),
    url: activePage.url(),
    title: await activePage.title().catch(() => ''),
    elements: snapshot.elements,
  };

  return {
    ...lastSnapshot,
    textExcerpt: snapshot.textExcerpt,
  };
}

async function handleClick(body) {
  const activePage = await ensurePage();
  const selector = resolveSelector(body);
  const target = activePage.locator(selector).first();
  await target.click({ timeout: 10000 });
  await activePage.waitForTimeout(250);
  return {
    ok: true,
    selector,
    url: activePage.url(),
    title: await activePage.title().catch(() => ''),
    message: 'Click completed.',
  };
}

async function handleType(body) {
  const activePage = await ensurePage();
  const selector = resolveSelector(body);
  const value = String(body.text || '');
  if (!value) {
    throw new Error('Missing text.');
  }

  const target = activePage.locator(selector).first();
  const isContentEditable = await target.evaluate((node) => node.isContentEditable).catch(() => false);

  await target.click({ timeout: 10000 });

  if (isContentEditable) {
    await activePage.keyboard.press(SELECT_ALL_SHORTCUT).catch(() => {});
    await activePage.keyboard.type(value, { delay: 12 });
  } else {
    await target.fill(value, { timeout: 10000 });
  }

  if (body.submit) {
    await target.press('Enter').catch(async () => {
      await activePage.keyboard.press('Enter');
    });
  }

  await activePage.waitForTimeout(250);
  return {
    ok: true,
    selector,
    url: activePage.url(),
    title: await activePage.title().catch(() => ''),
    message: body.submit ? 'Typing completed and submit requested.' : 'Typing completed.',
  };
}

async function handleWait(body) {
  const activePage = await ensurePage();
  const seconds = Math.max(0, Math.min(Number(body.seconds || 1), 30));
  const timeout = Math.round(seconds * 1000);
  const text = String(body.text || '').trim();

  if (text) {
    await activePage.getByText(text, { exact: false }).first().waitFor({
      state: 'visible',
      timeout,
    });
  } else {
    await activePage.waitForTimeout(timeout);
  }

  return {
    ok: true,
    url: activePage.url(),
    title: await activePage.title().catch(() => ''),
    message: text
      ? `Waited for text: ${text}`
      : `Waited for ${seconds} second${seconds === 1 ? '' : 's'}.`,
  };
}

async function handleReset() {
  lastSnapshot = null;
  if (page && !page.isClosed()) {
    await page.close().catch(() => {});
  }
  page = null;
  if (context) {
    await context.close().catch(() => {});
  }
  context = null;
  return { ok: true, message: 'Browser session reset.' };
}

async function handleHealth() {
  return {
    ok: true,
    browserRunning: Boolean(browser),
    pageReady: Boolean(page && !page.isClosed()),
    url: page && !page.isClosed() ? page.url() : '',
    title: page && !page.isClosed() ? await page.title().catch(() => '') : '',
  };
}

async function shutdown() {
  if (context) {
    await context.close().catch(() => {});
  }
  context = null;
  page = null;
  if (browser) {
    await browser.close().catch(() => {});
  }
  browser = null;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${HOST}:${PORT}`);

  try {
    if (req.method === 'GET' && url.pathname === '/health') {
      json(res, 200, await handleHealth());
      return;
    }

    if (req.method !== 'POST') {
      json(res, 405, { error: 'Method not allowed.' });
      return;
    }

    const body = await readJson(req);

    if (url.pathname === '/session/reset') {
      json(res, 200, await handleReset());
      return;
    }
    if (url.pathname === '/page/navigate') {
      json(res, 200, await handleNavigate(body));
      return;
    }
    if (url.pathname === '/page/snapshot') {
      json(res, 200, await handleSnapshot(body));
      return;
    }
    if (url.pathname === '/page/click') {
      json(res, 200, await handleClick(body));
      return;
    }
    if (url.pathname === '/page/type') {
      json(res, 200, await handleType(body));
      return;
    }
    if (url.pathname === '/page/wait') {
      json(res, 200, await handleWait(body));
      return;
    }

    json(res, 404, { error: 'Not found.' });
  } catch (error) {
    json(res, 500, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`[playwright-service] listening on http://${HOST}:${PORT}`);
});

async function stopServer() {
  await shutdown();
  server.close(() => process.exit(0));
}

process.on('SIGINT', () => {
  stopServer();
});

process.on('SIGTERM', () => {
  stopServer();
});
