# Offline Support Plan

## Status: Deferred — Revisit after scheduling + patient modules are live

---

## Problem

The practice needs access to the schedule and patient records — and the ability to make changes — even when the office internet is unreliable or down. Staff also access the app remotely (e.g., dentist or practice manager working from home), so a cloud-hosted web app is still required.

---

## Decision: One App, Not Two

A properly built **PWA (Progressive Web App)** handles both scenarios from a single codebase. No separate native desktop app is needed.

| Scenario | How PWA handles it |
|---|---|
| Dentist working from home | It's a URL — works in any browser, served from cloud |
| Office internet goes down | Service worker serves the app shell from browser cache; IndexedDB serves cached data |
| Changes made while offline | Mutation queue in IndexedDB; synced to server on reconnect |
| Installed feel on front desk computer | "Add to Home Screen" = behaves like a native app |

The only reason to build a separate native desktop app would be hardware integration (e.g., x-ray software like Dexis, TWAIN scanners). That is a separate problem.

---

## Architecture

```
Online:  Browser → apiClient → FastAPI → Postgres (source of truth)
                              ↓ also syncs to IndexedDB (Dexie)

Offline: Browser → offlineAwareGet() → IndexedDB (Dexie)
         Writes  → pendingMutations table → replayed on reconnect
         App UI  → Service Worker cache (serwist)
```

**Auth offline:** The service worker caches rendered HTML responses (NetworkFirst strategy). On an offline page load, it serves the cached page directly — the Next.js server middleware does not run, but the user's JWT is still in their session cookie. On reconnect the middleware validates normally.

---

## Implementation Phases

### Phase 1 — PWA App Shell (Service Worker)

**Goal:** The app loads in the browser with no internet, as long as it was opened once while online.

**New dependencies:**
```
@serwist/next   — Next.js service worker plugin (modern next-pwa replacement)
serwist         — Workbox-based service worker toolkit
```

**Files:**
- `apps/web/app/sw.ts` — service worker entry point
  - Precaches all Next.js static assets (JS, CSS, fonts)
  - `NavigationRoute` with `NetworkFirst` strategy (5s timeout) for HTML pages
  - Falls back to cached HTML on network failure
- `apps/web/next.config.ts` — wrap config with `@serwist/next` plugin
  - `swSrc: "app/sw.ts"`, `swDest: "public/sw.js"`
  - Disabled in `development` to avoid cache confusion
- `apps/web/app/layout.tsx` — add PWA manifest link + service worker registration

---

### Phase 2 — Offline Data Store (Dexie + PHI Encryption)

**Goal:** Persistent, encrypted local storage for patients, appointments, providers, and operatories.

**New dependency:** `dexie` — IndexedDB wrapper with TypeScript support

#### PHI Encryption Strategy

**File:** `apps/web/lib/offline/crypto.ts`

- On login: generate a random AES-256-GCM key via `crypto.subtle.generateKey()`, store in `sessionStorage`
- `sessionStorage` is cleared when the browser tab/window closes — PHI is inaccessible after browser close (HIPAA-friendly)
- If a new key is detected on startup alongside existing IndexedDB data (old key gone), all PHI tables are cleared and re-synced
- `encrypt(plaintext, key)` / `decrypt(ciphertext, key)` — AES-256-GCM with random IV per record

#### Dexie Schema

**File:** `apps/web/lib/offline/db.ts`

| Table | Fields | Indexes |
|---|---|---|
| `patients` | `id, practiceId, encryptedData, updatedAt` | `[practiceId+updatedAt]` |
| `appointments` | `id, practiceId, encryptedData, date, updatedAt` | `[practiceId+date]` |
| `providers` | `id, practiceId, encryptedData, updatedAt` | `practiceId` |
| `operatories` | `id, practiceId, encryptedData, updatedAt` | `practiceId` |
| `pendingMutations` | `id, idempotencyKey, method, path, encryptedBody, createdAt, retryCount, status` | `[status+createdAt]` |
| `syncMeta` | `entity, lastCursorAt` | — |

---

### Phase 3 — Network Status + Offline UI

**Goal:** Practice sees a clear offline indicator; cloud-only features (eligibility, claims) are disabled.

**Files:**
- `apps/web/lib/offline/network-status.ts` — `useNetworkStatus(): { isOnline: boolean }` hook wrapping `navigator.onLine` + browser events
- `apps/web/components/ui/OfflineBanner.tsx` — fixed banner when offline: *"You're offline — viewing cached data. Changes will sync when reconnected."*
- `apps/web/app/(app)/layout.tsx` — add `<OfflineBanner />` above `<main>`

---

### Phase 4 — Sync Engine (Pull: Cloud → IndexedDB)

**Goal:** On login and on reconnect, sync server data into IndexedDB incrementally.

**File:** `apps/web/lib/offline/sync-engine.ts`

```typescript
// Syncs one entity type using updatedAt cursor for incremental sync
async function syncEntity(entity: SyncableEntity, token: string): Promise<void>

// Orchestrates all entity syncs in parallel
export async function runFullSync(token: string): Promise<void>

// Called on: login, 'online' event, window focus (throttled 5 min)
export function startSyncListeners(): () => void  // returns cleanup fn
```

