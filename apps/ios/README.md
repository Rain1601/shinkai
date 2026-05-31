# Shinkai iOS

SwiftUI client for shinkai — observe + review only in V0 (per
`docs/engineering-framework-v0.md` §10 IP-5).

## Status

**Skeleton only.** This directory holds SwiftUI source files but no Xcode project
yet. To boot it:

```
cd apps/ios
xed Shinkai            # opens the directory in Xcode; create a new SwiftUI App
                       # target named "Shinkai" pointing at Shinkai/*.swift
```

The Swift files here are designed to compile against iOS 17+ with no external
dependencies beyond `Foundation`, `SwiftUI`, and `Combine`.

> Note: any "Cannot find type X in scope" diagnostics outside Xcode are expected.
> The files are single-target sources; SourceKit-LSP needs the Xcode-generated
> project context to resolve `AppSession`, `Run`, etc. across files.

## V0 scope (deferred from the main repo's V1.0 ship)

- `/runs` list — pull from `GET /api/v1/runs`
- run detail — pull events via `GET /api/v1/runs/{id}/events` (SSE)
- checkpoint review — POST `/api/v1/runs/{id}/checkpoint`
- inject note — POST `/api/v1/runs/{id}/inject`

Starting a new run remains web-only in V0.

## Why a skeleton instead of nothing

The user has confirmed that interaction is the central design lever and that iOS
is a first-class client. Stubbing it here makes the engineering-framework
commitment visible in the repo even when the full Xcode project hasn't been built
yet. Replace this file with a real Xcode-generated structure when work starts.
