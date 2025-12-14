import resend
import config
import datetime

def send_executive_brief(decision, account_info, junior_reports, portfolio):
    """
    Sends the "Mirror Protocol" Dashboard:
    1. Financial Snapshot (Header)
    2. Action Signals (Trades to Copy Today)
    3. Portfolio Sync (Current Holdings to Match)
    4. Intelligence (Context)
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ Resend API Key missing. Skipping Brief.")
        return

    print("📧 Sending Executive Briefing via Resend...")
    resend.api_key = config.RESEND_API_KEY
    
    today = datetime.date.today().strftime("%b %d, %Y")
    trades = decision.get('final_execution_orders', [])
    junior_map = {r.get('ticker'): r for r in junior_reports}
    
    subject = f"🔔 GVQM Signal: {len(trades)} Actions | {today}"

    # --- STYLES ---
    TH_STYLE = "background-color: #f4f4f4; color: #555; font-size: 10px; text-transform: uppercase; padding: 6px; border: 1px solid #ddd;"
    TD_STYLE = "padding: 6px; border: 1px solid #ddd; font-size: 12px;"
    
    html_content = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; max-width: 800px; margin: auto;">
        
        <div style="background-color: #2c3e50; color: white; padding: 15px; border-radius: 6px 6px 0 0;">
            <table style="width: 100%; border-collapse: collapse; color: white;">
                <tr>
                    <td style="width: 60%;">
                        <h2 style="margin:0;">GVQM Mirror Protocol</h2>
                        <p style="margin:0; font-size: 11px; opacity: 0.8;">Generated {today}</p>
                    </td>
                    <td style="width: 40%; text-align: right;">
                        <span style="font-size: 24px; font-weight: bold;">${float(account_info.equity):,.2f}</span><br>
                        <span style="font-size: 10px; text-transform: uppercase;">Bot Equity</span>
                    </td>
                </tr>
            </table>
        </div>

        <table style="width: 100%; border-collapse: collapse; background-color: #ecf0f1; text-align: center; font-size: 12px;">
            <tr>
                <td style="padding: 8px; border-right: 1px solid #bdc3c7;"><b>💵 Cash:</b> ${float(account_info.cash):,.2f}</td>
                <td style="padding: 8px;"><b>🚀 Buying Power:</b> ${float(account_info.buying_power):,.2f}</td>
            </tr>
        </table>
        <br>

        <h3 style="margin-bottom: 5px; color: #e67e22; border-bottom: 2px solid #e67e22;">🚨 1. Action Signals (Copy These)</h3>
        <p style="margin: 0 0 10px 0; font-size: 11px; color: #777;"><i>Execute these orders in your real account to mirror the strategy.</i></p>
        
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
            <thead>
                <tr style="background-color: #f8f9fa;">
                    <th style="{TH_STYLE}">Action</th>
                    <th style="{TH_STYLE}">Ticker</th>
                    <th style="{TH_STYLE}">Limit Price</th>
                    <th style="{TH_STYLE}">TP / SL</th>
                    <th style="{TH_STYLE} width: 40%;">Rationale & Justification</th>
                </tr>
            </thead>
            <tbody>
    """
    
    if not trades:
        html_content += f"<tr><td colspan='5' style='{TD_STYLE} text-align: center; color: #999;'>No actions required today. Hold positions.</td></tr>"
    else:
        for order in trades:
            p = order.get('confirmed_params', {})
            action = order.get('action', 'HOLD')
            ticker = order.get('ticker')
            reason = order.get('reason', 'N/A')
            
            # Color Coding
            if action == "OPEN_NEW":
                badge = "<span style='color: #27ae60; font-weight: bold;'>🟢 OPEN</span>"
                bg = "#eafaf1"
            elif action == "UPDATE_EXISTING":
                badge = "<span style='color: #2980b9; font-weight: bold;'>♻️ UPDATE</span>"
                bg = "#ebf5fb"
            elif action == "CANCEL":
                badge = "<span style='color: #c0392b; font-weight: bold;'>🚫 CANCEL</span>"
                bg = "#fdedec"
            else:
                badge = "<span style='color: #7f8c8d; font-weight: bold;'>🛑 HOLD</span>"
                bg = "#ffffff"

            html_content += f"""
                <tr style="background-color: {bg};">
                    <td style="{TD_STYLE}">{badge}</td>
                    <td style="{TD_STYLE}"><b>{ticker}</b></td>
                    <td style="{TD_STYLE}">${p.get('buy_limit', '-')}</td>
                    <td style="{TD_STYLE}">
                        <span style="color: #27ae60;">${p.get('take_profit', '-')}</span> / 
                        <span style="color: #c0392b;">${p.get('stop_loss', '-')}</span>
                    </td>
                    <td style="{TD_STYLE} font-style: italic;">{reason}</td>
                </tr>
            """

    html_content += """
            </tbody>
        </table>
        <br>

        <h3 style="margin-bottom: 5px; color: #2c3e50; border-bottom: 2px solid #2c3e50;">📂 2. Portfolio Sync (Audit)</h3>
        <p style="margin: 0 0 10px 0; font-size: 11px; color: #777;"><i>Current bot holdings. Ensure your real portfolio matches this list.</i></p>
        
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
            <thead>
                <tr style="background-color: #f8f9fa;">
                    <th style="{TH_STYLE}">Ticker</th>
                    <th style="{TH_STYLE}">Qty</th>
                    <th style="{TH_STYLE}">Avg Entry</th>
                    <th style="{TH_STYLE}">Current</th>
                    <th style="{TH_STYLE}">P/L ($)</th>
                    <th style="{TH_STYLE}">P/L (%)</th>
                </tr>
            </thead>
            <tbody>
    """

    if not portfolio:
        html_content += f"<tr><td colspan='6' style='{TD_STYLE} text-align: center; color: #999;'>Portfolio is currently 100% Cash.</td></tr>"
    else:
        for pos in portfolio:
            # Parse Data
            symbol = pos.symbol
            qty = pos.qty
            avg_entry = float(pos.avg_entry_price)
            current_price = float(pos.current_price)
            unrealized_pl = float(pos.unrealized_pl)
            unrealized_plpc = float(pos.unrealized_plpc) * 100
            
            # P/L Styling
            pl_color = "#27ae60" if unrealized_pl >= 0 else "#c0392b"
            pl_icon = "▲" if unrealized_pl >= 0 else "▼"

            html_content += f"""
            <tr>
                <td style="{TD_STYLE}"><b>{symbol}</b></td>
                <td style="{TD_STYLE}">{qty}</td>
                <td style="{TD_STYLE}">${avg_entry:,.2f}</td>
                <td style="{TD_STYLE}"><b>${current_price:,.2f}</b></td>
                <td style="{TD_STYLE} color: {pl_color}; font-weight: bold;">{pl_icon} ${unrealized_pl:,.2f}</td>
                <td style="{TD_STYLE} color: {pl_color};">{unrealized_plpc:,.2f}%</td>
            </tr>
            """

    html_content += f"""
            </tbody>
        </table>
        <br>

        <div style="background-color: #fcfcfc; border-left: 4px solid #34495e; padding: 15px; margin-top: 10px;">
            <h4 style="margin-top: 0; color: #34495e;">🗣️ CEO Strategy Note</h4>
            <p style="font-size: 13px; line-height: 1.5; color: #555;">
                "{decision.get('ceo_report', 'No report available.')}"
            </p>
        </div>

        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 10px; color: #999; text-align: center;">
            Generated by GVQM Alpha Protocol v3.0 | Time: {datetime.datetime.now().strftime("%H:%M EST")}
        </p>
    </body>
    </html>
    """
    
    # --- SEND ---
    try:
        r = resend.Emails.send({
            "from": config.EMAIL_SENDER,
            "to": config.EMAIL_RECIPIENT,
            "subject": subject,
            "html": html_content
        })
        print(f"✅ Email sent successfully. RESEND ID: {r.get('id')}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")