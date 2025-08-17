import os, base64, json, re, time
from typing import Dict, Any, List, Tuple

from groq import Groq
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
INTERNAL_PROCESSED_LABEL = "AI/Processed"
AI_IMPORTANT_LABEL = "AI/Important"
MAX_RESULTS = 100
BODY_CHAR_LIMIT = 8000  # keep tokens/cost small

GROQ_MODEL = "moonshotai/kimi-k2-instruct"  # Fast and effective Groq model

def gmail_client():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                print("Please re-authenticate by running locally first to generate a fresh token.json")
                raise RuntimeError("Authentication failed - token expired and refresh failed")
        else:
            # In cloud environment, we can't run interactive OAuth
            if not os.path.exists("client_secret.json"):
                raise RuntimeError("client_secret.json not found. Please upload this file to your cloud service.")
            
            print("ERROR: No valid token.json found and running in cloud environment.")
            print("To fix this:")
            print("1. Run this script locally first with: python gmail_groq_worker.py")
            print("2. Complete the OAuth flow in your browser")
            print("3. Upload the generated token.json file to your cloud service")
            print("4. Redeploy your application")
            raise RuntimeError("Authentication required - run locally first to generate token.json")
        
        # Save refreshed credentials
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def ensure_label(service, name: str) -> str:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for l in labels:
        if l["name"] == name:
            return l["id"]
    new_label = service.users().labels().create(
        userId="me", body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    ).execute()
    return new_label["id"]

def get_unprocessed_message_ids(service, processed_label_id: str) -> List[str]:
    # Get recent emails not yet processed, excluding trash and already marked spam
    q = f"-label:{INTERNAL_PROCESSED_LABEL} -in:trash -in:spam newer_than:7d"
    res = service.users().messages().list(userId="me", q=q, maxResults=MAX_RESULTS).execute()
    return [m["id"] for m in res.get("messages", [])]

def _decode_part(b64: str) -> str:
    return base64.urlsafe_b64decode(b64.encode("UTF-8")).decode(errors="ignore")

def _collect_text(payload: Dict[str, Any]) -> str:
    # Walk parts, prefer text/plain, fallback to html->text
    def walk(p) -> Tuple[str, str]:
        mime = p.get("mimeType", "")
        bd = p.get("body", {})
        data = bd.get("data")
        if data and mime == "text/plain":
            return (_decode_part(data), "")
        if data and mime == "text/html":
            html = _decode_part(data)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return ("", text)
        parts = p.get("parts", [])
        txts, htmls = [], []
        for child in parts:
            t, h = walk(child)
            if t: txts.append(t)
            if h: htmls.append(h)
        return ("\n".join(txts), "\n".join(htmls))

    t, h = walk(payload)
    if t.strip():
        return t
    return h

def fetch_message(service, msg_id: str) -> Dict[str, Any]:
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

def headers_map(msg) -> Dict[str, str]:
    headers = {}
    for h in msg["payload"].get("headers", []):
        headers[h["name"].lower()] = h["value"]
    return headers

def summarize_for_llm(msg) -> Dict[str, Any]:
    hdrs = headers_map(msg)
    subject = hdrs.get("subject", "")
    from_ = hdrs.get("from", "")
    to = hdrs.get("to", "")
    cc = hdrs.get("cc", "")
    body = _collect_text(msg["payload"])[:BODY_CHAR_LIMIT]
    snippet = msg.get("snippet", "")
    return {
        "subject": subject, "from": from_, "to": to, "cc": cc,
        "snippet": snippet, "body": body
    }

def groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY env var not set")
    return Groq(api_key=api_key)

CLASSIFY_PROMPT_SYS = """You are an aggressive spam filter and email organizer. Your goal is to keep the inbox clean.

Return ONLY valid JSON matching this schema:
{
  "is_spam": true|false,
  "is_important": true|false,
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "actions": {
    "mark_spam": true|false,
    "star": true|false,
    "archive": true|false,
    "mark_read": true|false
  }
}

SPAM DETECTION RULES (mark as spam if ANY of these apply):
1. Form submissions with gibberish/random text in fields (like "EdMdbjVoiclGswk", "ypAYYcUGutD")
2. Random character strings in names, addresses, or phone numbers
3. Suspicious patterns: mixed case random strings, nonsensical addresses
4. Bot-filled contact forms ("New Quote Request", "Contact Form Submission" with garbage data)
5. Obvious phishing, scams, or unsolicited commercial email
6. Emails with only random characters or test data

IMPORTANT EMAIL RULES (keep in inbox and possibly star):
- Personal emails from real humans
- Work-related or business communications
- Account security alerts, password resets
- Financial transactions, receipts for real purchases
- Travel confirmations, appointments
- Emails requiring action or response

DEFAULT ACTIONS:
- SPAM: mark_spam=true, mark_read=true, archive=false (Gmail handles spam folder)
- NEWSLETTERS/MARKETING: archive=true, mark_read=true
- IMPORTANT: keep in inbox, possibly star
- OTHER: archive=true unless it might need attention

Be aggressive about spam detection. If fields contain random characters or nonsensical data, it's spam."""

