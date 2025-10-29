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


def send_token_email(team: str, email: str, token: str) -> None:
    """Send email notification with the submission token."""
    if not email:
        print("No email provided, skipping email notification", file=sys.stderr)
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
    
    # Build email message
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = email
    msg["Subject"] = f"Your Submission Token - {team}"
    msg["Reply-To"] = reply_to
    msg["X-Mailer"] = "Argusa Token Generator"
    
    # Email body (plain text)
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
    
    # HTML version (prettier)
    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .token-box {{ background: #fff; border: 2px solid #667eea; padding: 20px; margin: 20px 0; border-radius: 5px; text-align: center; }}
        .token {{ font-family: monospace; font-size: 18px; font-weight: bold; color: #667eea; word-break: break-all; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
        .warning-title {{ color: #856404; font-weight: bold; margin-bottom: 10px; }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 8px; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Your Submission Token</h1>
            <p>Argusa Data Challenge</p>
        </div>
        <div class="content">
            <p>Hello <strong>{team}</strong>,</p>
            <p>Your submission token has been generated for the Argusa Data Challenge.</p>
            
            <div class="token-box">
                <div class="token">{token}</div>
            </div>
            
            <div class="warning">
                <div class="warning-title">⚠️ IMPORTANT INFORMATION</div>
                <ul>
                    <li><strong>This token is FOR ONE-TIME USE ONLY</strong></li>
                    <li>You can submit your answers using this token</li>
                    <li>After submission, the token will be marked as used</li>
                    <li><strong>NO additional tokens will be provided except in very special cases</strong></li>
                    <li>Keep this token secure and do not share it</li>
                </ul>
            </div>
            
            <p>Please use this token carefully when submitting your answers.</p>
            <p>If you have any questions or encounter issues, please contact the organizers.</p>
            
            <div class="footer">
                <p>Best regards,<br>
                <strong>Argusa Data Challenge Team</strong></p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")
    
    # Send email
    try:
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
    
    parser = argparse.ArgumentParser(description="Generate or rotate a submission token for a team (with optional email)")
    parser.add_argument("--team", required=True, help="Team name (participant_id)")
    parser.add_argument("--email", default="", help="Email address to attach to the token")
    parser.add_argument("--tokens-path", default=os.getenv("TOKENS_PATH", os.path.join(os.path.dirname(__file__), "tokens.json")), help="Path to tokens JSON mapping")
    parser.add_argument("--length", type=int, default=24, help="Token length parameter for token_urlsafe (default 24)")
    parser.add_argument("--rotate", action="store_true", help="Rotate token even if the team already has one")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email notification")
    parser.add_argument("--env-file", default="/etc/ecoflex.env", help="Path to environment file (default: /etc/ecoflex.env)")
    args = parser.parse_args()
    
    # Allow loading custom env file via argument
    if args.env_file != "/etc/ecoflex.env":
        load_env_file(args.env_file)

    tokens_path = args.tokens_path
    mapping = load_tokens(tokens_path)

    # Normalize existing mapping to new schema {token: {team,email,used}}
    normalized: Dict[str, Any] = {}
    if isinstance(mapping, dict):
        for tkn, val in mapping.items():
            if isinstance(val, str):
                normalized[tkn] = {"team": val, "email": "", "used": False}
            elif isinstance(val, dict):
                normalized[tkn] = {
                    "team": str(val.get("team", "")),
                    "email": str(val.get("email", "")),
                    "used": bool(val.get("used", False)),
                }
    mapping = normalized

    # Inverse map: team -> token (first match)
    team_to_token: Dict[str, str] = {}
    for tkn, info in mapping.items():
        team_to_token.setdefault(info.get("team", ""), tkn)

    if args.team in team_to_token and not args.rotate:
        # Update email if provided
        existing_token = team_to_token[args.team]
        if args.email:
            info = mapping.get(existing_token, {})
            old_email = info.get("email", "")
            info["email"] = args.email
            mapping[existing_token] = info
            try:
                write_tokens_atomic(tokens_path, mapping)
            except Exception as exc:
                print(f"Failed to write tokens file: {exc}", file=sys.stderr)
                sys.exit(1)
            # Send email if email was just added or changed
            if not args.no_email and args.email and args.email != old_email:
                send_token_email(args.team, args.email, existing_token)
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

    # Assign new token with new schema
    mapping[token] = {"team": args.team, "email": args.email, "used": False}

    try:
        write_tokens_atomic(tokens_path, mapping)
    except Exception as exc:
        print(f"Failed to write tokens file: {exc}", file=sys.stderr)
        sys.exit(1)

    # Send email notification (if email provided and not disabled)
    if not args.no_email and args.email:
        send_token_email(args.team, args.email, token)

    print(token)


if __name__ == "__main__":
    main()
