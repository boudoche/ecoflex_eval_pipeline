#!/usr/bin/env python3

import argparse
import json
import os
import sys
import tempfile
from secrets import token_urlsafe
from typing import Dict


def load_tokens(path: str) -> Dict[str, str]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # ensure all keys/values are strings
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except Exception:
        return {}


def write_tokens_atomic(path: str, data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="tokens.", suffix=".json", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or rotate a submission token for a team")
    parser.add_argument("--team", required=True, help="Team name (participant_id)")
    parser.add_argument("--tokens-path", default=os.getenv("TOKENS_PATH", os.path.join(os.path.dirname(__file__), "tokens.json")), help="Path to tokens JSON mapping {token: team}")
    parser.add_argument("--length", type=int, default=24, help="Token length parameter for token_urlsafe (default 24)")
    parser.add_argument("--rotate", action="store_true", help="Rotate token even if the team already has one")
    args = parser.parse_args()

    tokens_path = args.tokens_path
    mapping = load_tokens(tokens_path)

    # Inverse map: team -> token (first match)
    team_to_token: Dict[str, str] = {}
    for tkn, team in mapping.items():
        team_to_token.setdefault(team, tkn)

    if args.team in team_to_token and not args.rotate:
        token = team_to_token[args.team]
        print(token)
        return

    # Generate a unique token
    token = token_urlsafe(args.length)
    while token in mapping:
        token = token_urlsafe(args.length)

    # Remove old token for team if present
    if args.team in team_to_token:
        old = team_to_token[args.team]
        mapping.pop(old, None)

    # Assign new token
    mapping[token] = args.team

    try:
        write_tokens_atomic(tokens_path, mapping)
    except Exception as exc:
        print(f"Failed to write tokens file: {exc}", file=sys.stderr)
        sys.exit(1)

    print(token)


if __name__ == "__main__":
    main()
