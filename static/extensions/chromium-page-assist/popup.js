const statusEl = document.getElementById('status');
const sendBtn = document.getElementById('send');
const askBtn = document.getElementById('ask');
const actBtn = document.getElementById('act');
const questionEl = document.getElementById('question');
const systemPromptEl = document.getElementById('system-prompt');
const answerEl = document.getElementById('answer');
const agentModeEl = document.getElementById('agent-mode');

const TARGETS = ['http://127.0.0.1:8899', 'http://localhost:8899'];
const SYSTEM_PROMPT_KEY = 'mlx_page_assist_system_prompt';
const DEFAULT_SYSTEM_PROMPT = [
  'You are MLX Studio Page Assist.',
  'Answer strictly from the provided page context when possible.',
  'If context is weak or incomplete, say what is missing before guessing.',
  'Use concise markdown with short sections and bullets when useful.',
  'Never output long repeated characters, binary-like text, or formatting noise.',
].join(' ');
const ACT_PRESET_SYSTEM_PROMPT = [
  'Act mode preset:',
  'When asked to perform an action, use browser tools to take the action on the live page.',
  'Prefer small safe steps with clear confirmations after each step.',
  'Never claim an action succeeded unless tool results confirm it.',
  'If a required input is missing, ask a single focused follow-up question.',
].join(' ');

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function collectPagePayload(tabId) {
  // Use scripting.executeScript instead of sendMessage so we don't depend on
  // the content script being pre-injected (avoids "Receiving end does not exist").
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({
        title: document.title || 'Untitled Page',
        url: location.href,
        selection: String(window.getSelection() || '').trim().slice(0, 6000),
        text: (document.body?.innerText || '').trim().slice(0, 10000),
        source: 'chromium-extension',
      }),
    });
    return result?.result || {};
  } catch (err) {
    // chrome:// pages, PDFs, or other restricted URLs won't allow scripting
    const tab = await chrome.tabs.get(tabId);
    return { title: tab.title || 'Restricted Page', url: tab.url || '', text: '', selection: '', source: 'chromium-extension' };
  }
}

