"""Create a scrypt hash for the opt-in judge demo account."""

from getpass import getpass
import hashlib
import secrets


def main() -> None:
    password = getpass("New judge demo password (minimum 16 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    if len(password) < 16:
        raise SystemExit("Use at least 16 characters.")

    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    print("JUDGE_DEMO_PASSWORD_HASH=scrypt$16384$8$1$" + salt.hex() + "$" + digest.hex())


if __name__ == "__main__":
    main()
