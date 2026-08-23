#!/usr/bin/env python3

import os
import re
import sys
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

import jdatetime
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth
from urllib3.exceptions import InsecureRequestWarning
from zoneinfo import ZoneInfo


# =========================================================
# تنظیمات
# =========================================================

load_dotenv()

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

CDR_URL = os.getenv("CDR_URL", "").strip()
CDR_USER = os.getenv("CDR_USER", "").strip()
CDR_PASS = os.getenv("CDR_PASS", "").strip()

CDR_VERIFY_SSL = (
    os.getenv("CDR_VERIFY_SSL", "false").lower() == "true"
)

SMS_URL = os.getenv(
    "SMS_URL",
    "https://niksms.com/fa/publicapi/groupsms"
).strip()

SMS_USER = os.getenv("SMS_USER", "").strip()
SMS_PASS = os.getenv("SMS_PASS", "").strip()
SMS_SENDER = os.getenv("SMS_SENDER", "").strip()
SMS_RECIPIENT = os.getenv("SMS_RECIPIENT", "").strip()

SMS_VERIFY_SSL = (
    os.getenv("SMS_VERIFY_SSL", "true").lower() == "true"
)


# =========================================================
# تنظیمات شماره تلفن
# =========================================================

# اگر شماره ثابت 8 رقمی از CDR دریافت شود،
# به صورت پیش‌فرض مربوط به تهران در نظر گرفته می‌شود.
#
# مثال:

#
# اگر این شماره‌ها مربوط به شهر دیگری هستند،
# فقط این مقدار را تغییر دهید.
DEFAULT_LANDLINE_AREA_CODE = "21"


# =========================================================
# داخلی‌ها
# =========================================================

EXTENSIONS = {
    "market": {"300"},
    "factory": {"304", "306"},
    "shadabad": {"301", "302", "303", "310"},
    "smk": {"smk"},
}


SECTION_TITLES = {
    "market": "آهن مکان",
    "factory": "کارخانه",
    "shadabad": "شادآباد",
    "smk": "پیام به مشتری",
}


SECTION_EXTENSION_ORDER = {
    "market": ["300"],
    "shadabad": ["301", "302", "303", "310"],
    "factory": ["304", "306"],
    "smk": ["smk"],
}


ALL_EXTENSIONS = {
    "300",
    "301",
    "302",
    "303",
    "304",
    "306",
    "310",
    "smk",
}


RING_GROUP_TO_SECTION = {
    "6400": "market",
}


# =========================================================
# لاگ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            "call_report.log",
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger(__name__)


if not CDR_VERIFY_SSL:
    requests.packages.urllib3.disable_warnings(
        category=InsecureRequestWarning
    )


# =========================================================
# توابع عمومی
# =========================================================

def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


# =========================================================
# تشخیص مقادیر غیرمعتبر شماره تلفن
# =========================================================

INVALID_PHONE_VALUES = {
    "",
    "unknown",
    "unknow",
    "نامشخص",
    "anonymous",
    "unknown caller",
    "anonymous caller",
    "private",
    "blocked",
    "restricted",
    "unavailable",
    "none",
    "null",
    "nil",
    "n/a",
    "na",
    "-",
    "--",
    "caller",
    "callerid",
    "s",
}


def is_invalid_phone_value(value: Any) -> bool:
    """
    بررسی می‌کند مقدار دریافت‌شده اصلاً شبیه شماره تلفن هست یا خیر.
    """

    if value is None:
        return True

    text = normalize_text(value)

    if not text:
        return True

    if text.lower() in INVALID_PHONE_VALUES:
        return True

    return False


# =========================================================
# نرمال‌سازی شماره تلفن ایران
# =========================================================

def normalize_phone(number: str) -> str:
    """

    """

    if is_invalid_phone_value(number):
        return "نامشخص"

    # فقط اعداد
    digits = re.sub(
        r"\D",
        "",
        str(number),
    )

    if not digits:
        return "نامشخص"

    # -----------------------------------------------------
    # 0098xxxxxxxxxx
    # -----------------------------------------------------

    if (
        digits.startswith("0098")
        and len(digits) == 14
    ):
        digits = "0" + digits[4:]

    # -----------------------------------------------------
    # 98xxxxxxxxxx
    # -----------------------------------------------------

    elif (
        digits.startswith("98")
        and len(digits) == 12
    ):
        digits = "0" + digits[2:]

    # -----------------------------------------------------

    # -----------------------------------------------------

    elif (
        digits.startswith("9")
        and len(digits) == 10
    ):
        digits = "0" + digits

    # -----------------------------------------------------

    # -----------------------------------------------------

    elif (
        len(digits) == 10
        and digits[0] in "2345678"
    ):
        digits = "0" + digits

    # -----------------------------------------------------
    # شماره ثابت محلی 8 رقمی

    # -----------------------------------------------------

    elif len(digits) == 8:
        digits = (
            "0"
            + DEFAULT_LANDLINE_AREA_CODE
            + digits
        )

    return digits


