chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'mlx-collect-page') return false;
  sendResponse({
    title: document.title || 'Untitled Page',
    url: location.href,
    selection: String(window.getSelection() || '').trim().slice(0, 6000),
    text: (document.body?.innerText || '').trim().slice(0, 10000),
    source: 'chromium-extension',
  });
  return false;
});
