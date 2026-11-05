import getpass
import os

from scitracker.domain.errors import DomainError
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.services.accounts import create_admin_user
from scitracker.storage.database import create_db_engine, create_session_factory
from scitracker.storage.repositories import SqlUserRepository


def main() -> None:
    email = input("Admin email: ").strip()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    factory = create_session_factory(create_db_engine(os.environ["DATABASE_URL"]))
    try:
        with factory() as session, session.begin():
            user = create_admin_user(
                SqlUserRepository(session), Argon2PasswordHasher(), email=email, password=password
            )
    except DomainError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Administrator {user.email} created")  # noqa: T201


if __name__ == "__main__":
    main()