def classify_email_groq(client: Groq, payload: Dict[str, Any]) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": CLASSIFY_PROMPT_SYS},
        {"role": "user", "content": json.dumps(payload)}
    ]
    comp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    txt = comp.choices[0].message.content
    try:
        data = json.loads(txt)
    except Exception as e:
        print(f"Failed to parse LLM response: {e}")
        data = {
            "is_spam": False,
            "is_important": False,
            "confidence": 0.5,
            "reason": "Failed to classify",
            "actions": {
                "mark_spam": False,
                "star": False,
                "archive": False,
                "mark_read": False
            }
        }
    return data

def apply_actions(service, msg_id: str, decision: Dict[str, Any], label_ids: Dict[str, str]):
    add, rem = [], []

    # Handle spam
    if decision["actions"].get("mark_spam"):
        add.append("SPAM")
        rem.append("INBOX")  # Remove from inbox when marking as spam
        rem.append("UNREAD")  # Mark as read
    
    # Handle important emails
    if decision.get("is_important") and decision["actions"].get("star"):
        add.append("STARRED")
        add.append(label_ids["important"])  # Add AI/Important label
    
    # Handle archiving
    if decision["actions"].get("archive"):
        rem.append("INBOX")
    
    # Mark as read if specified
    if decision["actions"].get("mark_read"):
        rem.append("UNREAD")
    
    # Always mark as processed
    add.append(label_ids["processed"])

    # Apply changes
    body = {"addLabelIds": list(set(add)), "removeLabelIds": list(set(rem))}
    service.users().messages().modify(userId="me", id=msg_id, body=body).execute()

def main():
    service = gmail_client()
    # Simplified label system - only 2 custom labels
    label_ids = {
        "processed": ensure_label(service, INTERNAL_PROCESSED_LABEL),
        "important": ensure_label(service, AI_IMPORTANT_LABEL),
    }
    
    client = groq_client()
    ids = get_unprocessed_message_ids(service, label_ids["processed"])
    if not ids:
        print("No new messages to process.")
        return

    print(f"Processing {len(ids)} emails...")
    stats = {"spam": 0, "important": 0, "archived": 0, "kept": 0}
    
    for mid in ids:
        try:
            msg = fetch_message(service, mid)
            payload = summarize_for_llm(msg)
            decision = classify_email_groq(client, payload)
            apply_actions(service, mid, decision, label_ids)
            
            # Update statistics
            if decision["actions"].get("mark_spam"):
                stats["spam"] += 1
                status = "SPAM"
            elif decision.get("is_important"):
                stats["important"] += 1
                status = "IMPORTANT"
            elif decision["actions"].get("archive"):
                stats["archived"] += 1
                status = "ARCHIVED"
            else:
                stats["kept"] += 1
                status = "KEPT"
            
            print(f"OK {mid} -> {status} (confidence: {decision.get('confidence', 0):.1f}) - {decision.get('reason', '')}")
            time.sleep(0.2)  # gentle pacing
        except Exception as e:
            print(f"ERR {mid}: {e}")
    
    # Print summary
    print(f"\n=== Summary ===")
    print(f"Spam: {stats['spam']}, Important: {stats['important']}, Archived: {stats['archived']}, Kept in inbox: {stats['kept']}")

def run_health_server():
    """Run a simple HTTP server for health checks (required by Render Web Services)."""
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "healthy", "service": "gmail-groq-worker"}')
            else:
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<h1>Gmail Groq Worker</h1><p>Service is running. <a href="/health">Health Check</a></p>')
        
        def log_message(self, format, *args):
            # Suppress HTTP server logs to keep output clean
            pass
    
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"Health server running on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    import sys
    import threading
    
    # Check if we should run once or continuously
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        print("Running in continuous mode (every 10 minutes)...")
        
        # Start health server in background thread (for Render Web Service)
        if os.getenv("RENDER") or os.getenv("PORT"):
            health_thread = threading.Thread(target=run_health_server, daemon=True)
            health_thread.start()
            print("Health server started for cloud deployment")
        
        while True:
            try:
                main()
                print("Sleeping for 10 minutes...")
                time.sleep(600)  # 10 minutes
            except KeyboardInterrupt:
                print("\nStopping continuous mode...")
                break
            except Exception as e:
                print(f"Error in continuous mode: {e}")
                print("Sleeping for 10 minutes before retry...")
                time.sleep(600)
    else:
        main()
