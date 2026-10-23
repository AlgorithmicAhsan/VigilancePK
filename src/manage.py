"""Admin commands. Run from the project root:

    python -m src.manage init-db
    python -m src.manage import-lists data/client/*.xlsx
    python -m src.manage create-user <username> --role admin
    python -m src.manage list-users
    python -m src.manage list-models
"""
import argparse
import getpass
import sys

from psycopg import errors
from src import auth, db, llm, lookups


def cmd_init_db(args):
    db.init_schema()
    print("Schema is up to date.")
    added = lookups.seed_defaults()
    for kind, count in added.items():
        print(f"Seeded {count} default '{kind}' entries.")


def cmd_import_lists(args):
    for path in args.files:
        kind, rows = lookups.parse_hrms_export(path)
        result = lookups.import_rows(rows)
        print(f"{path}: {kind} - {result['inserted']} added, {result['updated']} updated, {len(result['failed'])} failed")
        for problem in result["failed"]:
            print(f"   ! {problem}")


def cmd_create_user(args):
    # Typed at a prompt, never passed on the command line (shell history).
    password = getpass.getpass(f"Password for {args.username}: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    try:
        hashed = auth.hash_password(password)
    except ValueError as e:
        sys.exit(str(e))
    try:
        with db.connection() as conn:
            conn.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                         (args.username, hashed, args.role))
    except errors.UniqueViolation:
        sys.exit(f"User '{args.username}' already exists.")
    print(f"Created {args.role} '{args.username}'.")


def cmd_list_users(args):
    with db.connection() as conn:
        for u in conn.execute("SELECT username, role, active, created_at FROM users ORDER BY username"):
            print(f"{u['username']:20} {u['role']:9} {'active' if u['active'] else 'disabled':9} {u['created_at']:%Y-%m-%d}")


def cmd_list_models(args):
    for model in llm.client().models.list():
        if "generateContent" in (model.supported_actions or []) or "embedContent" in (model.supported_actions or []):
            print(model.name)


def main():
    parser = argparse.ArgumentParser(prog="python -m src.manage")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("init-db", help="create tables and seed default lists").set_defaults(func=cmd_init_db)
    p = sub.add_parser("import-lists", help="import HRMS Excel exports")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_import_lists)
    p = sub.add_parser("create-user", help="create a dashboard account")
    p.add_argument("username")
    p.add_argument("--role", choices=["admin", "reviewer"], default="reviewer")
    p.set_defaults(func=cmd_create_user)
    sub.add_parser("list-users").set_defaults(func=cmd_list_users)
    sub.add_parser("list-models", help="list Gemini models this key can use").set_defaults(func=cmd_list_models)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
