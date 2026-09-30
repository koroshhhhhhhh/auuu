"""Every text the bot sends lives here. Edit freely."""

# Confirmation
CONFIRM = "آیا از عملیات تبدیل فرمت اطمینان دارید؟ "
BTN_YES = "✓"
BTN_NO = "✕"
CANCELLED = "عملیات لغو شد ):"

# Progress
STAGE_DOWNLOAD = "در حال دریافت ویدیو"
STAGE_CONVERT = "در حال استخراج صدا"
STAGE_UPLOAD = "در حال ارسال فایل"
STAGE_DONE = "فایل ارسال شد"

BAR_FILLED = "▰"
BAR_EMPTY = "▱"
BAR_LENGTH = 5


def progress_text(stage: str, percent: int) -> str:
    filled = min(BAR_LENGTH, percent * BAR_LENGTH // 100)
    bar = BAR_FILLED * filled + BAR_EMPTY * (BAR_LENGTH - filled)
    return f"{stage}\n\n\u200e{bar} {percent}%"


# Limits and errors
COOLDOWN = "لطفاً {seconds} ثانیه دیگر صبر کنید و دوباره درخواست بدهید."
BUSY = "درخواست قبلی شما هنوز در حال انجام است."
NOT_YOURS = "این دکمه مخصوص کاربری است که درخواست داده است."
EXPIRED = "این درخواست منقضی شده یا قبلاً پردازش شده است. دوباره درخواست بدهید."
ERR_TOO_BIG = "حجم ویدیو بیشتر از ۲۰ مگابایت است و ربات نمی‌تواند آن را دریافت کند."
ERR_NO_AUDIO = "این ویدیو صدا ندارد."
ERR_OUTPUT_BIG = "حجم فایل صوتی خروجی بیشتر از ۵۰ مگابایت است و قابل ارسال نیست."
ERR_GENERIC = "مشکلی پیش آمد. لطفاً دوباره تلاش کنید."

# Help (/help, /start, /راهنما) - HTML, expandable quotes
HELP = """<b>راهنمای ربات</b>
تبدیل صدای ویدیو به فایل MP3

<b>نحوه کارکرد ربات</b>
<blockquote expandable><b>در پیوی</b>
ویدیو را برای ربات بفرستید.
ربات روی ویدیو ریپلای می‌زند و تأیید می‌گیرد.

<b>در گروه</b>
ربات به ویدیوها واکنشی نشان نمی‌دهد.
روی ویدیوی موردنظر ریپلای کنید و بنویسید mp3
سپس ربات تأیید می‌گیرد.</blockquote>

<b>نحوه دریافت MP3</b>
<blockquote expandable>۱. ویدیو را در پیوی بفرستید یا در گروه روی آن ریپلای کنید و mp3 بنویسید.
۲. در پیام تأیید، دکمه «بله» را بزنید. با دکمه «خیر» عملیات لغو می‌شود.
۳. پیشرفت کار با نوار درصد نمایش داده می‌شود.
۴. فایل MP3 برای شما ارسال می‌شود.

حداکثر حجم ویدیو ۲۰ مگابایت است.
بعد از هر درخواست باید چند ثانیه صبر کنید.</blockquote>"""
