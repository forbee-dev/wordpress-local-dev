---
title: "Slots API embed page: escaping iframe_code must match old browser parsing"
author: forbee-dev
date: 2026-10-26
touches:
  - slots-library/slots-library-api/src/modules/iframes/public/iframes-public.service.ts
  - slots-library/slots-library-admin/src/common/contexts/auth-context/index.tsx
---

## Decided
- Embed `src`: cut the raw stored value at the first literal `"`, decode HTML character refs (incl. bare trailing `&amp`), validate http(s) or `//`, then attribute-escape. Keep only `allow`/`allowfullscreen` from the pasted tail.
- Admin tokens stay in the Auth0 SDK; axios requests await an "auth ready" promise resolved when `isLoading` is false.

## Tried and ruled out
- Plain escaping of `iframe_code`: broke 3,097 of 22,158 embed pages (stored `&amp;` became `&amp;amp;`).
- Cutting at the quote after decoding: changes URLs that contain `&quot;`.
- Returning `{}` from the token provider while Auth0 loads: first calls after reload go out without a token (401 on immediate submit).

## Watch out
- Unit tests and DB snapshots did not catch either regression; only the browser-resolved `iframe.src` over all rows (S16 parity) did. Re-run that harness (scratchpad e2e/harness) for any embed change.
- 27 slots store pasted HTML attributes after the URL; 4 rows end with bare `&amp`.
- scraper origin/staging is far behind main; base scraper work on origin/main.
