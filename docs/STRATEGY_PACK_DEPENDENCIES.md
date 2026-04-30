# Strategy Pack — Dependency Archaeology Report

**Seeds analyzed:** 8
**First-party files reached (transitively):** 37
**Third-party top-level packages required:** 10

## Third-party packages (lean requirements_pack.txt set)

- anthropic
- bs4
- dotenv
- google
- kiteconnect
- numpy
- pandas
- pyotp
- requests
- yfinance

## First-party modules pulled in (the actual code surface)

- config
- pipeline
- pipeline.asian_correlation
- pipeline.atr_stops
- pipeline.autoresearch.etf_v3_loader
- pipeline.autoresearch.etf_v3_research
- pipeline.break_signal_generator
- pipeline.eodhd_client
- pipeline.gemma4_pilot.audit_logger
- pipeline.gemma4_pilot.rubrics
- pipeline.gemma4_pilot.shadow_dispatcher
- pipeline.gemma4_pilot.wiring
- pipeline.kite_auth
- pipeline.kite_client
- pipeline.llm_providers.anthropic_provider
- pipeline.llm_providers.base
- pipeline.llm_providers.gemini_provider
- pipeline.llm_providers.openai_compat
- pipeline.llm_router
- pipeline.political_signals
- pipeline.premarket_scanner
- pipeline.research.intraday_v1.kill_switch
- pipeline.research.vwap_filter
- pipeline.risk_guardrails
- pipeline.shadow_pnl
- pipeline.signal_badges
- pipeline.signal_enrichment
- pipeline.signal_tracker
- pipeline.spread_bootstrap
- pipeline.spread_leaderboard
- pipeline.spread_statistics
- pipeline.synthetic_options
- pipeline.telegram_bot
- pipeline.trade_postmortem
- pipeline.trading_calendar

## Files visited (transitive)

- pipeline\asian_correlation.py
- pipeline\atr_stops.py
- pipeline\autoresearch\etf_v3_curated_signal.py
- pipeline\autoresearch\etf_v3_loader.py
- pipeline\autoresearch\etf_v3_research.py
- pipeline\break_signal_generator.py
- pipeline\eodhd_client.py
- pipeline\gemma4_pilot\audit_logger.py
- pipeline\gemma4_pilot\rubrics\__init__.py
- pipeline\gemma4_pilot\shadow_dispatcher.py
- pipeline\gemma4_pilot\wiring.py
- pipeline\h_2026_04_26_001_paper.py
- pipeline\kite_auth.py
- pipeline\kite_client.py
- pipeline\llm_providers\anthropic_provider.py
- pipeline\llm_providers\base.py
- pipeline\llm_providers\gemini_provider.py
- pipeline\llm_providers\openai_compat.py
- pipeline\llm_router.py
- pipeline\political_signals.py
- pipeline\premarket_scanner.py
- pipeline\research\intraday_v1\kill_switch.py
- pipeline\research\neutral_cohort_tracker.py
- pipeline\research\vwap_filter.py
- pipeline\risk_guardrails.py
- pipeline\run_signals.py
- pipeline\shadow_pnl.py
- pipeline\signal_badges.py
- pipeline\signal_enrichment.py
- pipeline\signal_tracker.py
- pipeline\spread_bootstrap.py
- pipeline\spread_leaderboard.py
- pipeline\spread_statistics.py
- pipeline\synthetic_options.py
- pipeline\telegram_bot.py
- pipeline\trade_postmortem.py
- pipeline\trading_calendar.py