# =========================================================
# اعتبارسنجی شماره ایران
# =========================================================
def is_valid_iran_phone(number: str) -> bool:
    """

    شماره ثابت کامل ایران:
        0 + کد منطقه 2 رقمی + 8 رقم
        = 11 رقم
    """

    if not number:
        return False

    digits = re.sub(
        r"\D",
        "",
        str(number),
    )

    # ---------------------------------------------
    # موبایل
    # 09 + 9 رقم
    # مجموعاً 11 رقم
    # ---------------------------------------------

    if re.fullmatch(
        r"09\d{9}",
        digits,
    ):
        return True

    # ---------------------------------------------
    # شماره ثابت ایران
    #
    # 0 + کد منطقه + 8 رقم
    #
    # مثال:
    # 02133937029
    # 03155312352
    #
    # مجموعاً 11 رقم
    # ---------------------------------------------

    if re.fullmatch(
        r"0[2-8]\d{9}",
        digits,
    ):
        return True

    return False
    # -----------------------------------------------------
    # موبایل
    # -----------------------------------------------------

    if re.fullmatch(
        r"09\d{9}",
        digits,
    ):
        return True

    # -----------------------------------------------------
    # ثابت
    # -----------------------------------------------------

    if re.fullmatch(
        r"0[2-8]\d{8}",
        digits,
    ):
        return True

    return False


# =========================================================
# بررسی اینکه مقدار یک شماره معتبر ایران است
# =========================================================

def normalize_and_validate_phone(value: Any) -> str:
    """
    مقدار خام را نرمال و سپس اعتبارسنجی می‌کند.

    اگر شماره معتبر نباشد:
        "نامشخص"
    """

    if is_invalid_phone_value(value):
        return "نامشخص"

    normalized = normalize_phone(
        normalize_text(value)
    )

    if not normalized:
        return "نامشخص"

    if normalized == "نامشخص":
        return "نامشخص"

    if not is_valid_iran_phone(normalized):
        return "نامشخص"

    return normalized


# =========================================================
# گرفتن گیرنده‌های SMS
# =========================================================

def get_sms_recipients() -> list[str]:
    """
    امکان استفاده از چند گیرنده:

    SMS_RECIPIENT=09123456789

    یا:

    SMS_RECIPIENT=09123456789,09351234567

    یا:

    SMS_RECIPIENT=09123456789;09351234567
    """

    if not SMS_RECIPIENT:
        return []

    raw_numbers = re.split(
        r"[,;\s]+",
        SMS_RECIPIENT,
    )

    recipients = []

    for raw_number in raw_numbers:

        raw_number = raw_number.strip()

        if not raw_number:
            continue

        normalized = normalize_phone(
            raw_number
        )

        if not is_valid_iran_phone(normalized):
            raise ValueError(
                "شماره گیرنده SMS نامعتبر است: "
                f"{raw_number!r} -> "
                f"{normalized!r}"
            )

        if normalized not in recipients:
            recipients.append(normalized)

    return recipients


# =========================================================
# اعتبارسنجی تنظیمات
# =========================================================

def validate_config() -> None:

    required = {
        "CDR_URL": CDR_URL,
        "CDR_USER": CDR_USER,
        "CDR_PASS": CDR_PASS,
        "SMS_URL": SMS_URL,
        "SMS_USER": SMS_USER,
        "SMS_PASS": SMS_PASS,
        "SMS_SENDER": SMS_SENDER,
        "SMS_RECIPIENT": SMS_RECIPIENT,
    }

    missing = [
        name
        for name, value in required.items()
        if not value
    ]

    if missing:
        raise ValueError(
            "تنظیمات زیر در فایل .env وارد نشده‌اند: "
            + ", ".join(missing)
        )

    recipients = get_sms_recipients()

    if not recipients:
        raise ValueError(
            "هیچ شماره گیرنده معتبری برای "
            "SMS_RECIPIENT پیدا نشد."
        )

    logger.info(
        "گیرنده‌های SMS: %s",
        ", ".join(recipients),
    )


