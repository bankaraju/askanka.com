"""Phase C multi-day holding-period descriptive (read-only).

Backlog #119. User intent (2026-04-23): Phase 1 = T+1 overnight risk
only. Phase 2 (T+2..T+5 with MFE/MAE) was deferred until forward
shadow confirms T+1 edge is real.

This module ships Phase 1 + a Phase 2 preview: per-event SHORT P&L at
T+1 through T+5 close-to-close from each Phase C SHORT event in the
v2 mechanical-replay roster. Reports per-horizon hit rate + avg P&L,
per |z| bucket, plus per-event MFE/MAE within the [+1, +5] window.

Read-only. No production change. Verdict input for the Phase C
overnight overlay decision (#113) and the deferred multi-day
extension (#119 Phase 2).
"""
