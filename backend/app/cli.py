r"""Operator CLI for pipeline stages that exist so far.

Examples (PowerShell, from backend/):
    $env:DATABASE_URL = "sqlite:///outreach.db"   # until Postgres is up
    python -m app.cli init-db
    python -m app.cli import-csv .\colleges.csv
    python -m app.cli research --limit 5
"""

import argparse
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.discovery.importer import import_colleges_csv
from app.llm.providers import get_provider
from app.models import Base, College, ResearchStatus, ResearchSummary
from app.research.engine import research_college
from app.research.fetcher import PoliteFetcher


def cmd_init_db(_args) -> None:
    Base.metadata.create_all(engine)
    print(f"Schema created on {engine.url}")


def cmd_import_csv(args) -> None:
    csv_text = Path(args.path).read_text(encoding="utf-8-sig")
    with SessionLocal() as db:
        result = import_colleges_csv(db, csv_text, source_label=Path(args.path).name)
    print(result)


def cmd_research(args) -> None:
    settings = get_settings()
    llm = get_provider(settings.llm_provider, settings.llm_api_key, settings.llm_model)
    fetcher = PoliteFetcher()
    with SessionLocal() as db:
        pending = (
            db.query(College)
            .outerjoin(ResearchSummary)
            .filter(
                (ResearchSummary.id.is_(None))
                | (ResearchSummary.status.in_([ResearchStatus.PENDING, ResearchStatus.FAILED]))
            )
            .filter(College.website.isnot(None))
            .limit(args.limit)
            .all()
        )
        if not pending:
            print("Nothing to research (no colleges with websites lacking a DONE summary).")
            return
        for college in pending:
            record = research_college(db, college, fetcher, llm)
            print(f"{college.name}: {record.status.value}"
                  + (f" ({record.last_error})" if record.last_error else ""))


def cmd_discover_contacts(args) -> None:
    from app.contacts.engine import discover_contacts

    settings = get_settings()
    llm = get_provider(settings.llm_provider, settings.llm_api_key, settings.llm_model)
    fetcher = PoliteFetcher()
    with SessionLocal() as db:
        colleges = (
            db.query(College)
            .filter(College.website.isnot(None))
            .limit(args.limit)
            .all()
        )
        for college in colleges:
            contacts = discover_contacts(db, college, fetcher, llm)
            print(f"{college.name}: {len(contacts)} decision-maker(s)")
            for c in contacts:
                print(f"  - {c.full_name} | {c.role.value} | {c.email or 'NO EMAIL'} "
                      f"| confidence {c.confidence} | {c.status.value}")


def cmd_draft_emails(args) -> None:
    from app.models import ContactStatus
    from app.personalize.engine import generate_draft

    settings = get_settings()
    llm = get_provider(settings.llm_provider, settings.llm_api_key, settings.llm_model)
    with SessionLocal() as db:
        from app.models import Contact, EmailDraft

        drafted_ids = db.query(EmailDraft.contact_id).filter(EmailDraft.touch_number == 1)
        contacts = (
            db.query(Contact)
            .filter(Contact.status == ContactStatus.VERIFIED,
                    ~Contact.id.in_(drafted_ids))
            .limit(args.limit)
            .all()
        )
        for contact in contacts:
            draft = generate_draft(db, contact, llm)
            ok = "PASS" if draft.lint_report.get("ok") else f"LINT FAIL {draft.lint_report['errors']}"
            print(f"draft #{draft.id} for {contact.full_name} ({contact.college.name}): {ok}")


def cmd_show_draft(args) -> None:
    from app.models import EmailDraft

    with SessionLocal() as db:
        draft = db.get(EmailDraft, args.id)
        if not draft:
            print(f"No draft with id {args.id}")
            return
        print(f"Status: {draft.status.value} | lint ok: {draft.lint_report.get('ok')}")
        print("Subjects:")
        for i, s in enumerate(draft.subject_options or [], 1):
            print(f"  {i}. {s}")
        print("\n" + (draft.body_text or "<empty>"))


def cmd_approve_draft(args) -> None:
    from app.models import EmailDraft
    from app.personalize.engine import approve_draft

    with SessionLocal() as db:
        draft = db.get(EmailDraft, args.id)
        if not draft:
            print(f"No draft with id {args.id}")
            return
        approve_draft(db, draft, user_id=None)
        print(f"Draft {draft.id} approved.")


def cmd_send(args) -> None:
    from app.sender.providers import SMTPSender
    from app.sender.service import remaining_quota, send_approved_batch

    with SessionLocal() as db:
        quota = remaining_quota(db)
        print(f"Quota remaining (daily/hourly caps): {quota}")
        if args.dry_run:
            from app.models import DraftStatus, EmailDraft

            approved = db.query(EmailDraft).filter_by(status=DraftStatus.APPROVED).count()
            print(f"Dry run: {approved} approved draft(s) queued; nothing sent.")
            return
        stats = send_approved_batch(db, SMTPSender(), limit=args.limit)
        print(stats)


def cmd_create_user(args) -> None:
    import getpass

    from app.core.security import hash_password
    from app.models import User, UserRole

    password = args.password or getpass.getpass("Password: ")
    with SessionLocal() as db:
        if db.query(User).filter(User.email.ilike(args.email)).count():
            print(f"User {args.email} already exists")
            return
        db.add(User(email=args.email.lower(), full_name=args.name,
                    hashed_password=hash_password(password),
                    role=UserRole(args.role.upper())))
        db.commit()
    print(f"Created {args.role} user {args.email}")


def cmd_followups(args) -> None:
    from app.followups.runner import run_due_followups

    settings = get_settings()
    llm = get_provider(settings.llm_provider, settings.llm_api_key, settings.llm_model)
    with SessionLocal() as db:
        print(run_due_followups(db, llm))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="outreach")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create all tables on DATABASE_URL")

    p_import = sub.add_parser("import-csv", help="import colleges from a CSV file")
    p_import.add_argument("path")

    p_research = sub.add_parser("research", help="research colleges lacking a summary")
    p_research.add_argument("--limit", type=int, default=10)

    p_discover = sub.add_parser("discover-contacts", help="find decision-makers per college")
    p_discover.add_argument("--limit", type=int, default=10)

    p_draft = sub.add_parser("draft-emails", help="generate drafts for verified contacts")
    p_draft.add_argument("--limit", type=int, default=10)

    p_show = sub.add_parser("show-draft", help="print a draft's subjects and body")
    p_show.add_argument("id", type=int)

    p_approve = sub.add_parser("approve-draft", help="approve a lint-passing draft")
    p_approve.add_argument("id", type=int)

    p_send = sub.add_parser("send", help="send approved drafts (respects caps + suppression)")
    p_send.add_argument("--limit", type=int, default=None)
    p_send.add_argument("--dry-run", action="store_true")

    p_user = sub.add_parser("create-user", help="create a dashboard/API user")
    p_user.add_argument("email")
    p_user.add_argument("--name", default="Operator")
    p_user.add_argument("--role", default="admin", choices=["admin", "operator", "viewer"])
    p_user.add_argument("--password", default=None)

    sub.add_parser("followups", help="draft due follow-ups, reconcile schedules")

    args = parser.parse_args(argv)
    {
        "create-user": cmd_create_user,
        "followups": cmd_followups,
        "send": cmd_send,
        "init-db": cmd_init_db,
        "import-csv": cmd_import_csv,
        "research": cmd_research,
        "discover-contacts": cmd_discover_contacts,
        "draft-emails": cmd_draft_emails,
        "show-draft": cmd_show_draft,
        "approve-draft": cmd_approve_draft,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