# =========================================================
# تاریخ
# =========================================================

def get_today() -> datetime:
    return datetime.now(TEHRAN_TZ)


def gregorian_date_string(
    now: datetime,
) -> str:

    return now.strftime("%Y-%m-%d")


def jalali_date_string(
    now: datetime,
) -> str:

    jalali = jdatetime.date.fromgregorian(
        date=now.date()
    )

    return jalali.strftime("%Y/%m/%d")


# =========================================================
# دریافت CDR
# =========================================================

def fetch_cdr_data(
    now: datetime,
) -> Any:

    date_value = gregorian_date_string(now)

    logger.info(
        "در حال دریافت CDR تاریخ %s",
        date_value,
    )

    response = requests.get(
        CDR_URL,
        auth=HTTPDigestAuth(
            CDR_USER,
            CDR_PASS,
        ),
        timeout=90,
        verify=CDR_VERIFY_SSL,
    )

    response.raise_for_status()

    try:
        return response.json()

    except ValueError as exc:

        logger.error(
            "پاسخ CDR از نوع JSON معتبر نیست: %s",
            response.text[:500],
        )

        raise RuntimeError(
            "پاسخ CDR معتبر نیست."
        ) from exc


# =========================================================
# پیدا کردن آیتم‌های CDR
# =========================================================

def find_call_items(
    payload: Any,
) -> list[dict]:

    if isinstance(payload, list):

        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    if not isinstance(payload, dict):
        return []

    for key in (
        "cdr_root",
        "data",
        "result",
        "records",
        "cdrs",
        "items",
    ):

        value = payload.get(key)

        if isinstance(value, list):

            return [
                item
                for item in value
                if isinstance(item, dict)
            ]

        if isinstance(value, dict):

            nested = find_call_items(value)

            if nested:
                return nested

    if (
        "main_cdr" in payload
        or "sub_cdr_1" in payload
        or "AcctId" in payload
        or "session" in payload
    ):
        return [payload]

    return []


# =========================================================
# استخراج رکوردها
# =========================================================

def extract_records(
    call_item: dict,
) -> list[dict]:

    records = []

    if isinstance(
        call_item.get("main_cdr"),
        dict,
    ):

        records.append(
            call_item["main_cdr"]
        )

    sub_keys = sorted(
        [
            key
            for key in call_item.keys()
            if (
                key.startswith("sub_cdr_")
                and isinstance(
                    call_item.get(key),
                    dict,
                )
            )
        ],
        key=lambda key: safe_int(
            key.rsplit("_", 1)[-1]
        ),
    )

    for key in sub_keys:
        records.append(
            call_item[key]
        )

    if not records and any(
        key in call_item
        for key in (
            "AcctId",
            "src",
            "dst",
            "start",
            "disposition",
        )
    ):
        records.append(call_item)

    return records


# =========================================================
# بررسی تاریخ رکورد
# =========================================================

def record_is_for_date(
    record: dict,
    date_value: str,
) -> bool:

    start = normalize_text(
        record.get("start")
    )

    if not start:
        return False

    return start.startswith(date_value)


# =========================================================
# تشخیص تماس ورودی
# =========================================================

def is_inbound(
    records: list[dict],
) -> bool:

    for record in records:

        userfield = normalize_text(
            record.get("userfield")
        ).lower()

        channel_ext = normalize_text(
            record.get("channel_ext")
        ).lower()

        channel = normalize_text(
            record.get("channel")
        ).lower()

        if userfield == "inbound":
            return True

        if channel_ext.startswith("trunk"):
            return True

        if "/trunk" in channel:
            return True

    return False


# =========================================================
# Session ID
# =========================================================

def get_session_id(
    call_item: dict,
    records: list[dict],
    index: int,
) -> str:

    candidates = [
        call_item.get("cdr"),
        call_item.get("session"),
    ]

    for record in records:

        candidates.extend(
            [
                record.get("session"),
                record.get("uniqueid"),
            ]
        )

    for candidate in candidates:

        value = normalize_text(candidate)

        if value:
            return value

    return f"unknown-call-{index}"


# =========================================================
# Destination values
# =========================================================