**Sync behavior:**
- Entities: `patients`, `appointments` (current + 2 weeks ahead), `providers`, `operatories`
- Page size: 100 records per request (matches existing pagination schema)
- Upsert into Dexie via `bulkPut()` — idempotent
- Cursor stored in `syncMeta`: `{ entity: 'patients', lastCursorAt: '...' }` — incremental syncs only fetch new/updated records

**Note:** Patient and appointment API endpoints are not yet implemented (planned for Phase 1.6+). The sync engine is designed now so wiring it to real endpoints is additive — no rework required.

**Modified:** `apps/web/components/providers.tsx` — call `runFullSync(token)` after login and register `startSyncListeners()` in a `useEffect`

---

### Phase 5 — Offline-Aware API Layer

**Goal:** Reads fall back to IndexedDB when offline; writes queue instead of failing.

#### Reads

**File:** `apps/web/lib/offline/offline-query.ts`

```typescript
export async function offlineAwareGet<T>(
  path: string,
  dexieQuery: () => Promise<T>,
): Promise<T>
// Tries apiClient.get(); if offline or network error, executes dexieQuery instead.
```

Used in React Query hooks:
```typescript
useQuery({
  queryKey: ['patients', practiceId],
  queryFn: () => offlineAwareGet(
    '/patients',
    () => db.patients.where('practiceId').equals(practiceId).toArray().then(decrypt)
  )
})
```

#### Mutation Queue

**File:** `apps/web/lib/offline/mutation-queue.ts`

```typescript
// When offline: writes mutation to pendingMutations instead of sending immediately
export async function queueMutation(
  method: HttpMethod,
  path: string,
  body: unknown,
  idempotencyKey: string,
): Promise<void>

// Replays mutations in createdAt order; safe to retry because all mutations have idempotency keys
export async function processMutationQueue(): Promise<ProcessQueueResult>
```

- `processMutationQueue()` called on the `online` event and after `runFullSync` completes
- Max 5 retries; after that, marks mutation as `'failed'` and surfaces a UI toast for manual retry
- Mutation body encrypted before storing in Dexie (may contain PHI)

---

### Phase 6 — React Query Persister

**Goal:** React Query cache survives page reload so offline reads don't always need to query Dexie directly.

**New dependencies:**
```
@tanstack/query-async-storage-persister
@tanstack/query-persist-client-core
```

**Modified:** `apps/web/components/providers.tsx`
- Wrap `QueryClientProvider` with `PersistQueryClientProvider`
- Storage adapter backed by a non-PHI Dexie table
- `gcTime: 7 days` — long enough for a weekend offline period
- Only non-PHI query keys (providers, operatories) persisted here; patient/appointment data served directly from Dexie via `offlineAwareGet`

---

### Phase 7 — Logout / Cache Clearing (HIPAA)

**Goal:** All PHI is unreadable after logout.

**Modified:** `apps/web/components/layout/SignOutButton.tsx` — extend existing sign-out to:

1. Call existing `DELETE /api/auth/session` (clears server-side cookies)
2. Clear all Dexie tables: `patients`, `appointments`, `providers`, `operatories`, `pendingMutations`, `syncMeta`
3. `sessionStorage.clear()` — encryption key gone; any remaining IndexedDB data is unreadable
4. Clear service worker cache: `caches.keys().then(keys => keys.forEach(k => caches.delete(k)))`
5. Navigate to `/login`

---

## Files Changed Summary

| Action | File |
|---|---|
| New | `apps/web/app/sw.ts` |
| New | `apps/web/lib/offline/db.ts` |
| New | `apps/web/lib/offline/crypto.ts` |
| New | `apps/web/lib/offline/sync-engine.ts` |
| New | `apps/web/lib/offline/offline-query.ts` |
| New | `apps/web/lib/offline/mutation-queue.ts` |
| New | `apps/web/lib/offline/network-status.ts` |
| New | `apps/web/components/ui/OfflineBanner.tsx` |
| Modified | `apps/web/next.config.ts` |
| Modified | `apps/web/app/layout.tsx` |
| Modified | `apps/web/app/(app)/layout.tsx` |
| Modified | `apps/web/components/providers.tsx` |
| Modified | `apps/web/components/layout/SignOutButton.tsx` |
| Modified | `apps/web/lib/api-client.ts` (minor — add `isNetworkError` helper) |
| Modified | `apps/web/package.json` |

---

## Why Defer?

This is deferred until the scheduling and patient modules are live because:

1. **Nothing to sync yet.** Patients, appointments, and schedule are currently placeholder pages. A sync engine with no data to sync can't be tested or validated.
2. **The complexity isn't justified yet.** The offline layer is substantial. Getting core features in front of the practice first makes the offline requirement concrete rather than hypothetical.
3. **Retrofitting is clean here.** The data model already has everything needed — `updatedAt` on all entities, soft deletes, and idempotency keys on all mutations. Nothing in the current architecture blocks offline support later; it is purely additive.

**Revisit trigger:** After the patient module (Phase 1.6) and scheduling module are live and the practice is actively using them.

---

## Conflict Resolution

Server is always the source of truth. If the same record is modified online by one device and offline by another, the online mutation wins (last-write-wins at the server). Idempotency keys on all mutations prevent double-application during sync replay.
