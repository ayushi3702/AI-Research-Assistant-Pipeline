"""
Authentication utilities — JWT tokens, password hashing, email verification.
"""
from __future__ import annotations
import os
import secrets
import datetime
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
VERIFY_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_verification_token(email: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=VERIFY_TOKEN_EXPIRE_MINUTES)
    payload = {"email": email, "purpose": "verify", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def send_verification_email(email: str, token: str) -> None:
    """
    Send verification email. Uses SMTP if configured, otherwise logs the link.
    """
    import logging
    logger = logging.getLogger(__name__)

    base_url = os.getenv("APP_BASE_URL", "http://localhost:3000")
    verify_url = f"{base_url}/api/auth/verify?token={token}"

    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        from_email = os.getenv("SMTP_FROM", smtp_user)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Verify your email - AI Research Assistant"
        msg["From"] = from_email
        msg["To"] = email

        html = f"""
        <html>
        <body>
            <h2>Verify your email</h2>
            <p>Click the link below to verify your account:</p>
            <p><a href="{verify_url}">Verify Email</a></p>
            <p>This link expires in 24 hours.</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, email, msg.as_string())

        logger.info(f"[auth] Verification email sent to {email}")
    else:
        # No SMTP configured — log the verification link
        logger.warning(
            f"[auth] SMTP not configured. Verification link for {email}: {verify_url}"
        )


async def send_report_notification(email: str, query: str, job_id: str, user_id: str = None) -> None:
    """
    Send email notification when a research report is generated.
    Logs the notification to DB regardless of SMTP success.
    """
    import logging
    logger = logging.getLogger(__name__)

    base_url = os.getenv("APP_BASE_URL", "http://localhost:3000")
    report_url = f"{base_url}?job={job_id}"
    subject = f"Your research report is ready: {query[:50]}"
    preview = f"Research on '{query[:80]}' has been completed. Click to view your report."
    send_status = "sent"

    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        from_email = os.getenv("SMTP_FROM", smtp_user)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your research report is ready: {query[:50]}"
        msg["From"] = from_email
        msg["To"] = email

        html = f"""
        <html>
        <body style="font-family: 'Helvetica', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #4361ee, #6366f1); padding: 24px; border-radius: 12px; color: white; text-align: center;">
                <h1 style="margin: 0; font-size: 22px;">📄 Report Ready!</h1>
            </div>
            <div style="padding: 24px; background: #f8fafc; border-radius: 0 0 12px 12px; border: 1px solid #e2e8f0; border-top: none;">
                <p style="color: #334155; font-size: 15px;">Your research report has been generated successfully.</p>
                <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0;">
                    <p style="margin: 0; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Research Topic</p>
                    <p style="margin: 4px 0 0; color: #1e293b; font-size: 15px; font-weight: 500;">{query}</p>
                </div>
                <a href="{report_url}" style="display: inline-block; background: #4361ee; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 500; font-size: 14px;">
                    View Report →
                </a>
                <p style="color: #94a3b8; font-size: 12px; margin-top: 20px;">AI Research Assistant Pipeline</p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_user:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, email, msg.as_string())
            logger.info(f"[notify] Report notification sent to {email} for job {job_id}")
        except Exception as e:
            send_status = "failed"
            logger.error(f"[notify] Failed to send notification to {email}: {e}")
    else:
        logger.info(f"[notify] SMTP not configured. Report ready for {email}: {report_url}")

    # Log notification to DB
    if user_id:
        try:
            from shared.database import SessionLocal, NotificationLog
            db = SessionLocal()
            log = NotificationLog(
                user_id=user_id,
                type="report_ready",
                subject=subject,
                preview=preview,
                ref_id=job_id,
                status=send_status,
                is_read=False,
            )
            db.add(log)
            db.commit()
            db.close()
        except Exception as db_err:
            logger.warning(f"[notify] Failed to log notification: {db_err}")