def destination_values(
    record: dict,
) -> set[str]:

    values = {
        normalize_text(
            record.get("dst")
        ).lower(),

        normalize_text(
            record.get("dstanswer")
        ).lower(),

        normalize_text(
            record.get("dstchannel_ext")
        ).lower(),

        normalize_text(
            record.get("chanext")
        ).lower(),

        normalize_text(
            record.get("dstchanext")
        ).lower(),
    }

    return {
        value
        for value in values
        if value
    }


# =========================================================
# تشخیص تماس پاسخ داده شده
# =========================================================

def record_is_answered(
    record: dict,
) -> bool:

    disposition = normalize_text(
        record.get("disposition")
    ).upper()

    answer = normalize_text(
        record.get("answer")
    )

    billsec = safe_int(
        record.get("billsec")
    )

    return (
        disposition == "ANSWERED"
        and (
            bool(answer)
            or billsec > 0
        )
    )


# =========================================================
# داخلی‌هایی که تماس روی آنها رفته
# =========================================================

def get_attempted_extensions(
    records: list[dict],
) -> set[str]:

    attempted = set()

    for record in records:

        destinations = destination_values(
            record
        )

        attempted.update(
            destinations.intersection(
                ALL_EXTENSIONS
            )
        )

    return attempted


# =========================================================
# داخلی‌هایی که پاسخ داده‌اند
# =========================================================

def get_answered_extensions(
    records: list[dict],
) -> set[str]:

    answered = set()

    for record in records:

        if not record_is_answered(record):
            continue

        destinations = destination_values(
            record
        )

        answered.update(
            destinations.intersection(
                ALL_EXTENSIONS
            )
        )

    return answered


# =========================================================
# Ring Group
# =========================================================

def get_sections_from_ring_groups(
    records: list[dict],
) -> set[str]:

    sections = set()

    for record in records:

        values = destination_values(
            record
        )

        action_type = normalize_text(
            record.get("action_type")
        ).upper()

        for (
            ring_group,
            section,
        ) in RING_GROUP_TO_SECTION.items():

            if (
                ring_group in values
                or f"RINGGROUP[{ring_group}]"
                in action_type
            ):
                sections.add(section)

    return sections


# =========================================================
# بخش‌هایی که تماس روی آنها بوده
# =========================================================

def get_attempted_sections(
    records: list[dict],
    attempted_extensions: set[str],
) -> set[str]:

    sections = (
        get_sections_from_ring_groups(
            records
        )
    )

    if "300" in attempted_extensions:
        sections.add("market")

    if attempted_extensions.intersection(
        {
            "301",
            "302",
            "303",
            "310",
        }
    ):
        sections.add("shadabad")

    if attempted_extensions.intersection(
        {
            "304",
            "306",
        }
    ):
        sections.add("factory")

    if "smk" in attempted_extensions:
        sections.add("smk")

    return sections


# =========================================================
# گرفتن شماره تماس‌گیرنده
# =========================================================

