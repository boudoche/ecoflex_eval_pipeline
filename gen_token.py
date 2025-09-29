#!/usr/bin/env python3

import argparse
import json
import os
import sys
import tempfile
from secrets import token_urlsafe
from typing import Dict, Any


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or rotate a submission token for a team (with optional email)")
    parser.add_argument("--team", required=True, help="Team name (participant_id)")
    parser.add_argument("--email", default="", help="Email address to attach to the token")
    parser.add_argument("--tokens-path", default=os.getenv("TOKENS_PATH", os.path.join(os.path.dirname(__file__), "tokens.json")), help="Path to tokens JSON mapping")
    parser.add_argument("--length", type=int, default=24, help="Token length parameter for token_urlsafe (default 24)")
    parser.add_argument("--rotate", action="store_true", help="Rotate token even if the team already has one")
    args = parser.parse_args()

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
            info["email"] = args.email
            mapping[existing_token] = info
            try:
                write_tokens_atomic(tokens_path, mapping)
            except Exception as exc:
                print(f"Failed to write tokens file: {exc}", file=sys.stderr)
                sys.exit(1)
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

    print(token)


if __name__ == "__main__":
    main()
