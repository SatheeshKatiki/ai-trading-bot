<!-- BEGIN:nextjs-agent-rules -->
# Next.js version note

This project runs Next.js 16 / React 19 — newer than many training cutoffs.
In practice this codebase sticks to conventional App Router patterns
(`app/**/page.tsx`, `app/**/layout.tsx`, `app/api/**/route.ts` handlers) —
nothing exotic. If something you're about to write doesn't match what you
see in the surrounding files, or you hit a deprecation warning, check
`node_modules/next/dist/docs/` before assuming it's a training-data gap.
<!-- END:nextjs-agent-rules -->
