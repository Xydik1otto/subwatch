# Cancel assistant: static knowledge base for the top-20 subscription
# services. Each entry carries the official cancellation page URL and
# step-by-step instructions in Ukrainian and English.
# No network calls, no scraping — pure static data, updated with releases.
from __future__ import annotations

import re
from typing import Any

# id -> {name, url, keywords, steps_uk, steps_en}
SERVICES: dict[str, dict[str, Any]] = {
    "netflix": {
        "name": "Netflix",
        "url": "https://www.netflix.com/cancelplan",
        "keywords": ["netflix"],
        "steps_uk": [
            "Увійдіть на netflix.com і відкрийте свій профіль.",
            "Розділ «Акаунт» → «Членство та оплати» → «Скасувати план».",
            "Підтвердьте скасування. Доступ зберігається до кінця оплаченого періоду.",
            "Перевірте email від Netflix — підтвердження скасування.",
        ],
        "steps_en": [
            "Sign in at netflix.com and open your profile.",
            "Account → Membership & Billing → Cancel plan.",
            "Confirm. Access stays until the end of the paid period.",
            "Check your email for the cancellation confirmation.",
        ],
    },
    "spotify": {
        "name": "Spotify",
        "url": "https://www.spotify.com/account/subscription/",
        "keywords": ["spotify"],
        "steps_uk": [
            "Увійдіть на spotify.com → ваш акаунт → «Підписка».",
            "Прокрутіть до «Змінити або скасувати» → «Скасувати преміум».",
            "Пройдіть екран утримання («Залишитися» — пропустіть) і підтвердьте.",
            "Акаунт повернеться у безкоштовний режим після поточного періоду.",
        ],
        "steps_en": [
            "Sign in at spotify.com → your account → Subscription.",
            "Scroll to 'Change or cancel' → Cancel Premium.",
            "Click through the retention screen ('stay' offers) and confirm.",
            "The account returns to free mode after the current period.",
        ],
    },
    "youtube-premium": {
        "name": "YouTube Premium",
        "url": "https://www.youtube.com/paid_memberships",
        "keywords": ["youtube premium", "youtube premium", "youtube red", "ytmusic", "youtube music"],
        "steps_uk": [
            "Відкрийте youtube.com → аватар → «Платні підписки».",
            "Знайдіть YouTube Premium → «Керувати підпискою».",
            "«Скасувати» → підтвердьте (майте на увазі вікно з вигодами залишитися).",
            "Дослідіть пільги зберігаються до кінця оплаченого циклу.",
        ],
        "steps_en": [
            "Open youtube.com → profile avatar → Paid memberships.",
            "Find YouTube Premium → Manage subscription.",
            "Click Cancel and confirm (ignore the retention offers).",
            "Benefits remain until the end of the paid cycle.",
        ],
    },
    "disneyplus": {
        "name": "Disney+",
        "url": "https://www.disneyplus.com/account/subscription",
        "keywords": ["disney", "disney+", "disney plus"],
        "steps_uk": [
            "Увійдіть на disneyplus.com → іконка профілю → «Акаунт».",
            "«Підписка» → «Скасувати підписку».",
            "Підтвердьте — сторінка покаже дату кінця доступу.",
            "Якщо платите через App Store/Google Play — скасовуйте там.",
        ],
        "steps_en": [
            "Sign in at disneyplus.com → profile icon → Account.",
            "Subscription → Cancel subscription.",
            "Confirm — the page shows when access ends.",
            "If you pay via App Store/Google Play, cancel there instead.",
        ],
    },
    "max": {
        "name": "Max (HBO Max)",
        "url": "https://play.max.com/account",
        "keywords": ["hbo", "hbo max", "max"],
        "steps_uk": [
            "Увійдіть на play.max.com → профіль → «Акаунт».",
            "Розділ «Підписка» → «Керувати підпискою» → «Скасувати».",
            "Підтвердьте скасування; доступ активний до кінця циклу.",
            "Білінг через третю сторону (провайдер, App Store)? Скасуйте через них.",
        ],
        "steps_en": [
            "Sign in at play.max.com → profile → Account.",
            "Subscription section → Manage subscription → Cancel.",
            "Confirm; access runs until the end of the cycle.",
            "If billed via a third party (provider, App Store), cancel with them.",
        ],
    },
    "amazon-prime": {
        "name": "Amazon Prime",
        "url": "https://www.amazon.com/gp/primecentral",
        "keywords": ["amazon prime", "prime video", "amazon"],
        "steps_uk": [
            "Відкрийте amazon.com → «Акаунт» → Prime (Prime Central).",
            "«Керувати членством» → «Завершити членство».",
            "Amazon покаже переваги та нагадає про залишок — оберіть «Продовжити скасування».",
            "Підтвердьте: повернення грошей можливе, якщо не користувалися перевагами.",
        ],
        "steps_en": [
            "Open amazon.com → Account → Prime (Prime Central).",
            "Manage membership → End membership.",
            "Amazon shows perks and remaining days — choose 'Continue to cancel'.",
            "Confirm; a refund may apply if you have not used benefits.",
        ],
    },
    "apple": {
        "name": "Apple (iCloud+, App Store)",
        "url": "https://apps.apple.com/account/subscriptions",
        "keywords": ["icloud", "apple", "app store", "apple music", "apple tv", "apple one"],
        "steps_uk": [
            "iPhone/iPad: Налаштування → [ваше ім'я] → Підписки.",
            "Mac: App Store → обліковий запис → Підписки.",
            "Оберіть підписку → «Скасувати підписку» (або «Скасувати план»).",
            "Веб: apps.apple.com/account/subscriptions, увійдіть Apple ID.",
        ],
        "steps_en": [
            "iPhone/iPad: Settings → [your name] → Subscriptions.",
            "Mac: App Store → account → Subscriptions.",
            "Pick the subscription → Cancel Subscription (or Cancel Plan).",
            "Web: apps.apple.com/account/subscriptions, sign in with Apple ID.",
        ],
    },
    "google-play": {
        "name": "Google Play subscriptions",
        "url": "https://play.google.com/store/account/subscriptions",
        "keywords": ["google play", "google one", "youtube music", "play pass"],
        "steps_uk": [
            "Відкрийте play.google.com/store/account/subscriptions.",
            "Оберіть підписку → «Керувати» → «Скасувати підписку».",
            "Вкажіть причину (опційно) і підтвердьте.",
            "У застосунку Play Store: Профіль → Платежі та підписки → Підписки.",
        ],
        "steps_en": [
            "Open play.google.com/store/account/subscriptions.",
            "Select the subscription → Manage → Cancel subscription.",
            "Optionally pick a reason and confirm.",
            "In the Play Store app: Profile → Payments & subscriptions → Subscriptions.",
        ],
    },
    "xbox-game-pass": {
        "name": "Xbox Game Pass",
        "url": "https://account.microsoft.com/services",
        "keywords": ["xbox", "game pass", "gamepass", "xbox live", "game pass ultimate"],
        "steps_uk": [
            "Увійдіть на account.microsoft.com/services.",
            "Знайдіть Game Pass / Xbox → «Керувати».",
            "Вимкніть «Автоматичне поновлення» (Turn off recurring billing).",
            "Передоплата діє до кінця періоду; повторне списання не відбудеться.",
        ],
        "steps_en": [
            "Sign in at account.microsoft.com/services.",
            "Find Game Pass / Xbox → Manage.",
            "Turn off recurring billing.",
            "Prepaid time remains until period end; no further charge.",
        ],
    },
    "playstation-plus": {
        "name": "PlayStation Plus",
        "url": "https://www.playstation.com/subscriptions/",
        "keywords": ["playstation", "ps plus", "psn", "playstation plus", "ps plus"],
        "steps_uk": [
            "На консолі: Налаштування → Керування акаунтом → Інформація про акаунт.",
            "«Підписки» (PlayStation Subscriptions) → оберіть PS Plus.",
            "Вимкніть «Автоматичне поновлення фінансування».",
            "Веб: playstation.com/subscriptions → увійдіть → скасуйте поновлення.",
        ],
        "steps_en": [
            "On console: Settings → Account Management → Account Information.",
            "Subscriptions → choose PS Plus.",
            "Turn off 'Renew Automatically'.",
            "Web: playstation.com/subscriptions → sign in → cancel renewal.",
        ],
    },
    "adobe": {
        "name": "Adobe Creative Cloud",
        "url": "https://account.adobe.com/plans",
        "keywords": ["adobe", "creative cloud", "photoshop", "lightroom"],
        "steps_uk": [
            "Увійдіть на account.adobe.com/plans.",
            "«Керувати планом» → «Скасувати план».",
            "Якщо в межах 14 днів від покупки — повне повернення коштів.",
            "Пізніше можливий збір за дострокове скасування річного плану (50% залишку).",
        ],
        "steps_en": [
            "Sign in at account.adobe.com/plans.",
            "Manage plan → Cancel plan.",
            "Within 14 days of purchase you get a full refund.",
            "Later, an early-termination fee may apply (50% of remaining annual plan).",
        ],
    },
    "microsoft-365": {
        "name": "Microsoft 365",
        "url": "https://account.microsoft.com/services",
        "keywords": ["microsoft 365", "office 365", "microsoft365", "onedrive", "office"],
        "steps_uk": [
            "Увійдіть на account.microsoft.com/services.",
            "Знайдіть Microsoft 365 → «Керувати».",
            "«Скасувати підписку» або вимкніть повторне виставлення рахунків.",
            "Залежно від тривалості активної передоплати можливе повернення коштів.",
        ],
        "steps_en": [
            "Sign in at account.microsoft.com/services.",
            "Find Microsoft 365 → Manage.",
            "Cancel subscription or turn off recurring billing.",
            "Depending on remaining prepaid time, a refund may be available.",
        ],
    },
    "dropbox": {
        "name": "Dropbox",
        "url": "https://www.dropbox.com/account/plan",
        "keywords": ["dropbox"],
        "steps_uk": [
            "Увійдіть на dropbox.com → аватар → «Налаштування» → «План».",
            "«Керувати підпискою» → «Скасувати план».",
            "Пройдіть опитування-утримання та підтвердьте скасування.",
            "План не поновиться; файлы залишаться доступними для читання.",
        ],
        "steps_en": [
            "Sign in at dropbox.com → avatar → Settings → Plan.",
            "Manage subscription → Cancel plan.",
            "Answer the retention survey and confirm.",
            "The plan will not renew; files stay available in read-only mode.",
        ],
    },
    "twitch": {
        "name": "Twitch",
        "url": "https://www.twitch.tv/subscriptions",
        "keywords": ["twitch"],
        "steps_uk": [
            "Увійдіть на twitch.tv/subscriptions.",
            "Оберіть канал з активною підпискою → «Скасувати підписку».",
            "Підтвердьте; переваги діють до кінця оплаченого місяця.",
            "Автоматичне поновлення через Amazon Prime — скасуйте у Prime Central.",
        ],
        "steps_en": [
            "Sign in at twitch.tv/subscriptions.",
            "Pick the channel with an active sub → Cancel subscription.",
            "Confirm; perks last until the paid month ends.",
            "For Prime subscriptions, cancel in Amazon Prime Central.",
        ],
    },
    "canva": {
        "name": "Canva",
        "url": "https://www.canva.com/settings/billing-and-plans",
        "keywords": ["canva"],
        "steps_uk": [
            "Увійдіть на canva.com → Налаштування → «Білінг і плани».",
            "Для Canva Pro: «Плани та ціни» → «Скасувати Pro».",
            "Підтвердьте скасування на наступному екрані.",
            "Ваші дизайн-макети залишаться у безкоштовному акаунті.",
        ],
        "steps_en": [
            "Sign in at canva.com → Settings → Billing & plans.",
            "For Canva Pro: Plans & pricing → Cancel Pro.",
            "Confirm the cancellation on the next screen.",
            "Your designs stay in the free account.",
        ],
    },
    "figma": {
        "name": "Figma",
        "url": "https://www.figma.com/settings",
        "keywords": ["figma"],
        "steps_uk": [
            "Увійдіть на figma.com → аватар → «Налаштування».",
            "Вкладка «Білінг» → поточний план → «Скасувати план».",
            "Скасування наприкінці циклу; ви можете вибирати «Завершити зараз».",
            "Понизьте до Starter безкоштовно — файли залишаться.",
        ],
        "steps_en": [
            "Sign in at figma.com → avatar → Settings.",
            "Billing tab → current plan → Cancel plan.",
            "Cancellation applies at cycle end; you may choose to end now.",
            "Downgrade to the free Starter plan — files remain.",
        ],
    },
    "chatgpt-plus": {
        "name": "ChatGPT Plus",
        "url": "https://chatgpt.com/#settings/General",
        "keywords": ["chatgpt", "openai", "gpt plus"],
        "steps_uk": [
            "Увійдіть на chatgpt.com → ім'я профілю → «Мій план» / Налаштування.",
            "«Мій план» → «Керувати моєю підпискою» → «Скасувати план».",
            "Підтвердьте; доступ до Plus діє до кінця оплаченого періоду.",
            "Альтернатива: help.openai.com → керування підпискою.",
        ],
        "steps_en": [
            "Sign in at chatgpt.com → profile name → My plan / Settings.",
            "My plan → Manage my subscription → Cancel plan.",
            "Confirm; Plus access stays until the paid period ends.",
            "Alternative: help.openai.com → manage subscription.",
        ],
    },
    "duolingo-super": {
        "name": "Duolingo Super",
        "url": "https://www.duolingo.com/settings/super",
        "keywords": ["duolingo", "duolingo super", "duolingo plus"],
        "steps_uk": [
            "Увійдіть на duolingo.com → «Ще» → «Магазин» / «Super».",
            "Веб: duolingo.com/settings/super → «Керувати підпискою».",
            "«Скасувати підписку» і підтвердьте.",
            "Через App Store/Google Play — скасуйте у відповідному магазині.",
        ],
        "steps_en": [
            "Sign in at duolingo.com → More → Shop / Super.",
            "Web: duolingo.com/settings/super → Manage subscription.",
            "Cancel subscription and confirm.",
            "Via App Store/Google Play — cancel in the respective store.",
        ],
    },
    "audible": {
        "name": "Audible",
        "url": "https://www.audible.com/account/membership",
        "keywords": ["audible"],
        "steps_uk": [
            "Увійдіть на audible.com → «Акаунт» → «Деталі членства».",
            "«Скасувати членство» внизу сторінки.",
            "Пройдіть екран утримання (кредити залишаються 1 рік) і підтвердьте.",
            "Викуплені книги залишаються вашими назавжди.",
        ],
        "steps_en": [
            "Sign in at audible.com → Account → Membership details.",
            "Cancel membership at the bottom of the page.",
            "Click through the retention screen (credits last 1 year) and confirm.",
            "Books you purchased remain yours forever.",
        ],
    },
    "nordvpn": {
        "name": "NordVPN",
        "url": "https://my.nordaccount.com/dashboard/subscriptions/",
        "keywords": ["nordvpn", "nord", "nord account"],
        "steps_uk": [
            "Увійдіть на my.nordaccount.com → «Підписки».",
            "Оберіть NordVPN → «Скасувати автоматичне поновлення».",
            "Підтвердьте; захист працює до кінця оплаченого терміну.",
            "Для повернення коштів у 30-денний період — служба підтримки (чат).",
        ],
        "steps_en": [
            "Sign in at my.nordaccount.com → Subscriptions.",
            "Select NordVPN → Cancel automatic renewal.",
            "Confirm; protection runs until the paid term ends.",
            "For a refund within the 30-day period — contact support (chat).",
        ],
    },
}

