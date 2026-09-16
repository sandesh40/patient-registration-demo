import Vapi from '@vapi-ai/web';

const start = document.querySelector('#start');
const stop = document.querySelector('#stop');
const status = document.querySelector('#status');
const hint = document.querySelector('#hint');
const timer = document.querySelector('#timer');
const transcript = document.querySelector('#transcript');
let vapi;
let config;
let active = false;
let starting = false;
let startPending = false;
let cancelled = false;
let clock;
let began;

function display(title, description) {
  status.textContent = title;
  hint.textContent = description;
}

function reset() {
  active = false;
  starting = false;
  clearInterval(clock);
  document.body.classList.remove('active');
  start.disabled = startPending || !config?.enabled;
  start.hidden = false;
  stop.hidden = true;
  stop.disabled = false;
}

function callError(error) {
  const denied = /permission|denied|notallowed/i.test(String(error?.message || error?.error?.message || error?.error || ''));
  reset();
  display(denied ? 'Microphone access is needed' : 'The call could not connect', denied
    ? 'Allow microphone access in your browser settings, then try again.'
    : 'Please try again. If this continues, the demo may be unavailable or out of credits.');
}

async function initialize() {
  try {
    const response = await fetch('/demo/config', {cache: 'no-store'});
    if (!response.ok) throw new Error('Configuration unavailable');
    config = (await response.json()).data;
    if (!config?.enabled) {
      display('Browser calling is being set up', 'Please return after the demo configuration is complete.');
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      display('A microphone-enabled browser is needed', 'Open this page over HTTPS in a supported browser.');
      return;
    }
    vapi = new Vapi(config.public_key);
    vapi.on('call-start', () => {
      if (cancelled) { vapi.stop(); return; }
      starting = false;
      active = true;
      began = Date.now();
      document.body.classList.add('active');
      start.hidden = true;
      stop.hidden = false;
      display('Connected with Alex', 'Speak naturally. You can interrupt or correct a detail.');
      clearInterval(clock);
      clock = setInterval(() => {
        const seconds = Math.floor((Date.now() - began) / 1000);
        timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
      }, 1000);
    });
    vapi.on('call-end', () => {
      reset();
      display('Call ended', 'A record is saved only if you confirmed and Alex reported a successful save.');
    });
    vapi.on('error', callError);
    vapi.on('message', (message) => {
      if (message.type !== 'transcript' || message.transcriptType !== 'final') return;
      transcript.querySelector('.empty')?.remove();
      const item = document.createElement('li');
      const who = document.createElement('strong');
      who.textContent = message.role === 'assistant' ? 'Alex' : 'You';
      item.append(who, document.createTextNode(message.transcript || ''));
      transcript.append(item);
      transcript.scrollTop = transcript.scrollHeight;
    });
    start.disabled = false;
    display('Ready when you are', 'Find a quiet spot and have your fictional details ready.');
  } catch {
    display('The demo is temporarily unavailable', 'Refresh the page in a moment to try again.');
  }
}

start.addEventListener('click', async () => {
  if (active || starting || startPending || !vapi) return;
  starting = true;
  startPending = true;
  cancelled = false;
  start.disabled = true;
  stop.hidden = false;
  timer.textContent = '00:00';
  transcript.replaceChildren();
  display('Connecting…', 'Allow microphone access when your browser asks.');
  try {
    const call = await vapi.start(config.assistant_id);
    if (cancelled) { vapi.stop(); return; }
    if (!call && !active) callError(new Error('No call created'));
  } catch (error) { if (!cancelled) callError(error); }
  finally {
    startPending = false;
    if (cancelled) {
      reset();
      display('Call ended', 'You can start again whenever you are ready.');
    } else if (!active) { start.disabled = false; }
  }
});

stop.addEventListener('click', () => {
  cancelled = true;
  vapi?.stop();
  if (startPending) {
    start.disabled = true;
    stop.hidden = false;
    stop.disabled = true;
    display('Cancelling connection…', 'Dismiss any microphone prompt. Please wait before starting again.');
    return;
  }
  reset();
  display('Call ended', 'You can start again whenever you are ready.');
});
window.addEventListener('pagehide', () => { cancelled = true; vapi?.stop(); });
initialize();
