const MENU_ID = 'mlx-moxy-wirks-send-selection';
const TARGETS = ['http://127.0.0.1:8899/api/page-assist/capture', 'http://localhost:8899/api/page-assist/capture'];

async function postClip(payload) {
  let lastError = null;
  for (const url of TARGETS) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return true;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('MLX-Moxy-Wirks is not reachable');
}

async function captureFromTab(tabId, fallbackSelection = '') {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      title: document.title || 'Untitled Page',
      url: location.href,
      selection: String(window.getSelection() || '').trim().slice(0, 6000),
      text: (document.body?.innerText || '').trim().slice(0, 10000),
      source: 'chromium-extension'
    }),
  });
  const payload = result?.result || {};
  if (fallbackSelection && !payload.selection) {
    payload.selection = fallbackSelection.slice(0, 6000);
  }
  return payload;
}

chrome.runtime.onInstalled.addListener(() => {
  if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch((error) => {
      console.warn('Unable to enable side panel action behavior', error);
    });
  }
  chrome.contextMenus.create({
    id: MENU_ID,
    title: 'Send selection to MLX-Moxy-Wirks',
    contexts: ['selection', 'page'],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID || !tab?.id) return;
  try {
    const payload = await captureFromTab(tab.id, info.selectionText || '');
    await postClip(payload);
  } catch (error) {
    console.error('Failed to send clip to MLX-Moxy-Wirks', error);
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== 'mlx-send-page-assist') return false;
  postClip(message.payload)
    .then(() => sendResponse({ ok: true }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
