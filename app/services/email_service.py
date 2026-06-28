from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


class EmailService:

    async def send_password_reset(
        self,
        email: str,
        first_name: str,
        reset_link: str,
    ):

        message = EmailMessage()

        message["From"] = settings.SMTP_EMAIL
        message["To"] = email
        message["Subject"] = "Reset your InvestorDocs password"

        html = f"""
        <html>

        <body
        style="
        font-family:Arial;
        max-width:650px;
        margin:auto;
        padding:30px;
        ">

            <h2>Hello {first_name},</h2>

            <p>
            We received a request to reset your password.
            </p>

            <p>
            Click the button below to reset it.
            </p>

            <p>

            <a
                href="{reset_link}"
                style="
                    background:#2563eb;
                    color:white;
                    padding:14px 24px;
                    text-decoration:none;
                    border-radius:8px;
                    display:inline-block;
                "
            >
                Reset Password
            </a>

            </p>

            <p>
            This link expires in 30 minutes.
            </p>

            <hr>

            <p style="font-size:13px;color:gray">
            If you didn't request this password reset,
            you can safely ignore this email.
            </p>

            <br>

            <strong>InvestorDocs AI</strong>

        </body>

        </html>
        """

        message.set_content(
            f"Reset your password here:\n\n{reset_link}"
        )

        message.add_alternative(
            html,
            subtype="html",
        )

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            start_tls=True,
            username=settings.SMTP_EMAIL,
            password=settings.SMTP_PASSWORD,
        )