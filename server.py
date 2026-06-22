
from requests.auth import HTTPDigestAuth
import urllib3
import time
import logging
from urllib.parse import quote

urllib3.disable_warnings()

# -----------------------------
# LOGGING
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("log/smk.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("smk")

# -----------------------------
# CDR CONFIG
# -----------------------------
CDR_URL = "https://192.168.1.10:8443/cdrapi?format=JSON"
CDR_USER = "xxxxx"
CDR_PASS = "xxxxx123"

# -----------------------------
# SMS CONFIG
# -----------------------------
SMS_URL = "https://sms.com/fa/publicapi/groupsms"
SMS_USER = "xxxxxxxxxx"
SMS_PASS = "xxxxxxxxxx"
SENDER = "xxxxxxxxx"

# -----------------------------
# MEMORY
# -----------------------------
seen = set()


# -----------------------------
# SEND SMS
# -----------------------------
def send_sms(to_number):
    message_text =" مشتری گرامی، با سپاس از تماس شما. مطابق درخواست ثبت‌شده، لینک لیست قیمت خدمات برای شما ارسال شد"
    message = quote(message_text)

    url = (
        f"{SMS_URL}"
        f"?username={SMS_USER}"
        f"&password={SMS_PASS}"
        f"&numbers={to_number}"
        f"&sendernumber={SENDER}"
        f"&message={message}"
    )

    try:
        r = requests.get(url, timeout=10)

#        logger.info(f"[SMS SENT TO] {to_number}")
#        logger.info(f"[SMS RESPONSE] {r.text}")

    except Exception as e:
        logger.error(f"[SMS ERROR] {e}")

# -----------------------------
# LOAD OLD CALLS
# -----------------------------
def init_seen():
    try:
        r = requests.get(
            CDR_URL,
            auth=HTTPDigestAuth(CDR_USER, CDR_PASS),
            verify=False,
            timeout=10
        )

        data = r.json()

        for call in data.get("cdr_root", []):

            main = call.get("main_cdr", {})

            src = str(main.get("src", ""))
            dst = str(main.get("dst", ""))
            start = str(main.get("start", ""))

            call_id = f"{src}-{dst}-{start}"

            seen.add(call_id)

#        logger.info(f"[INIT] Ignored old calls: {len(seen)}")

    except Exception as e:
        logger.error(f"[INIT ERROR] {e}")


# -----------------------------
# START
# -----------------------------
#logger.info("🚀 Service Started...")

init_seen()

# -----------------------------
# MAIN LOOP
# -----------------------------
while True:

    try:

        r = requests.get(
            CDR_URL,
            auth=HTTPDigestAuth(CDR_USER, CDR_PASS),
            verify=False,
            timeout=10
        )

        data = r.json()

        for call in data.get("cdr_root", []):

            main = call.get("main_cdr", {})

            src = str(main.get("src", ""))
            dst = str(main.get("dst", ""))
            start = str(main.get("start", ""))

            raw = str(call).lower()

           
            if "test" not in raw:
                continue

            call_id = f"{src}-{dst}-{start}"

        
            if call_id in seen:
                continue

            seen.add(call_id)

            logger.info(
                f"📞 SMK CALL DETECTED | FROM={src} | TO={dst} | TIME={start}"
            )

          
            send_sms(src)

        time.sleep(5)

    except Exception as e:

        logger.error(f"[ERROR] {e}")

        time.sleep(5)