async function requestStudio(method, path, body) {
  let lastError = null;
  for (const base of TARGETS) {
    try {
      const options = { method, headers: {} };
      if (body !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(body);
      }
      const response = await fetch(`${base}${path}`, options);
      if (!response.ok) {
        const details = await response.text();
        throw new Error(`HTTP ${response.status}${details ? `: ${details}` : ''}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('MLX Studio is not reachable');
}

async function postToStudio(path, body) {
  return requestStudio('POST', path, body);
}

async function getFromStudio(path) {
  return requestStudio('GET', path);
}

function buildSystemPrompt({ customPrompt, agentMode, browserReady, forceAct }) {
  const parts = [DEFAULT_SYSTEM_PROMPT];
  if (agentMode) {
    parts.push(ACT_PRESET_SYSTEM_PROMPT);
  }
  if (customPrompt) {
    parts.push(`Additional instructions: ${customPrompt}`);
  }
  if (agentMode) {
    parts.push(
      browserReady
        ? 'Browser tool sidecar is reachable and synced to the current page URL. If the user asks to take action on the webpage, use browser tools to perform the actions, then report exactly what changed and what still needs user input.'
        : 'Browser tool sidecar is not reachable. Do not attempt browser tools; answer from captured context only.'
    );
  }
  if (forceAct) {
    parts.push('The user explicitly requested action mode. Execute web actions first when feasible, then summarize outcomes.');
  }
  return parts.join('\n\n');
}

function buildGroundedPrompt(question, payload) {
  const userQuestion = (question || '').trim();
  const selection = (payload.selection || '').trim();
  const text = (payload.text || '').trim();
  const title = payload.title || 'Untitled Page';
  const url = payload.url || '';

  const contextParts = ['[Current Page]', `Title: ${title}`];
  if (url) {
    contextParts.push(`URL: ${url}`);
  }
  if (selection) {
    contextParts.push('', `[Selected Text]\n${selection}`);
  }
  if (text) {
    contextParts.push('', `[Page Excerpt]\n${text}`);
  }

  return [
    userQuestion || 'Give me a concise summary of this page and the key takeaways.',
    '',
    'Use the following page context for your answer:',
    '',
    ...contextParts,
  ].join('\n');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function replayAgentActionsOnTab(tabId, toolRuns) {
  const replay = [];
  for (const step of toolRuns) {
    if (!step || step.error) {
      continue;
    }
    const tool = step.tool;
    try {
      if (tool === 'browser_navigate' && step.url) {
        await chrome.tabs.update(tabId, { url: step.url });
        replay.push({ tool, ok: true, detail: step.url });
        continue;
      }

      if (tool === 'browser_click' && step.selector) {
        await chrome.scripting.executeScript({
          target: { tabId },
          args: [step.selector],
          func: (selector) => {
            const el = document.querySelector(selector);
            if (!el) {
              throw new Error(`No element matched selector: ${selector}`);
            }
            el.click();
          },
        });
        replay.push({ tool, ok: true, detail: step.selector });
        continue;
      }

      if (tool === 'browser_type' && step.selector) {
        const text = typeof step.text === 'string' ? step.text : '';
        const submit = Boolean(step.submit);
        await chrome.scripting.executeScript({
          target: { tabId },
          args: [step.selector, text, submit],
          func: (selector, value, doSubmit) => {
            const el = document.querySelector(selector);
            if (!el) {
              throw new Error(`No element matched selector: ${selector}`);
            }
            if ('focus' in el) {
              el.focus();
            }
            if ('value' in el) {
              el.value = value;
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
              throw new Error('Matched element is not an input/textarea');
            }
            if (doSubmit) {
              const form = el.closest('form');
              if (form) {
                form.requestSubmit();
              } else {
                el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
              }
            }
          },
        });
        replay.push({ tool, ok: true, detail: step.selector });
        continue;
      }

      if (tool === 'browser_wait') {
        const seconds = Number(step.seconds || 1);
        const ms = Math.max(0, Math.min(seconds, 5)) * 1000;
        await sleep(ms);
        replay.push({ tool, ok: true, detail: `${seconds}s` });
      }
    } catch (err) {
      replay.push({ tool, ok: false, detail: err?.message || 'failed' });
    }
  }
  return replay;
}

function setBusy(isBusy) {
  sendBtn.disabled = isBusy;
  askBtn.disabled = isBusy;
  if (actBtn) {
    actBtn.disabled = isBusy;
  }
}

function applyActPresetPromptIfNeeded() {
  if (!agentModeEl?.checked || !systemPromptEl) {
    return;
  }
  if (systemPromptEl.value.trim()) {
    return;
  }
  systemPromptEl.value = ACT_PRESET_SYSTEM_PROMPT;
  localStorage.setItem(SYSTEM_PROMPT_KEY, systemPromptEl.value);
}

if (systemPromptEl) {
  systemPromptEl.value = localStorage.getItem(SYSTEM_PROMPT_KEY) || '';
  systemPromptEl.addEventListener('input', () => {
    localStorage.setItem(SYSTEM_PROMPT_KEY, systemPromptEl.value || '');
  });
}

if (agentModeEl) {
  agentModeEl.addEventListener('change', () => {
    applyActPresetPromptIfNeeded();
  });
}

sendBtn.addEventListener('click', async () => {
  setBusy(true);
  answerEl.style.display = 'none';
  answerEl.textContent = '';
  statusEl.textContent = 'Collecting page context…';
  try {
    const tab = await getActiveTab();
    if (!tab?.id) {
      throw new Error('No active tab');
    }
    const payload = await collectPagePayload(tab.id);
    const response = await chrome.runtime.sendMessage({
      type: 'mlx-send-page-assist',
      payload,
    });
    if (!response?.ok) {
      throw new Error(response?.error || 'MLX Studio did not accept the clip');
    }
    statusEl.textContent = 'Sent to MLX Studio.';
  } catch (error) {
    statusEl.textContent = `Failed: ${error.message}`;
  } finally {
    setBusy(false);
  }
});

async function runAsk({ forceAct = false } = {}) {
  setBusy(true);
  answerEl.style.display = 'none';
  answerEl.textContent = '';
  statusEl.textContent = 'Checking model and tools…';

  try {
    if (forceAct && agentModeEl) {
      agentModeEl.checked = true;
    }
    applyActPresetPromptIfNeeded();

    const health = await getFromStudio('/api/health');
    if (!health?.loaded_model) {
      throw new Error('No model loaded in MLX Studio. Load a model in the app first.');
    }

    let useAgentMode = forceAct || Boolean(agentModeEl?.checked);
    let browserReady = false;
    if (useAgentMode) {
      try {
        const browserHealth = await getFromStudio('/api/browser/health');
        browserReady = Boolean(browserHealth?.ok);
        if (!browserReady) {
          useAgentMode = false;
        }
      } catch (_error) {
        useAgentMode = false;
      }
    }

    statusEl.textContent = 'Collecting tab context…';
    const tab = await getActiveTab();
    if (!tab?.id) {
      throw new Error('No active tab');
    }

    const payload = await collectPagePayload(tab.id);
    if (!payload || (!payload.text && !payload.selection)) {
      throw new Error('No readable text found on this page.');
    }

    if (useAgentMode && browserReady && payload.url) {
      statusEl.textContent = 'Syncing agent browser to current page…';
      try {
        await postToStudio('/api/browser/navigate', { url: payload.url });
      } catch (_error) {
        // If sync fails, fall back to non-agent response instead of hard failing.
        useAgentMode = false;
        browserReady = false;
      }
    }

    statusEl.textContent = 'Saving page clip…';
    await postToStudio('/api/page-assist/capture', payload);

    statusEl.textContent = 'Generating answer…';
    const prompt = buildGroundedPrompt(questionEl.value, payload);
    const customSystemPrompt = (systemPromptEl?.value || '').trim();
    const systemPrompt = buildSystemPrompt({
      customPrompt: customSystemPrompt,
      agentMode: useAgentMode,
      browserReady,
      forceAct,
    });
    const actionInstruction = forceAct
      ? 'Act now: use browser tools to execute the requested webpage actions. Then report what was completed, what changed on the page, and any next required user input.'
      : 'If my request asks for interaction on the page (click, type, submit, open, navigate), execute those actions using browser tools and then summarize results.';
    const maxTokens = forceAct ? 2048 : useAgentMode ? 1536 : 1024;
    const result = await postToStudio('/api/generate', {
      prompt,
      messages: [
        { role: 'system', content: systemPrompt },
        {
          role: 'user',
          content: `${prompt}\n\n${actionInstruction}`,
        },
      ],
      max_tokens: maxTokens,
      temperature: 0.35,
      top_p: 0.9,
      repetition_penalty: 1.05,
      agent_mode: useAgentMode,
    });

    if (!result?.response) {
      throw new Error(result?.error || 'No response from MLX Studio');
    }

    const toolRuns = Array.isArray(result.agent_tools) ? result.agent_tools : [];
    let replayRuns = [];
    if (tab?.id && toolRuns.length && useAgentMode) {
      replayRuns = await replayAgentActionsOnTab(tab.id, toolRuns);
    }
    let display = '';
    if (toolRuns.length) {
      const steps = toolRuns.map((t, i) => {
        const label = t.tool || 'tool';
        const detail = t.url || t.query || t.id || (t.error ? `error: ${t.error}` : '');
        return `Step ${i + 1}: ${label}${detail ? ` — ${detail}` : ''}${t.error ? ' ✗' : ' ✓'}`;
      }).join('\n');
      display = `[Agent actions]\n${steps}\n\n`;
    }
    if (replayRuns.length) {
      const replaySummary = replayRuns.map((r, i) => {
        return `Replay ${i + 1}: ${r.tool} — ${r.detail}${r.ok ? ' ✓' : ' ✗'}`;
      }).join('\n');
      display += `[Applied on current tab]\n${replaySummary}\n\n`;
    }
    display += result.response.trim();
    answerEl.textContent = display;
    answerEl.style.display = 'block';
    statusEl.textContent = toolRuns.length
      ? `Done — ${toolRuns.length} action${toolRuns.length === 1 ? '' : 's'} taken.`
      : 'Answer ready.';
  } catch (error) {
    statusEl.textContent = `Failed: ${error.message}`;
  } finally {
    setBusy(false);
  }
}

askBtn.addEventListener('click', () => {
  runAsk({ forceAct: false });
});

if (actBtn) {
  actBtn.addEventListener('click', () => {
    runAsk({ forceAct: true });
  });
}
