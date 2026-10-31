# arzan.kz баға бақылаушысы

Бағаны оқиды → `price_history.csv`-ге жазады → баға өзгерсе `rocksomeone080@gmail.com` поштасына хат жібереді.
Өзгеріс: абсолют = соңғы − бастапқы; % = айырма ÷ бастапқы × 100. Баға оқылмаса, нөлмен толтырмайды, қате туралы хабарлайды.

## Қалай жұмыс істейді
arzan.kz беті JavaScript арқылы салынады, сондықтан бақылаушы бетті headless браузермен (Playwright) ашады
және `store` сөзі ("magnum") бар ұсыныстың бағасын алады: алдымен жүктелген JSON-нан, болмаса беттегі мәтіннен.
Бірнеше әртүрлі баға табылса (мысалы Magnum және Magnum Express), ол қате ретінде тізімделеді: сонда
`products.json`-да `"store"` мәнін нақтылаңыз (мысалы `"magnum go"`). Қателік хатында беттің мәтіні мен JSON
сұраулардың тізімі беріледі, бұл баптауға көмектеседі.

## Хат жіберу (алушы: rocksomeone080@gmail.com)
Алушыны `products.json`-дағы `recipient` өрісінен өзгертуге болады (бірнешеу үшін тізім: `["a@x.kz", "b@y.com"]`).
1. Gmail-де екі сатылы растауды қосып, Google Account → Security → App passwords арқылы 16 таңбалы құпия сөз алыңыз.
2. Құпия сөзді ешкімге жібермеңіз және файлға жазбаңыз; тек GitHub Secrets-ке немесе орта айнымалысына салыңыз:
   `SMTP_USER=rocksomeone080@gmail.com`, `SMTP_PASS=<app password>` (SMTP_HOST/PORT бастапқы: smtp.gmail.com / 587).

## Іске қосу
    pip install -r requirements.txt && playwright install chromium
    DRY_RUN=1 python price_monitor.py     # хатсыз тексеру (экранға шығарады)
    python price_monitor.py               # шынайы іске қосу

Автоматты: GitHub-та жеке репозиторий жасап, осы файлдарды салыңыз, Settings → Secrets → Actions ішіне
`SMTP_USER` пен `SMTP_PASS` қосыңыз. `.github/workflows/monitor.yml` күн сайын 09:00 (Астана) іске қосылады,
тарихты репозиторийге қайта сақтайды. Қолмен: Actions → Run workflow.

`price_history.csv` ішінде бастапқы мәндер (26.10.2026) тұр: Rakhat 969, Bayan Sulu 875, Яшкино 649 ₸.
Бірінші іске қосуда баға осыдан өзгеше болса, хат келеді.
