
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# SMTP Configuration (User should update these in .env)
SMTP_SERVER   = os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL  = os.getenv("SENDER_EMAIL") or os.getenv("SMTP_FROM") or SMTP_USERNAME
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")

def send_rtr_email(candidate_email: str, candidate_name: str, rtr_content: str, otp: str, agreement_id: str):
    """
    Sends the RTR agreement and OTP to the candidate.
    """
    verify_link = f"{FRONTEND_URL}/verify-rtr?id={agreement_id}"
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("WARNING: SMTP credentials not set. Email not sent.")
        return False

    msg = MIMEMultipart('alternative')
    msg['From'] = SENDER_EMAIL
    msg['To'] = candidate_email
    msg['Subject'] = "ACTION REQUIRED: Right to Represent (RTR) Agreement - Aigrev LLC"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2 style="color: #2563eb;">Right to Represent (RTR) Agreement</h2>
            <p>Dear <strong>{candidate_name}</strong>,</p>
            <p>Please review the agreement below. To accept and sign this agreement, use the OTP provided and click the button below:</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <div style="font-size: 24px; font-weight: bold; background: #f3f4f6; display: inline-block; padding: 10px 20px; border-radius: 5px; color: #1f2937; letter-spacing: 5px;">
                    {otp}
                </div>
                <p style="font-size: 12px; color: #6b7280; margin-top: 5px;">Verification OTP</p>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{verify_link}" style="background-color: #2563eb; color: white; padding: 15px 30px; text-decoration: none; font-weight: bold; border-radius: 5px; display: inline-block;">
                    View & Sign Agreement
                </a>
            </div>

            <div style="background: #f9fafb; padding: 15px; border-radius: 5px; font-size: 13px; color: #4b5563; border-left: 4px solid #2563eb;">
                <strong>Agreement Content:</strong><br/>
                <pre style="white-space: pre-wrap; margin-top: 10px;">{rtr_content}</pre>
            </div>

            <p style="margin-top: 20px; font-size: 12px; color: #9ca3af;">
                Note: This link and OTP are confidential. If you did not expect this email, please ignore it.
            </p>
            
            <hr style="border: 0; border-top: 1px solid #eee; margin-top: 20px;">
            <p style="font-size: 11px; color: #9ca3af; text-align: center;">Aigrev LLC - AI Recruitment Platform</p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
