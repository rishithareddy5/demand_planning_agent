import os
import re
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")

ATTACHMENT_DIR = "attachments"
os.makedirs(ATTACHMENT_DIR, exist_ok=True)


def decode_mime_words(value: str) -> str:
    if not value:
        return ""

    decoded_parts = decode_header(value)
    parts = []

    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                parts.append(part.decode(encoding or "utf-8", errors="ignore"))
            except Exception:
                parts.append(part.decode("utf-8", errors="ignore"))
        else:
            parts.append(part)

    return "".join(parts)


def extract_sender_email(from_header: str) -> str:
    _, email_address = parseaddr(from_header)
    return (email_address or "").strip().lower()


def strip_html_tags(html: str) -> str:
    if not html:
        return ""

    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    return text.strip()


def extract_text_from_message(msg) -> str:
    plain_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "").lower()

            if "attachment" in content_disposition:
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset() or "utf-8"

            try:
                decoded_payload = payload.decode(charset, errors="ignore")
            except Exception:
                decoded_payload = payload.decode("utf-8", errors="ignore")

            if content_type == "text/plain":
                plain_body += decoded_payload + "\n"
            elif content_type == "text/html":
                html_body += decoded_payload + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded_payload = payload.decode(charset, errors="ignore")
            except Exception:
                decoded_payload = payload.decode("utf-8", errors="ignore")

            if msg.get_content_type() == "text/html":
                html_body = decoded_payload
            else:
                plain_body = decoded_payload

    if plain_body.strip():
        return plain_body.strip()

    if html_body.strip():
        return strip_html_tags(html_body)

    return ""


def clean_reply_body(body: str) -> str:
    if not body:
        return ""

    lines = body.splitlines()
    cleaned_lines = []

    stop_patterns = [
        "On ",
        "From:",
        "Subject:",
        "Sent:",
        "To:",
        "Cc:",
        "-----Original Message-----"
    ]

    for line in lines:
        stripped = line.strip()

        if any(stripped.startswith(pattern) for pattern in stop_patterns):
            break

        if stripped.startswith(">"):
            continue

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines).strip()
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text


def save_attachments(msg, message_id: str):
    attachment_paths = []

    if not msg.is_multipart():
        return attachment_paths

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition") or "")
        if "attachment" not in content_disposition.lower():
            continue

        filename = part.get_filename()
        if not filename:
            continue

        decoded_filename = decode_mime_words(filename)
        safe_filename = f"{message_id}_{decoded_filename}"
        file_path = os.path.join(ATTACHMENT_DIR, safe_filename)

        payload = part.get_payload(decode=True)
        if payload:
            with open(file_path, "wb") as f:
                f.write(payload)
            attachment_paths.append(file_path)

    return attachment_paths


def read_unseen_replies():
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        raise ValueError("EMAIL_ADDRESS or EMAIL_APP_PASSWORD missing in .env")

    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
    mail.select("inbox")

    # Search all emails with matching subject (no UNSEEN filter)
    # Deduplication is handled by already_saved() in save_to_postgres.py
    # using the real Message-ID header to avoid re-processing
    status, messages = mail.search(None, '(SUBJECT "Re: Demand Request")')

    if status != "OK":
        mail.logout()
        raise Exception("Failed to search inbox")

    email_data = []

    for num in messages[0].split():
        status, msg_data = mail.fetch(num, "(RFC822)")
        if status != "OK":
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Use real Message-ID header instead of IMAP sequence number.
        # IMAP sequence numbers (1, 2, 3...) shift when emails are deleted
        # or the mailbox is re-selected — causing wrong deduplication in DB.
        message_id = msg.get("Message-ID", "").strip() or num.decode()

        subject = decode_mime_words(msg.get("Subject", ""))
        from_header = decode_mime_words(msg.get("From", ""))
        from_email = extract_sender_email(from_header)

        raw_body = extract_text_from_message(msg)
        cleaned_body = clean_reply_body(raw_body)
        attachment_paths = save_attachments(msg, message_id)

        email_data.append({
            "message_id": message_id,
            "from_header": from_header,
            "from_email": from_email,
            "subject": subject,
            "raw_body": raw_body,
            "body": cleaned_body,
            "attachment_paths": attachment_paths,
        })

    mail.logout()
    return email_data


if __name__ == "__main__":
    emails = read_unseen_replies()

    if not emails:
        print("No unread replies found.")
    else:
        for index, item in enumerate(emails, start=1):
            print("=" * 60)
            print(f"Email #{index}")
            print("Message ID:", item["message_id"])
            print("From Email:", item["from_email"])
            print("Subject:", item["subject"])
            print("Body Preview:")
            print(item["body"][:500])
            print("Attachments:", item["attachment_paths"])
            print("=" * 60)