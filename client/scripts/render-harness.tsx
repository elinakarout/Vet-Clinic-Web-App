// Do the chat components render what the server actually sent? (Phase 8)
//
// Two things here cannot be caught by `tsc -b` or oxlint, and both are the kind
// of bug that looks fine on the machine it was written on:
//
//   1. The formatter meets real model prose. The text below is a VERBATIM live
//      Gemini reply, `*   ` bullets and all — not an idealised sample, because a
//      sample written from the docs encodes the same assumption the code does.
//   2. The confirm card renders CLINIC time. `starts_at` below is a real
//      proposal from chat/tools.py: 06:00Z, which is 09:00 in Beirut. This file
//      is run under TZ=America/Los_Angeles precisely so that a browser-local bug
//      shows up as 23:00 on the previous day instead of quietly agreeing.
//
// Run it with scripts/verify-chat.sh.

import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MessageBubble } from '../src/components/chat/MessageBubble';
import { CancellationSuggestion, SlotSuggestion } from '../src/components/chat/SlotSuggestion';
import { ToastProvider } from '../src/components/ui/ToastContext';
import type { ChatTurn } from '../src/hooks/useChat';

// Verbatim from a live Gemini reply, captured during the Phase 8 verification.
const real =
  'We are open **Monday to Friday** and closed on Saturdays and Sundays. \n\n' +
  'Our patient consulting hours are from **09:00 to 18:00**, depending on the veterinarian:\n\n' +
  '*   **Dr. Anita Patel:** Monday–Friday, 09:00–17:00\n' +
  '*   **Dr. Marek Novak:** Monday–Friday, 10:00–18:00\n\n' +
  'If you need to book an appointment, let me know how I can help!';

const turn: ChatTurn = {
  key: 'a', role: 'ASSISTANT', text: real, toolLabels: ["Checking the clinic's information..."],
  activeTool: null, proposals: [], error: null, interrupted: false, pending: false, createdAt: null,
};

const html = renderToStaticMarkup(<MessageBubble turn={turn} />);
const bubbleChecks: [string, boolean][] = [
  ['two vets became a real <ul> with two <li>', (html.match(/<li>/g) ?? []).length === 2 && html.includes('<ul')],
  ['inline bold became <strong>', html.includes('<strong class="font-semibold">Monday to Friday</strong>')],
  ['bold inside a list item too', html.includes('<strong class="font-semibold">Dr. Anita Patel:</strong>')],
  ['no literal ** left on screen', !html.replace(/<[^>]+>/g, '').includes('**')],
  ['no literal bullet asterisk left', !html.replace(/<[^>]+>/g, '').includes('*   ')],
  ['lead paragraph and closing line kept', html.includes('We are open') && html.includes('let me know how I can help!')],
  ['tool trace rendered without its ellipsis', html.includes("Checking the clinic&#x27;s information") && !html.includes('information...')],
  ['nothing was injected as raw html', !html.includes('<script')],
];
// Produced by api/app/chat/tools.py:propose_appointment against the seeded
// database — copied out of the tool's own output, not written by hand.
const proposal = {"pet_id": 1, "pet_name": "Biscuit", "vet_id": 1, "vet_name": "Dr. Anita Patel", "starts_at": "2026-08-26T06:00:00Z", "ends_at": "2026-08-26T06:30:00Z", "reason": "Annual check-up"};
const cancellation = {"appointment_id": 7, "pet_id": 1, "pet_name": "Biscuit", "vet_name": "Dr. Anita Patel", "starts_at": "2026-08-26T06:00:00Z", "ends_at": "2026-08-26T06:30:00Z", "reason": null};

const cardHtml = renderToStaticMarkup(
  <MemoryRouter>
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <SlotSuggestion proposal={proposal} onAsk={() => {}} />
        <CancellationSuggestion proposal={cancellation} />
      </ToastProvider>
    </QueryClientProvider>
  </MemoryRouter>,
);
const cardText = cardHtml.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
console.log('\nbrowser TZ :', Intl.DateTimeFormat().resolvedOptions().timeZone);
console.log('card text  :', cardText.trim().slice(0, 260));

const cardChecks: [string, boolean][] = [
  ['renders 09:00 clinic time, not the browser\'s', cardText.includes('09:00')],
  ['does not render the browser-local hour', !cardText.includes('23:00') && !cardText.includes('11:00 pm')],
  ['names the clinic zone so a remote user knows', cardText.includes('GMT+3')],
  ['names the clinic-local weekday', cardText.includes('Wed 26 Aug')],
  ['carries the pet and vet from the proposal', cardText.includes('Biscuit') && cardText.includes('Dr. Anita Patel')],
  ['offers Confirm booking and Not now', cardText.includes('Confirm booking') && cardText.includes('Not now')],
  ['cancellation card is danger-toned and asks first', cardText.includes('Yes, cancel it') && cardText.includes('Keep it')],
  ['a null reason renders nothing rather than "null"', !cardText.includes('null')],
];
let bad = 0;
for (const [name, ok] of [...bubbleChecks, ...cardChecks]) {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}`);
  if (!ok) bad++;
}
console.log(bad === 0 ? '\nALL PASS' : `\n${bad} FAILURE(S)`);
process.exit(bad ? 1 : 0);
