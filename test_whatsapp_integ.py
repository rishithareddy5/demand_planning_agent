import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
TO_NUMBER = os.getenv("YOUR_WHATSAPP_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

message = client.messages.create(
    body="🚀 WhatsApp integration test successful!",
    from_=FROM_NUMBER,
    to=TO_NUMBER
)

print("Message SID:", message.sid)