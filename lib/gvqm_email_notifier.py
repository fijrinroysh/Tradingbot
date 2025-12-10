import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config
import datetime

def send_executive_brief(decision, account_info, junior_reports):
    """
    Sends the HTML formatted morning brief with CEO outlook, Trade Ticket, and Junior Intel.
    """
    if not hasattr(config, 'EMAIL_SENDER') or not config.EMAIL_SENDER:
        print("⚠️ Email configuration missing. Skipping Brief.")
        return

    print("📧 Sending Executive Briefing...")
    
    today = datetime.date.today().strftime("%b %d, %Y")
    trades = decision.get('final_execution_orders', [])
    
    # 1. SETUP EMAIL
    msg = MIMEMultipart("alternative")
    msg['Subject'] = f"🔔 Daily Executive Brief: {len(trades)} Trades [{today}]"
    msg['From'] = config.EMAIL_SENDER
    msg['To'] = config.EMAIL_RECIPIENT

    # 2. CONSTRUCT HTML CONTENT
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: auto;">
        
        <div style="background-color: #2c3e50; color: white; padding: 15px; text-align: center; border-radius: 5px 5px 0 0;">
            <h2 style="margin:0;">📈 GVQM Executive Brief</h2>
            <p style="margin:0; font-size: 0.9em;">{today}</p>
        </div>

        <h3 style="color: #2980b9; border-bottom: 2px solid #2980b9; padding-bottom: 5px;">🗣️ 1. The CEO's Morning Outlook</h3>
        <p style="background-color: #f8f9fa; padding: 15px; border-left: 5px solid #2980b9; font-style: italic;">
            "{decision.get('ceo_report', 'No report available.')}"
        </p>

        <h3 style="color: #27ae60; border-bottom: 2px solid #27ae60; padding-bottom: 5px;">🎫 2. The "Copy-Paste" Trade Ticket</h3>
        <p><i>Actionable moves for your Real Portfolio.</i></p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9em;">
            <tr style="background-color: #ecf0f1; text-align: left;">
                <th style="padding: 8px; border: 1px solid #ddd;">Action</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Ticker</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Limit Price</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Take Profit</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Stop Loss</th>
            </tr>
    """
    
    # Loop through orders to build table rows
    for order in trades:
        p = order.get('confirmed_params', {})
        action = order.get('action', 'HOLD')
        
        # Styling
        if action == "OPEN_NEW":
            action_style = "color: #27ae60; font-weight: bold;" # Green
            icon = "🟢"
        else:
            action_style = "color: #e67e22; font-weight: bold;" # Orange
            icon = "♻️"
        
        row = f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; {action_style}">{icon} {action}</td>
                <td style="padding: 8px; border: 1px solid #ddd;"><b>{order.get('ticker')}</b></td>
                <td style="padding: 8px; border: 1px solid #ddd;">${p.get('buy_limit', '-')}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">${p.get('take_profit', '-')}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">${p.get('stop_loss', '-')}</td>
            </tr>
        """
        html_content += row

    html_content += """
        </table>

        <h3 style="color: #8e44ad; border-bottom: 2px solid #8e44ad; padding-bottom: 5px;">🧠 3. Analyst Intelligence</h3>
    """

    # Loop to find matching reports
    for order in trades:
        ticker = order.get('ticker')
        # Find the report for this ticker
        report = next((r for r in junior_reports if r.get('ticker') == ticker), None)
        
        if report:
            html_content += f"""
            <div style="margin-bottom: 15px; border: 1px solid #eee; padding: 10px; border-radius: 5px;">
                <h4 style="margin-top: 0; color: #444;">Why {ticker}?</h4>
                <ul style="font-size: 0.9em; color: #555;">
                    <li><b>Conviction:</b> {report.get('conviction_score')}/100</li>
                    <li><b>Catalyst:</b> {report.get('catalysts', 'N/A')}</li>
                    <li><b>Valuation:</b> {report.get('valuation', 'N/A')}</li>
                    <li><b>Technical:</b> {report.get('technical_setup', 'N/A')}</li>
                </ul>
            </div>
            """

    html_content += """
        <h3 style="color: #34495e; border-bottom: 2px solid #34495e; padding-bottom: 5px;">📊 4. Paper Portfolio Scoreboard</h3>
        <div style="background-color: #f1f2f6; padding: 10px; border-radius: 5px;">
            <p style="margin: 5px 0;"><b>💰 Total Equity:</b> ${:,.2f}</p>
            <p style="margin: 5px 0;"><b>💵 Cash on Hand:</b> ${:,.2f}</p>
            <p style="margin: 5px 0;"><b>🚀 Buying Power:</b> ${:,.2f}</p>
        </div>
        
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 11px; color: #999; text-align: center;">Generated by GVQM AI Trading Bot v14.0</p>
    </body>
    </html>
    """.format(
        float(account_info.equity),
        float(account_info.cash),
        float(account_info.buying_power)
    )

    # 3. SEND
    part = MIMEText(html_content, 'html')
    msg.attach(part)

    try:
        # Connect to Gmail SMTP
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print("✅ Email sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")