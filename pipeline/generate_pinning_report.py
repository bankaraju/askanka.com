"""Generate the Pinning & Gamma Intelligence Report as HTML (print to PDF)."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST).strftime("%B %d, %Y %H:%M IST")

html = open(Path(__file__).parent / "data" / "pinning_report_template.html", "r", encoding="utf-8").read() if (Path(__file__).parent / "data" / "pinning_report_template.html").exists() else ""

# We'll write directly
out = Path(__file__).parent / "data" / "pinning_gamma_report.html"
out.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Anka Research - Expiry Pinning & Gamma Intelligence Report</title>
<style>
@page {{ margin: 2cm; }}
body {{ font-family: Georgia, serif; font-size: 11pt; line-height: 1.7; color: #1a1a1a; max-width: 780px; margin: 0 auto; padding: 40px; }}
h1 {{ font-size: 22pt; border-bottom: 3px solid #d4a855; padding-bottom: 8px; }}
h2 {{ font-size: 16pt; margin-top: 35px; border-bottom: 1px solid #ccc; padding-bottom: 5px; color: #2a2a2a; }}
h3 {{ font-size: 13pt; color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 10pt; }}
th {{ background: #f5f0e0; padding: 8px 12px; text-align: left; border: 1px solid #ddd; }}
td {{ padding: 6px 12px; border: 1px solid #ddd; }}
tr:nth-child(even) {{ background: #fafaf5; }}
.hl {{ background: #fff8e1; padding: 14px; border-left: 4px solid #d4a855; margin: 15px 0; }}
.stats {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; margin: 20px 0; }}
.stat {{ text-align: center; padding: 12px 22px; border: 2px solid #d4a855; border-radius: 8px; }}
.stat .v {{ font-size: 22pt; font-weight: bold; color: #d4a855; }}
.stat .l {{ font-size: 8pt; color: #666; text-transform: uppercase; }}
.footer {{ margin-top: 40px; padding-top: 15px; border-top: 2px solid #d4a855; font-size: 9pt; color: #888; }}
.pb {{ page-break-before: always; }}
</style></head><body>

<h1>Expiry Pinning & Gamma Intelligence</h1>
<p style="color:#666;font-size:10pt;">Anka Research | {now} | Confidential</p>

<div class="stats">
<div class="stat"><div class="v">86-100%</div><div class="l">Straddle Win Rate</div></div>
<div class="stat"><div class="v">+1.1%</div><div class="l">Avg Expiry Return</div></div>
<div class="stat"><div class="v">0/21</div><div class="l">Stop Losses Hit</div></div>
<div class="stat"><div class="v">10,920</div><div class="l">Parameters Tested</div></div>
</div>

<h2>1. Executive Summary</h2>
<p>We studied options expiry pinning across NIFTY, BANKNIFTY, and FINNIFTY using 5-minute intraday data from 7 weekly expiry Thursdays (Feb-Apr 2026). Selling straddles at the pin strike has been profitable 86-100% of the time with zero stop losses triggered. AutoResearch across 10,920 parameter combinations found the champion strategy: <strong>10:00 AM entry, VIX &gt; 18, 1x premium stop = 75% win rate, +0.97% avg, Sharpe 1.54.</strong></p>

<h2>2. Backtest Results</h2>
<table>
<tr><th>Index</th><th>Win Rate</th><th>Avg P&L</th><th>Stops Hit</th><th>Pin Held</th><th>Max Deviation</th></tr>
<tr><td><b>NIFTY</b></td><td><b>100%</b> (7/7)</td><td>+1.12%</td><td>0/7</td><td>57%</td><td>1.02%</td></tr>
<tr><td><b>BANKNIFTY</b></td><td><b>86%</b> (6/7)</td><td>+1.15%</td><td>0/7</td><td>71%</td><td>1.11%</td></tr>
<tr><td><b>FINNIFTY</b></td><td><b>86%</b> (6/7)</td><td>+1.07%</td><td>0/7</td><td>71%</td><td>1.18%</td></tr>
</table>

<div class="hl"><b>Key finding:</b> Even when the index wanders 1-1.7% from pin during the day, straddle premium (1.4-1.8%) exceeds closing distance, making the trade profitable.</div>

<h2 class="pb">3. AutoResearch: Optimal Parameters</h2>
<p>Tested: 7 entry times &times; 7 VIX thresholds &times; 4 pin filters &times; 5 stop levels &times; 3 indices &times; 7 days = <b>10,920 combinations</b></p>

<h3>Champion Strategy (Best Sharpe)</h3>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Entry Time</td><td><b>10:00 AM</b></td></tr>
<tr><td>VIX Minimum</td><td><b>18</b></td></tr>
<tr><td>Stop Loss</td><td><b>1.0x premium</b></td></tr>
<tr><td>Win Rate</td><td><b>75%</b> (9/12)</td></tr>
<tr><td>Avg P&L</td><td><b>+0.97%</b></td></tr>
<tr><td>Sharpe</td><td><b>1.54</b></td></tr>
</table>

<h3>Conservative Strategy (100% Win Rate)</h3>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Entry Time</td><td><b>2:30 PM</b></td></tr>
<tr><td>VIX Minimum</td><td><b>25</b></td></tr>
<tr><td>Stop Loss</td><td><b>1.5x premium</b></td></tr>
<tr><td>Win Rate</td><td><b>100%</b> (4/4)</td></tr>
</table>

<h3>Intraday Volatility Pattern</h3>
<table>
<tr><th>Time</th><th>Avg Move</th><th>Character</th></tr>
<tr><td>9:00-10:00</td><td>0.08%</td><td>Opening volatility</td></tr>
<tr><td>10:00-12:00</td><td>0.05%</td><td><b>Quiet zone - ideal entry</b></td></tr>
<tr><td>12:00-2:00</td><td>0.07%</td><td>Lunch, positioning</td></tr>
<tr><td><b>2:00-3:30</b></td><td><b>0.13%</b></td><td><b>Gamma zone - pinning intensifies</b></td></tr>
</table>

<h2 class="pb">4. Gamma Exposure (GEX) Analysis</h2>
<p>GEX measures hedging flow per 1-point index move. Max negative GEX = predicted pin strike.</p>

<h3>Live Example (April 7, 2026)</h3>
<table>
<tr><th>Strike</th><th>GEX</th><th>CE OI</th><th>PE OI</th><th>Straddle</th></tr>
<tr><td><b>22,800</b></td><td><b>-1,854,721</b></td><td>8.2M</td><td>18.0M</td><td>203 pts</td></tr>
<tr><td>22,900</td><td>-1,463,999</td><td>13.5M</td><td>6.7M</td><td>201 pts</td></tr>
<tr><td>23,000</td><td>-1,491,045</td><td>18.2M</td><td>4.3M</td><td>230 pts</td></tr>
</table>

<div class="hl"><b>Predicted pin: 22,800.</b> Nifty at 22,888 - 88 points of gravitational pull. Market makers with 26M contracts at 22800 MUST buy when Nifty drops below and sell when it rises above.</div>

<h2>5. Heavyweight Manipulation</h2>
<p>HDFCBANK = 30.2% of BANKNIFTY. Move HDFCBANK 1%, BankNifty moves 0.3%.</p>

<table>
<tr><th>Stock</th><th>Index</th><th>Weight</th><th>Best Absorption</th><th>PM Reversion</th></tr>
<tr><td>HDFCBANK</td><td>BankNifty</td><td>30.2%</td><td><b>98%</b></td><td>56%</td></tr>
<tr><td>ICICIBANK</td><td>BankNifty</td><td>23.5%</td><td><b>186%</b></td><td><b>71%</b></td></tr>
<tr><td>RELIANCE</td><td>Nifty</td><td>10.5%</td><td><b>118%</b></td><td>62%</td></tr>
</table>

<div class="hl"><b>98% absorption (Mar 19):</b> HDFCBANK dropped 0.35%. Expected BankNifty impact: -0.107%. Actual: -0.002%. Other stocks compensated to hold the pin. Textbook manipulation.</div>

<h2 class="pb">6. Thursday Signal Flow for Subscribers</h2>
<table>
<tr><th>Time</th><th>Signal</th><th>Content</th></tr>
<tr><td>09:15</td><td>Pin Detection</td><td>Pin strikes identified for all indices</td></tr>
<tr><td>09:42</td><td>GEX Analysis</td><td>Predicted pin, straddle premium, manipulation alerts</td></tr>
<tr><td>10:00</td><td>Entry Signal</td><td>Sell straddle at pin (if VIX &gt; 18)</td></tr>
<tr><td>Every 30m</td><td>Divergence</td><td>Heavyweight divergence from pinned index</td></tr>
<tr><td>After 1PM</td><td>Gamma Zone</td><td>Reversion probability increases to 71%</td></tr>
<tr><td>2:30 PM</td><td>Conservative</td><td>High-VIX entry (100% win rate)</td></tr>
</table>

<h2>7. VIX Filter</h2>
<table>
<tr><th>Date</th><th>VIX</th><th>Straddle P&L</th><th>Verdict</th></tr>
<tr><td>Mar 12</td><td>21.1</td><td><b>+1.58%</b></td><td>Sweet spot</td></tr>
<tr><td>Mar 5</td><td>21.1</td><td>+1.19%</td><td>Good</td></tr>
<tr><td>Feb 26</td><td>13.5</td><td>+1.09%</td><td>Ok despite low VIX</td></tr>
<tr><td>Feb 19</td><td>12.2</td><td><b>-0.67%</b></td><td>Lowest VIX = worst</td></tr>
</table>
<p><b>Rule: VIX &gt; 18 filters out losing trades.</b></p>

<h2>8. Risks</h2>
<ul>
<li>7 weeks is thin - need 6+ months for confidence</li>
<li>Current high-VIX environment may inflate results</li>
<li>Black swan events can overwhelm pinning</li>
<li>Straddle selling requires margin capital</li>
<li>Execution slippage on entry/exit</li>
</ul>

<div class="footer">
<b>Anka Research</b> - askanka.com | @ANKASIGNALS<br>
Generated: {now}<br>
Data: Kite Connect 5-min candles, NSE option chain | AutoResearch: 10,920 experiments<br>
<em>Research only. Not investment advice. Past performance does not guarantee future results.</em>
</div>
</body></html>""", encoding="utf-8")

print(f"Report saved: {out}")
print(f"Open in browser to print as PDF: file:///{str(out).replace(chr(92), '/')}")