def get_caller_number(
    records: list[dict],
) -> str:
    """
    شماره تماس‌گیرنده را از CDR پیدا می‌کند.

    ترتیب بررسی:

        src
        callerid
        clid
        cid_num


    candidates = []

    for record in records:

        candidates.extend(
            [
                record.get("src"),
                record.get("callerid"),
                record.get("clid"),
                record.get("cid_num"),
            ]
        )

    for candidate in candidates:

        if is_invalid_phone_value(candidate):
            continue

        normalized = normalize_and_validate_phone(
            candidate
        )

        if normalized == "نامشخص":
            continue

        # -------------------------------------------------
        #         # -------------------------------------------------

        if normalized in ALL_EXTENSIONS:
            continue

        return normalized

    return "نامشخص"


# =========================================================
# محاسبه گزارش
# =========================================================

def calculate_report(
    payload: Any,
    now: datetime,
) -> dict:

    call_items = find_call_items(payload)

    target_date = gregorian_date_string(now)

    result = {
        # تعداد تماس‌های پاسخ داده شده
        "answered": defaultdict(int),

        # تماس‌های بی‌پاسخ
        "missed_numbers": {
            section: defaultdict(list)
            for section in EXTENSIONS
        },

        "missed_count": defaultdict(int),

        # شماره تماس‌گیرنده‌های smk
        "smk_numbers": [],

        "total_inbound": 0,

        "processed_sessions": 0,
    }

    seen_sessions = set()

    for index, call_item in enumerate(
        call_items
    ):

        records = extract_records(
            call_item
        )

        today_records = [
            record
            for record in records
            if record_is_for_date(
                record,
                target_date,
            )
        ]

        if not today_records:
            continue

        if not is_inbound(today_records):
            continue

        session_id = get_session_id(
            call_item,
            today_records,
            index,
        )

        if session_id in seen_sessions:
            continue

        seen_sessions.add(session_id)

        result["processed_sessions"] += 1

        result["total_inbound"] += 1

        attempted_extensions = (
            get_attempted_extensions(
                today_records
            )
        )

        answered_extensions = (
            get_answered_extensions(
                today_records
            )
        )

        # -------------------------------------------------
        #
        # -------------------------------------------------

        for extension in answered_extensions:

            result["answered"][
                extension
            ] += 1

        # -------------------------------------------------
        # بخش‌های تماس
        # -------------------------------------------------

        attempted_sections = (
            get_attempted_sections(
                today_records,
                attempted_extensions,
            )
        )

        # -------------------------------------------------
        # شماره تماس‌گیرنده
        # -------------------------------------------------

        caller_number = get_caller_number(
            today_records
        )

        # -------------------------------------------------

        # -------------------------------------------------

        if (
            "smk" in answered_extensions
            and caller_number != "نامشخص"
        ):

            result[
                "smk_numbers"
            ].append(caller_number)

        # -------------------------------------------------
        # تماس‌های بی‌پاسخ
        # -------------------------------------------------

        for section in attempted_sections:

            section_extensions = (
                EXTENSIONS[section]
            )

            # اگر تماس در یکی از داخلی‌های
            # همان بخش پاسخ داده نشده باشد

            if not answered_extensions.intersection(
                section_extensions
            ):

                result[
                    "missed_count"
                ][section] += 1

                # -------------------------------------------------
                
             # -------------------------------------------------

                if section == "shadabad":

                    if caller_number != "نامشخص":

                        result[
                            "missed_numbers"
                        ][
                            "shadabad"
                        ][
                            "303"
                        ].append(
                            caller_number
                        )

                else:

                    extensions_tried = (
                        attempted_extensions.intersection(
                            section_extensions
                        )
                    )

                    if extensions_tried:

                        for ext in extensions_tried:

                            if (
                                caller_number
                                != "نامشخص"
                            ):

                                result[
                                    "missed_numbers"
                                ][
                                    section
                                ][
                                    ext
                                ].append(
                                    caller_number
                                )

                    else:

                        default_ext = (
                            SECTION_EXTENSION_ORDER[
                                section
                            ][0]
                        )

                        if (
                            caller_number
                            != "نامشخص"
                        ):

                            result[
                                "missed_numbers"
                            ][
                                section
                            ][
                                default_ext
                            ].append(
                                caller_number
                            )

    return result


# =========================================================
# ساخت بخش تماس‌های بی‌پاسخ
# =========================================================

def format_missed_section(
    section: str,
    report: dict,
) -> str:

    missed_count = (
        report[
            "missed_count"
        ].get(
            section,
            0,
        )
    )

    title = SECTION_TITLES[
        section
    ]

    lines = [
        f"{title}: {missed_count}"
    ]

    if missed_count == 0:
        return "\n".join(lines)

    extensions = (
        SECTION_EXTENSION_ORDER[
            section
        ]
    )

    numbers_by_ext = (
        report[
            "missed_numbers"
        ][section]
    )

    only_one_extension = (
        len(extensions) == 1
    )

    for ext in extensions:

        numbers = (
            numbers_by_ext.get(
                ext,
                [],
            )
        )

        if not numbers:
            continue

        if not only_one_extension:

            lines.append(
                f"{ext}:"
            )

        for i, number in enumerate(
            numbers,
            start=1,
        ):

            lines.append(
                f"{i})"
            )

            lines.append(
                number
            )

            lines.append("")

    return "\n".join(
        lines
    ).rstrip()


# =========================================================
# ساخت متن گزارش
# =========================================================

def build_report_message(
    report: dict,
    now: datetime,
) -> str:

    answered = report[
        "answered"
    ]

    message_lines = [
        "📞 گزارش تماس‌های ورودی",
        "",
        f"آهن مکان (300): "
        f"{answered.get('300', 0)}",
        "",
        "شادآباد",
        f"301: "
        f"{answered.get('301', 0)}",
        f"302: "
        f"{answered.get('302', 0)}",
        f"303: "
        f"{answered.get('303', 0)}",
        f"310: "
        f"{answered.get('310', 0)}",
        "",
        "کارخانه",
        f"304: "
        f"{answered.get('304', 0)}",
        f"306: "
        f"{answered.get('306', 0)}",
        "",
        f"پیام به مشتری (smk): "
        f"{answered.get('smk', 0)}",
        "",
    ]

    # =====================================================
    # شماره‌های پیام به مشتری (smk)
    # =====================================================

    smk_numbers = report.get(
        "smk_numbers",
        [],
    )

    for i, number in enumerate(
        smk_numbers,
        start=1,
    ):

        message_lines.append(
            f"{i})"
        )

        message_lines.append(
            number
        )

        message_lines.append("")

    # =====================================================
    # تماس‌های بی‌پاسخ
    # =====================================================

    message_lines.extend(
        [
            "تماس‌های بی‌پاسخ:",
            "",
            format_missed_section(
                "market",
                report,
            ),
            "",
            format_missed_section(
                "shadabad",
                report,
            ),
            "",
            format_missed_section(
                "factory",
                report,
            ),
            "",
            f"کل تماس‌های ورودی: "
            f"{report['total_inbound']}",
            "",
            f"تاریخ: "
            f"{jalali_date_string(now)}",
        ]
    )

    return "\n".join(
        message_lines
    )


# =========================================================
# ارسال پیامک
# =========================================================

def send_sms(
    message: str,
) -> str:

    recipients = get_sms_recipients()

    numbers = ",".join(
        recipients
    )

    payload = {
        "username": SMS_USER,
        "password": SMS_PASS,
        "numbers": numbers,
        "sendernumber": SMS_SENDER,
        "message": message,
    }

    logger.info(
        "در حال ارسال پیامک به: %s",
        numbers,
    )

    response = requests.post(
        SMS_URL,
        data=payload,
        timeout=60,
        verify=SMS_VERIFY_SSL,
    )

    response.raise_for_status()

    response_text = (
        response.text.strip()
    )

    if not response_text:

        raise RuntimeError(
            "پاسخ خالی از سرویس پیامک دریافت شد."
        )

    logger.info(
        "پاسخ سرویس پیامک: %s",
        response_text[:500],
    )

    return response_text


# =========================================================
# اجرای گزارش
# =========================================================

def create_and_send_daily_report(
    send: bool = True,
) -> str:

    now = get_today()

    logger.info(
        "شروع ساخت گزارش روزانه"
    )

    payload = fetch_cdr_data(
        now
    )

    report = calculate_report(
        payload,
        now,
    )

    message = build_report_message(
        report,
        now,
    )

    logger.info(
        "متن گزارش:\n%s",
        message,
    )

    if send:

        send_sms(message)

        logger.info(
            "گزارش با موفقیت ارسال شد."
        )

    else:

        logger.info(
            "حالت آزمایشی: پیامک ارسال نشد."
        )

    return message


# =========================================================
# اجرای امن Job
# =========================================================

def safe_daily_job() -> None:

    try:

        validate_config()

        create_and_send_daily_report(
            send=True
        )

    except Exception:

        logger.exception(
            "ساخت یا ارسال گزارش با خطا مواجه شد."
        )


# =========================================================
# Scheduler
# =========================================================

def start_scheduler() -> None:

    validate_config()

    scheduler = BlockingScheduler(
        timezone=TEHRAN_TZ
    )

    scheduler.add_job(
        safe_daily_job,
        trigger="cron",
        hour=19,
        minute=0,
        second=0,
        id="daily_call_report",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )

    logger.info(
        "برنامه فعال شد؛ "
        "گزارش هر روز ساعت 19:00 ارسال می‌شود."
    )

    try:

        scheduler.start()

    except (
        KeyboardInterrupt,
        SystemExit,
    ):

        logger.info(
            "برنامه متوقف شد."
        )


# =========================================================
# ورودی برنامه
# =========================================================

if __name__ == "__main__":

    command = (
        sys.argv[1].lower()
        if len(sys.argv) > 1
        else "schedule"
    )

    if command == "test":

        validate_config()

        print(
            create_and_send_daily_report(
                send=False
            )
        )

    elif command == "now":

        validate_config()

        create_and_send_daily_report(
            send=True
        )

    elif command == "schedule":

        start_scheduler()

    else:

        print(
            "دستور نامعتبر است.\n"
            "دستورات قابل استفاده:\n"
            " python call_report.py test\n"
            " python call_report.py now\n"
            " python call_report.py schedule"
        )

        sys.exit(1)