_REGEX_CACHE: dict[str, re.Pattern] = {}


def _pattern(service: dict[str, Any]) -> re.Pattern:
    key = service["name"]
    pat = _REGEX_CACHE.get(key)
    if pat is None:
        pat = re.compile(
            "|".join(re.escape(k.lower()) for k in sorted(service["keywords"],
                                                          key=len, reverse=True)))
        _REGEX_CACHE[key] = pat
    return pat


def match_service(name: str) -> str | None:
    """Return the service id whose keywords match a subscription name,
    or None. Longer keywords win so 'youtube premium' beats 'youtube'."""
    hay = (name or "").lower()
    best: tuple[int, str] | None = None
    for sid, svc in SERVICES.items():
        m = _pattern(svc).search(hay)
        if m and (best is None or len(m.group(0)) > best[0]):
            best = (len(m.group(0)), sid)
    return best[1] if best else None


def guide(service_id: str) -> dict[str, Any] | None:
    svc = SERVICES.get(service_id)
    if not svc:
        return None
    return {
        "id": service_id,
        "name": svc["name"],
        "cancel_url": svc["url"],
        "steps_uk": svc["steps_uk"],
        "steps_en": svc["steps_en"],
    }


def all_services() -> list[dict[str, Any]]:
    """Stable, name-sorted list for the cancel-assistant catalogue."""
    out = []
    for sid in sorted(SERVICES, key=lambda s: SERVICES[s]["name"].lower()):
        svc = SERVICES[sid]
        out.append({"id": sid, "name": svc["name"], "cancel_url": svc["url"],
                    "keywords": svc["keywords"]})
    return out
