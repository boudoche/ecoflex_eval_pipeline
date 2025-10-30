#!/usr/bin/env python3

import argparse
import json
import os
import smtplib
import ssl
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path
from secrets import token_urlsafe
from typing import Dict, Any


def load_env_file(env_path: str = "/etc/ecoflex.env") -> None:
    """Load environment variables from a file (like systemd EnvironmentFile)."""
    if not os.path.isfile(env_path):
        return
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=VALUE
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    # Only set if not already in environment
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Could not load {env_path}: {e}", file=sys.stderr)


def load_tokens(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def write_tokens_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="tokens.", suffix=".json", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def send_token_email(team: str, emails: list, token: str) -> None:
    """Send email notification with the submission token to multiple recipients."""
    if not emails:
        print("No email provided, skipping email notification", file=sys.stderr)
        return
    
    # Convert single email to list for compatibility
    if isinstance(emails, str):
        emails = [emails] if emails else []
    
    # Filter out empty emails
    emails = [e.strip() for e in emails if e and e.strip()]
    
    if not emails:
        print("No valid email addresses provided, skipping email notification", file=sys.stderr)
        return
    
    # Load SMTP configuration from environment
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", user)
    from_name = os.getenv("SMTP_FROM_NAME", "Argusa Data Challenge")
    reply_to = os.getenv("SMTP_REPLY_TO", from_addr)
    use_ssl = os.getenv("SMTP_USE_SSL", "").lower() in ("1", "true", "yes", "on")
    
    if not host or not from_addr:
        print("Email disabled: SMTP_HOST/SMTP_FROM not configured", file=sys.stderr)
        return
    
    # Email body (plain text) - same for all recipients
    plain_body = f"""Hello {team},

Your submission token has been generated for the Argusa Data Challenge.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUBMISSION TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{token}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ IMPORTANT INFORMATION:

• This token is FOR ONE-TIME USE ONLY
• You can submit your answers using this token
• After submission, the token will be marked as used
• NO additional tokens will be provided except in very special cases
• Keep this token secure and do not share it

Please use this token carefully when submitting your answers.

If you have any questions or encounter issues, please contact the organizers.

Best regards,
Argusa Data Challenge Team
"""
    
    # HTML version (Outlook-compatible using tables and inline styles with Argusa branding)
    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
    <!-- Main container table -->
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
        <tr>
            <td style="padding: 20px 0;">
                <!-- Content wrapper -->
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff;" align="center">
                    
                    <!-- Header with Argusa brand color -->
                    <tr>
                        <td style="background-color: #004B87; padding: 30px 20px; text-align: center; color: #ffffff;">
                            <h1 style="margin: 0 0 10px 0; font-size: 24px; font-weight: bold; color: #ffffff;">🎯 Your Submission Token</h1>
                            <p style="margin: 0; font-size: 16px; color: #ffffff;">Argusa Data Challenge</p>
                        </td>
                    </tr>
                    
                    <!-- Brand color bar (Argusa colors: Blue, Yellow, Black, Orange) -->
                    <tr>
                        <td style="padding: 0;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td width="25%" style="background-color: #004B87; height: 8px;"></td>
                                    <td width="25%" style="background-color: #FDB913; height: 8px;"></td>
                                    <td width="25%" style="background-color: #000000; height: 8px;"></td>
                                    <td width="25%" style="background-color: #E94E1B; height: 8px;"></td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Content section -->
                    <tr>
                        <td style="padding: 30px 20px; background-color: #f9f9f9; border-left: 1px solid #ddd; border-right: 1px solid #ddd;">
                            <p style="margin: 0 0 15px 0; font-size: 16px; color: #333333; line-height: 1.6;">Hello <strong>{team}</strong>,</p>
                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #333333; line-height: 1.6;">Your submission token has been generated for the Argusa Data Challenge.</p>
                            
                            <!-- Token box -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                                <tr>
                                    <td style="background-color: #ffffff; border: 2px solid #004B87; padding: 20px; text-align: center; border-radius: 3px;">
                                        <p style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 18px; font-weight: bold; color: #004B87; word-break: break-all;">{token}</p>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Warning box -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                                <tr>
                                    <td style="background-color: #fff3cd; border-left: 5px solid #FDB913; padding: 15px;">
                                        <p style="margin: 0 0 10px 0; font-size: 16px; font-weight: bold; color: #856404;">⚠️ IMPORTANT INFORMATION</p>
                                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                            <tr>
                                                <td style="padding: 0;">
                                                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #333333; line-height: 1.6;">• <strong>This token is FOR ONE-TIME USE ONLY</strong></p>
                                                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #333333; line-height: 1.6;">• You can submit your answers using this token</p>
                                                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #333333; line-height: 1.6;">• After submission, the token will be marked as used</p>
                                                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #333333; line-height: 1.6;">• <strong>NO additional tokens will be provided except in very special cases</strong></p>
                                                    <p style="margin: 0; font-size: 14px; color: #333333; line-height: 1.6;">• Keep this token secure and do not share it</p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="margin: 20px 0 15px 0; font-size: 16px; color: #333333; line-height: 1.6;">Please use this token carefully when submitting your answers.</p>
                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #333333; line-height: 1.6;">If you have any questions or encounter issues, please contact the organizers.</p>
                            
                            <p style="margin: 20px 0 0 0; font-size: 16px; color: #333333; line-height: 1.6;">Best regards,<br>
                            <strong>Argusa Data Challenge Team</strong></p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f5f5f5; padding: 20px; text-align: center; border-left: 1px solid #ddd; border-right: 1px solid #ddd; border-bottom: 1px solid #ddd;">
                            <!-- Brand color bar -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-bottom: 10px;">
                                <tr>
                                    <td width="25%" style="background-color: #004B87; height: 8px;"></td>
                                    <td width="25%" style="background-color: #FDB913; height: 8px;"></td>
                                    <td width="25%" style="background-color: #000000; height: 8px;"></td>
                                    <td width="25%" style="background-color: #E94E1B; height: 8px;"></td>
                                </tr>
                            </table>
                            <p style="margin: 0; font-size: 12px; color: #666666; line-height: 1.6;">This is an automated message. Please do not reply to this email.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    
    # Send to each email address
    for email in emails:
        if not email:
            continue
        
        try:
            # Build email message for this recipient
            msg = EmailMessage()
            msg["From"] = f"{from_name} <{from_addr}>"
            msg["To"] = email
            msg["Subject"] = f"Your Submission Token - {team}"
            msg["Reply-To"] = reply_to
            msg["X-Mailer"] = "Argusa Token Generator"
            
            msg.set_content(plain_body)
            msg.add_alternative(html_body, subtype="html")
            
            # Send email
            if use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as s:
                    if user and password:
                        s.login(user, password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as s:
                    s.ehlo()
                    try:
                        s.starttls(context=ssl.create_default_context())
                        s.ehlo()
                    except Exception:
                        pass
                    if user and password:
                        s.login(user, password)
                    s.send_message(msg)
            print(f"✅ Email sent successfully to {email}", file=sys.stderr)
        except Exception as exc:
            print(f"❌ Failed to send email to {email}: {exc}", file=sys.stderr)


def main() -> None:
    # Load environment variables from config file (if it exists)
    load_env_file("/etc/ecoflex.env")
    
    parser = argparse.ArgumentParser(description="Generate or rotate a submission token for a team (with optional emails)")
    parser.add_argument("--team", required=True, help="Team name (participant_id)")
    parser.add_argument("--email", default="", help="Email address to attach to the token (can be comma-separated for multiple emails)")
    parser.add_argument("--emails", default="", help="Alternative: comma-separated list of email addresses")
    parser.add_argument("--tokens-path", default=os.getenv("TOKENS_PATH", os.path.join(os.path.dirname(__file__), "tokens.json")), help="Path to tokens JSON mapping")
    parser.add_argument("--length", type=int, default=24, help="Token length parameter for token_urlsafe (default 24)")
    parser.add_argument("--rotate", action="store_true", help="Rotate token even if the team already has one")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email notification")
    parser.add_argument("--env-file", default="/etc/ecoflex.env", help="Path to environment file (default: /etc/ecoflex.env)")
    args = parser.parse_args()
    
    # Combine --email and --emails arguments, split by comma
    email_list = []
    if args.email:
        email_list.extend([e.strip() for e in args.email.split(',') if e.strip()])
    if args.emails:
        email_list.extend([e.strip() for e in args.emails.split(',') if e.strip()])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_emails = []
    for email in email_list:
        if email and email not in seen:
            seen.add(email)
            unique_emails.append(email)
    
    email_list = unique_emails
    
    # Allow loading custom env file via argument
    if args.env_file != "/etc/ecoflex.env":
        load_env_file(args.env_file)

    tokens_path = args.tokens_path
    mapping = load_tokens(tokens_path)

    # Normalize existing mapping to new schema {token: {team,emails,used}}
    # emails can be a string (old format) or list (new format)
    normalized: Dict[str, Any] = {}
    if isinstance(mapping, dict):
        for tkn, val in mapping.items():
            if isinstance(val, str):
                # Old format: token -> team_name
                normalized[tkn] = {"team": val, "emails": [], "used": False}
            elif isinstance(val, dict):
                # New format: token -> {team, email/emails, used}
                team = str(val.get("team", ""))
                used = bool(val.get("used", False))
                
                # Handle both 'email' (old) and 'emails' (new)
                emails = val.get("emails", val.get("email", []))
                if isinstance(emails, str):
                    # Convert old single email to list
                    emails = [emails] if emails else []
                elif not isinstance(emails, list):
                    emails = []
                
                normalized[tkn] = {
                    "team": team,
                    "emails": emails,
                    "used": used,
                }
    mapping = normalized

    # Inverse map: team -> token (first match)
    team_to_token: Dict[str, str] = {}
    for tkn, info in mapping.items():
        team_to_token.setdefault(info.get("team", ""), tkn)

    if args.team in team_to_token and not args.rotate:
        # Update emails if provided
        existing_token = team_to_token[args.team]
        if email_list:
            info = mapping.get(existing_token, {})
            old_emails = info.get("emails", [])
            info["emails"] = email_list
            mapping[existing_token] = info
            try:
                write_tokens_atomic(tokens_path, mapping)
            except Exception as exc:
                print(f"Failed to write tokens file: {exc}", file=sys.stderr)
                sys.exit(1)
            # Send email if emails were just added or changed
            if not args.no_email and email_list and email_list != old_emails:
                send_token_email(args.team, email_list, existing_token)
        print(existing_token)
        return

    # Generate a unique token
    token = token_urlsafe(args.length)
    while token in mapping:
        token = token_urlsafe(args.length)

    # Remove old token for team if present
    if args.team in team_to_token:
        old = team_to_token[args.team]
        mapping.pop(old, None)

    # Assign new token with new schema (emails as list)
    mapping[token] = {"team": args.team, "emails": email_list, "used": False}

    try:
        write_tokens_atomic(tokens_path, mapping)
    except Exception as exc:
        print(f"Failed to write tokens file: {exc}", file=sys.stderr)
        sys.exit(1)

    # Send email notification (if emails provided and not disabled)
    if not args.no_email and email_list:
        send_token_email(args.team, email_list, token)

    print(token)


if __name__ == "__main__":
    main()
