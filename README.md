# Trading Coach Bot 🤖📈

بوت ديسكورد متكامل يعمل كـ **مدرّب تداول شخصي** للفوركس والكريبتو. يحلّل الأسواق متعدد الفريمات (4H → 1m)، يبني خطة دخول كاملة (Entry / SL / TP) بنسبة مخاطرة ديناميكية 1:2 إلى 1:5، ويرسل ملخصاً يومياً + تنبيهات أسعار وأخبار.

> **مجاني 100%** — لا يعتمد على أي API مدفوع. Binance/Bybit عبر CCXT للكريبتو، yfinance للفوركس، ومصادر RSS مفتوحة للأخبار والتقويم الاقتصادي.

## ⚡ الاستراتيجية: Liquidity Sweep + MTF Confluence

استراتيجية مبنية خصيصاً وغير منتشرة، تجمع بين:

1. **تحديد الاتجاه على الفريم الأعلى (4H/1H)**: EMA stack + RSI Divergence + BOS/CHoCH.
2. **اختيار منطقة الدخول على 15m**: Liquidity Sweep + Order Block + Fair Value Gap.
3. **التوقيت على فريم 1m**: كسر هيكل + ارتفاع فوليوم.
4. **إدارة المخاطر الديناميكية**: SL مبني على ATR + هيكل، وTP بنسبة 1:2 / 1:3 / 1:5 حسب درجة الثقة.
5. **درجة ثقة (0-100%)** لكل إشارة قبل الدخول.

## 🛠️ الأوامر

| الأمر | الوظيفة |
|------|---------|
| `/analyze <symbol>` | تحليل MTF كامل + خطة دخول + شارت |
| `/daily` | ملخص السوق + أهم 3 فرص + أخبار |
| `/compare <symbol> <side> <entry> <sl> <tp>` | قارن تحليلك بتحليل البوت |
| `/backtest <symbol> [tf]` | باك تيست مبسط للاستراتيجية |
| `/price <symbol>` | السعر الفوري |
| `/watchlist add/remove/show` | قائمة متابعة |
| `/alert add/list/remove` | تنبيهات أسعار |
| `/news` | أهم الأخبار + sentiment |
| `/whales <symbol>` | حركات الحيتان + funding + OI + Long/Short |
| `/traders` | آخر تغريدات متداولين معروفين |
| `/calendar` | أحداث اقتصادية مهمة |
| `/cot` | تقرير COT الأسبوعي |
| `/portfolio open/close/show` | تتبّع الصفقات |
| `/journal add/show` | جورنال التداول |
| `/coach` | أسئلة المدرّب قبل الدخول |
| `/lesson` | درس اليوم |
| `/set_daily_channel` | اختر قناة الإشعار اليومي |

## 🚀 التشغيل المحلي

```bash
git clone https://github.com/FAFiveM/trading-coach-bot.git
cd trading-coach-bot
cp .env.example .env  # ضع توكن الديسكورد
pip install -e .[dev]
python -m coachbot
```

## ☁️ النشر على Fly.io (مجاني 24/7)

```bash
fly launch --no-deploy --name trading-coach-bot
fly volumes create coach_data --size 1 --region fra
fly secrets set DISCORD_BOT_TOKEN=<your_token>
# اختياري:
fly secrets set TWELVE_DATA_API_KEY=...
fly secrets set CRYPTOPANIC_API_KEY=...
fly secrets set ETHERSCAN_API_KEY=...
fly deploy
```

## 🔑 المتغيّرات

| المتغيّر | وصف |
|---------|-----|
| `DISCORD_BOT_TOKEN` | **مطلوب** — توكن البوت من Discord Developer Portal |
| `COACH_GUILD_ID` | (اختياري) ID لسيرفر معيّن لمزامنة الأوامر فوراً |
| `COACH_DAILY_HOUR_UTC` | ساعة إرسال الملخص اليومي بـ UTC (افتراضي 6) |
| `COACH_DEFAULT_RISK_PCT` | نسبة المخاطرة الافتراضية (افتراضي 1.0) |
| `TWELVE_DATA_API_KEY` | (اختياري) لتحسين بيانات الفوركس |
| `CRYPTOPANIC_API_KEY` | (اختياري) لأخبار الكريبتو |
| `ETHERSCAN_API_KEY` | (اختياري) لتتبع الحيتان |

## 📂 البنية

```
src/coachbot/
├── bot.py                # نقطة الدخول
├── config.py             # إعدادات
├── data/                 # طبقة البيانات (CCXT + yfinance + News + On-chain)
├── strategy/             # محرك التحليل (SMC, Indicators, Patterns, Engine, Backtest)
├── charts/               # توليد الشارتات
├── commands/             # أوامر Discord
├── alerts/               # المجدول
├── coach/                # دروس وأسئلة
├── db/                   # SQLAlchemy models + sessions
└── utils/                # أدوات (رموز، فريمات...)
```

## ⚠️ تنبيه

هذا البوت أداة تحليل تعليمية. التداول ينطوي على مخاطر، **التزم دائماً بإدارة المخاطر** (لا تخاطر بأكثر من 1% من رأس المال) ولا تعتمد على إشارة واحدة دون تحقق شخصي.
