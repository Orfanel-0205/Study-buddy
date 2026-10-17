"""Reliable technologies and third-party APIs, and blueprints for common app types.

Everything here is a well-established product or open-source project. Costs are described
qualitatively on purpose (free / free tier / paid per use): prices and limits change, so the
app always tells you to check the provider's pricing page before you rely on them.
"""

from __future__ import annotations

TECH: dict[str, dict] = {}


def _t(id_, name, category, for_, why, cost, url, langs=("any",)):
    TECH[id_] = {"id": id_, "name": name, "category": category, "for": for_, "why": why, "cost": cost, "url": url, "langs": list(langs)}


# ---- frontend
_t("html", "HTML, CSS and JavaScript", "Frontend", "simple pages with no build step", "nothing to install; hosts anywhere for free", "free", "https://developer.mozilla.org/")
_t("tailwind", "Tailwind CSS", "Frontend", "styling with ready-made utility classes", "fast to build consistent, responsive designs", "free, open source", "https://tailwindcss.com/")
_t("bootstrap", "Bootstrap", "Frontend", "ready-made responsive components", "very well known; quick to get a decent look", "free, open source", "https://getbootstrap.com/")
_t("react", "React + Vite", "Frontend", "interactive web interfaces", "the most widely used UI library; huge community", "free, open source", "https://react.dev/", ("js", "ts"))
_t("nextjs", "Next.js", "Frontend + backend", "React apps with pages, server rendering and API routes in one project", "one codebase for site + API; deploys easily", "free, open source", "https://nextjs.org/", ("js", "ts"))
_t("astro", "Astro", "Frontend", "fast content websites (menus, portfolios, landing pages)", "ships very little JavaScript, great for SEO", "free, open source", "https://astro.build/", ("js", "ts"))
_t("expo", "Expo (React Native)", "Mobile", "Android and iPhone apps in JavaScript/TypeScript", "one codebase for both phones; test on your phone with Expo Go", "free; paid cloud build options", "https://expo.dev/", ("js", "ts"))
_t("flutter", "Flutter", "Mobile", "Android and iPhone apps in Dart", "polished UI from one codebase", "free, open source", "https://flutter.dev/")
# ---- backend
_t("laravel", "Laravel (PHP)", "Backend", "full web apps: routing, database (Eloquent), login, queues, mail", "mature and productive; you already run PHP with Laragon", "free, open source", "https://laravel.com/", ("php",))
_t("filament", "Filament (for Laravel)", "Admin panel", "admin/CMS screens (CRUD forms, tables, uploads) in hours", "saves weeks of admin UI work", "free, open source", "https://filamentphp.com/", ("php",))
_t("laravel-breeze", "Laravel Breeze", "Auth", "login, registration and password reset for Laravel", "official starter kit; simple to read", "free", "https://laravel.com/docs/starter-kits", ("php",))
_t("django", "Django (Python)", "Backend", "full web apps with a built-in admin site", "batteries included; the admin is free CMS-like screens", "free, open source", "https://www.djangoproject.com/", ("python",))
_t("fastapi", "FastAPI (Python)", "Backend", "JSON APIs with automatic docs", "fast to write, validates input for you", "free, open source", "https://fastapi.tiangolo.com/", ("python",))
_t("express", "Express (Node.js)", "Backend", "small JSON APIs and servers", "minimal and well known", "free, open source", "https://expressjs.com/", ("js", "ts"))
# ---- databases and backends-as-a-service
_t("mysql", "MySQL / MariaDB", "Database", "relational data (menus, orders, users)", "standard on PHP hosting; Laragon includes it", "free, open source", "https://www.mysql.com/", ("php",))
_t("postgresql", "PostgreSQL", "Database", "relational data with strong reliability", "rock solid; supported everywhere", "free, open source", "https://www.postgresql.org/")
_t("sqlite", "SQLite", "Database", "small apps, prototypes, single-server sites", "just a file; zero setup", "free", "https://sqlite.org/")
_t("supabase", "Supabase", "Backend as a service", "hosted PostgreSQL plus login, file storage and realtime", "a whole backend without running a server", "free tier for small projects (check limits; inactive free projects can be paused)", "https://supabase.com/", ("js", "ts", "python"))
_t("firebase", "Firebase", "Backend as a service", "login, Firestore database, hosting, push notifications", "Google-backed; great SDKs for web and mobile", "free Spark plan with limits; pay-as-you-go Blaze plan", "https://firebase.google.com/", ("js", "ts"))
_t("pocketbase", "PocketBase", "Backend as a service", "a one-file backend (database, login, admin UI) you host yourself", "very simple; great for hackathons", "free, open source (you pay only for hosting)", "https://pocketbase.io/")
_t("mongodb", "MongoDB Atlas", "Database", "document (JSON-like) data", "flexible schema; hosted service", "free tier cluster available", "https://www.mongodb.com/atlas")
# ---- auth
_t("clerk", "Clerk", "Auth", "ready-made sign-in screens and user management", "very fast to add login to React/Next.js", "free tier; paid above it", "https://clerk.com/", ("js", "ts"))
_t("authjs", "Auth.js (NextAuth)", "Auth", "login with Google/GitHub/email in Next.js", "open source; you keep your users", "free, open source", "https://authjs.dev/", ("js", "ts"))
# ---- hosting
_t("github-pages", "GitHub Pages", "Hosting", "static sites (HTML/CSS/JS, Astro build output)", "free and simple; good for demos and portfolios", "free", "https://pages.github.com/")
_t("netlify", "Netlify", "Hosting", "static and Jamstack sites, forms, serverless functions", "deploys from Git; free tier", "free tier; paid plans", "https://www.netlify.com/")
_t("vercel", "Vercel", "Hosting", "Next.js and frontend apps", "made by the Next.js team; great previews", "free Hobby plan is for personal, non-commercial use; client work needs a paid plan (check terms)", "https://vercel.com/", ("js", "ts"))
_t("cloudflare-pages", "Cloudflare Pages", "Hosting", "static sites and functions on a global network", "fast and generous free tier", "free tier; paid plans", "https://pages.cloudflare.com/")
_t("render", "Render", "Hosting", "web services, background workers and databases", "simple Heroku-like hosting", "free tier for web services sleeps when idle; paid plans", "https://render.com/")
_t("shared-php", "Shared PHP hosting (e.g. Hostinger)", "Hosting", "PHP/Laravel sites with MySQL for small businesses", "cheap and common; includes email and a domain on some plans", "paid, low monthly cost (check current plans)", "https://www.hostinger.com/", ("php",))
_t("vps", "A small VPS (DigitalOcean, Linode, Vultr)", "Hosting", "full control: any language, your own server", "predictable monthly price; you manage updates and security", "paid monthly", "https://www.digitalocean.com/")
# ---- payments
_t("paymongo", "PayMongo", "Payments", "online payments in the Philippines (cards, GCash, Maya and more)", "local e-wallets that Filipino customers actually use", "fee per transaction (check pricing)", "https://www.paymongo.com/")
_t("xendit", "Xendit", "Payments", "payments in Southeast Asia, including the Philippines (e-wallets, cards, bank transfers)", "well-documented APIs; regional coverage", "fee per transaction (check pricing)", "https://www.xendit.co/")
_t("stripe", "Stripe", "Payments", "card payments and subscriptions", "excellent docs and tools", "fee per transaction; not available for businesses in every country (check yours)", "https://stripe.com/")
_t("paypal", "PayPal", "Payments", "payments from customers who use PayPal", "widely available", "fee per transaction", "https://developer.paypal.com/")
# ---- messaging and email
_t("messenger", "Facebook Messenger Platform", "Messaging", "a chatbot or order inquiries on a Facebook Page", "where many local businesses already talk to customers", "free to use the platform (check Meta's policies)", "https://developers.facebook.com/docs/messenger-platform/")
_t("whatsapp", "WhatsApp Business Platform (Cloud API)", "Messaging", "WhatsApp messages from your app", "official API from Meta", "charged per conversation/message type (check pricing)", "https://developers.facebook.com/docs/whatsapp/")
_t("telegram", "Telegram Bot API", "Messaging", "bots for notifications or simple ordering", "free and easy to start", "free", "https://core.telegram.org/bots/api")
_t("twilio", "Twilio", "Messaging", "SMS, voice and WhatsApp messages", "very reliable, global", "paid per message (check pricing)", "https://www.twilio.com/")
_t("semaphore", "Semaphore", "Messaging", "SMS to Philippine numbers (OTP, order alerts)", "local SMS gateway", "paid per message (check pricing)", "https://semaphore.co/")
_t("resend", "Resend", "Email", "sending emails from your app (receipts, password resets)", "simple developer API", "free tier; paid above it", "https://resend.com/")
_t("brevo", "Brevo", "Email", "transactional emails and newsletters", "free plan with a daily limit", "free plan; paid plans", "https://www.brevo.com/")
# ---- maps, listing, media
_t("google-business", "Google Business Profile", "Listing", "showing up on Google Search and Maps with hours, menu and reviews", "where customers search first; not an API you build, but crucial", "free", "https://www.google.com/business/")
_t("google-maps", "Google Maps Platform", "Maps", "maps, places and directions inside your app", "best-known maps", "needs a billing account; free usage up to monthly limits (check pricing)", "https://developers.google.com/maps")
_t("leaflet", "Leaflet + OpenStreetMap", "Maps", "an embedded map with your location", "free and open source (follow the OSM tile usage policy)", "free", "https://leafletjs.com/")
_t("cloudinary", "Cloudinary", "Media", "uploading, resizing and serving photos (menu pictures)", "automatic image optimization and CDN", "free tier; paid above it", "https://cloudinary.com/")
_t("r2", "Cloudflare R2", "Storage", "storing files (S3-compatible)", "no egress (download) fees", "free tier; paid per GB", "https://www.cloudflare.com/developer-platform/r2/")
_t("qrcode", "QR code libraries (endroid/qr-code, qrcode for Python/npm)", "Utility", "QR codes for table menus and links", "free, generated in your own app", "free, open source", "https://github.com/endroid/qr-code")
# ---- AI and chatbots
_t("faq-bot", "A rule-based FAQ bot (no AI)", "Chatbot", "answering hours, location, menu and prices from your own data", "predictable, free, never makes things up; a good first version", "free", "https://developer.mozilla.org/")
_t("gemini", "Google Gemini API", "AI", "a chatbot or summaries with a hosted model", "has a free tier with rate limits (check terms; free-tier data may be used to improve products)", "free tier; paid per token", "https://ai.google.dev/")
_t("openai", "OpenAI API", "AI", "chatbots, extraction, summaries", "capable models; widely documented", "paid per token", "https://platform.openai.com/")
_t("anthropic", "Anthropic API (Claude)", "AI", "chatbots, reasoning over documents", "strong at following instructions", "paid per token", "https://www.anthropic.com/api")
_t("ollama", "Ollama (local models)", "AI", "running open models on your own computer (what Jarvis uses)", "private and free per question; needs your own hardware", "free (your hardware)", "https://ollama.com/")
# ---- analytics, quality, design
_t("ga4", "Google Analytics 4", "Analytics", "visitors and conversions", "free and standard", "free", "https://marketingplatform.google.com/about/analytics/")
_t("umami", "Umami", "Analytics", "privacy-friendly visitor stats", "simple and open source; self-host or cloud", "free self-hosted; cloud plans", "https://umami.is/")
_t("sentry", "Sentry", "Monitoring", "catching errors from real users", "shows the exact line and browser", "free developer tier", "https://sentry.io/")
_t("github", "GitHub + GitHub Actions", "Dev tools", "code hosting, reviews, automatic tests/deploys (CI)", "the standard place to keep and show your code", "free for most student use (Actions minutes are limited on private repos)", "https://github.com/")
_t("figma", "Figma", "Design", "screens and prototypes before coding", "share clickable mockups with clients", "free plan", "https://www.figma.com/")
_t("canva", "Canva", "Design", "flyers, menus, social posts, pitch slides", "fast, templates", "free plan; Pro is paid", "https://www.canva.com/")
# ---- DevNet / network automation
_t("netmiko", "Netmiko", "Network automation", "sending CLI commands to network devices over SSH from Python", "simplest way to automate Cisco and other devices", "free, open source", "https://github.com/ktbyers/netmiko", ("python",))
_t("ncclient", "ncclient", "Network automation", "NETCONF from Python", "the standard NETCONF client", "free, open source", "https://github.com/ncclient/ncclient", ("python",))
_t("pyats", "Cisco pyATS", "Network automation", "testing and validating network state", "made by Cisco; used in DevNet", "free", "https://developer.cisco.com/pyats/", ("python",))
_t("devnet-sandbox", "Cisco DevNet Sandbox", "Labs", "free practice devices and controllers (IOS XE, DNA Center, Meraki)", "real equipment without buying any", "free", "https://developer.cisco.com/site/sandbox/")


BLUEPRINTS: list[dict] = [
    {
        "id": "restaurant",
        "title": "Restaurant website with a menu admin (CMS)",
        "keywords": ["restaurant", "menu", "cafe", "café", "food", "eatery", "carinderia", "bakery", "coffee shop", "resto"],
        "features": ["Public pages: home, menu with categories, prices and photos, hours, map, contact",
                     "Admin: owner logs in and edits menu items, prices, photos, availability and announcements",
                     "QR code for table menus", "Google Business Profile and Facebook Page links",
                     "Later: FAQ chatbot (hours, location, menu), then online orders with local e-wallet payments"],
        "stacks": [
            {"name": "PHP: Laravel + Filament (you already have Laragon)", "langs": ["php"],
             "tech": ["laravel", "filament", "laravel-breeze", "mysql", "tailwind", "shared-php", "cloudinary", "qrcode", "faq-bot", "paymongo"],
             "structure": "laravel-cms"},
            {"name": "JavaScript/TypeScript: Next.js + Supabase", "langs": ["js", "ts"],
             "tech": ["nextjs", "tailwind", "supabase", "netlify", "qrcode", "faq-bot", "paymongo"],
             "structure": "next-supabase"},
            {"name": "Validate first (almost no code)", "langs": ["any"],
             "tech": ["google-business", "messenger", "html", "github-pages", "canva", "qrcode"],
             "structure": "static-site"},
        ],
        "data": ["restaurants (name, slug, phone, address, map_url, hours) — add restaurant_id to every table if you serve many restaurants",
                 "users (name, email, password_hash, role: owner/staff)",
                 "categories (restaurant_id, name, sort)",
                 "menu_items (restaurant_id, category_id, name, description, price, photo_url, is_available, sort)",
                 "announcements (restaurant_id, title, body, starts_at, ends_at)",
                 "faqs (restaurant_id, question, answer) — for the chatbot"],
        "mvp": ["One restaurant's public menu page from the database, looking good on phones",
                "Owner login + edit menu items and prices (Filament/admin screens)",
                "QR code poster + Google Business Profile link; deploy and show the owner",
                "FAQ chatbot answering hours/location/menu from the database",
                "Multi-restaurant: restaurant_id everywhere + a subdomain or /r/slug per restaurant"],
        "skip": ["online payments and delivery tracking until restaurants ask for them", "a custom mobile app", "an AI chatbot before the FAQ bot works"],
    },
    {
        "id": "ordering",
        "title": "Online ordering / small e-commerce",
        "keywords": ["order", "ordering", "shop", "store", "e-commerce", "ecommerce", "cart", "checkout", "sell online", "delivery"],
        "features": ["Product/menu catalog", "Cart and checkout", "Order status for staff", "Payment with e-wallets/cards", "Order notifications (email/SMS/Messenger)"],
        "stacks": [
            {"name": "PHP: Laravel + Filament + PayMongo", "langs": ["php"], "tech": ["laravel", "filament", "mysql", "tailwind", "paymongo", "resend", "semaphore", "shared-php"], "structure": "laravel-cms"},
            {"name": "JavaScript/TypeScript: Next.js + Supabase + PayMongo", "langs": ["js", "ts"], "tech": ["nextjs", "supabase", "tailwind", "paymongo", "resend", "netlify"], "structure": "next-supabase"},
        ],
        "data": ["products (name, price, stock, photo_url, is_active)", "customers (name, phone, email)", "orders (customer_id, status, total, payment_status, payment_ref)", "order_items (order_id, product_id, quantity, unit_price)"],
        "mvp": ["Catalog page", "Cart + order form (pay on pickup)", "Staff order list with statuses", "Online payment (sandbox first, then live)", "Notifications"],
        "skip": ["discount engines and loyalty points at first", "real-time delivery tracking"],
    },
    {
        "id": "booking",
        "title": "Booking / appointments / reservations",
        "keywords": ["booking", "book", "appointment", "reservation", "reserve", "schedule", "salon", "clinic", "rental"],
        "features": ["Available time slots", "Booking form with confirmation", "Admin calendar", "Reminders (SMS/email)", "No double booking (a database rule)"],
        "stacks": [
            {"name": "PHP: Laravel + Filament", "langs": ["php"], "tech": ["laravel", "filament", "mysql", "resend", "semaphore", "shared-php"], "structure": "laravel-cms"},
            {"name": "Python: Django (built-in admin)", "langs": ["python"], "tech": ["django", "postgresql", "bootstrap", "render", "resend"], "structure": "django"},
            {"name": "JavaScript/TypeScript: Next.js + Supabase", "langs": ["js", "ts"], "tech": ["nextjs", "supabase", "resend", "netlify"], "structure": "next-supabase"},
        ],
        "data": ["services (name, duration_minutes, price)", "staff (name)", "bookings (service_id, staff_id, customer_name, phone, starts_at, ends_at, status) with a UNIQUE rule on staff_id + starts_at"],
        "mvp": ["Show free slots", "Book + confirm", "Admin list/calendar", "Reminders", "Cancel/reschedule"],
        "skip": ["payments at booking until no-shows are a real problem"],
    },
    {
        "id": "learning",
        "title": "School / quiz / learning app",
        "keywords": ["school", "quiz", "students", "teacher", "class", "lms", "learning", "exam", "grades", "reviewer"],
        "features": ["Courses or subjects", "Quizzes with automatic scoring", "Student progress", "Teacher dashboard"],
        "stacks": [
            {"name": "Python: Django", "langs": ["python"], "tech": ["django", "postgresql", "bootstrap", "render"], "structure": "django"},
            {"name": "PHP: Laravel + Filament", "langs": ["php"], "tech": ["laravel", "filament", "mysql", "shared-php"], "structure": "laravel-cms"},
            {"name": "JavaScript/TypeScript: Next.js + Supabase", "langs": ["js", "ts"], "tech": ["nextjs", "supabase", "tailwind", "netlify"], "structure": "next-supabase"},
        ],
        "data": ["users (role: student/teacher)", "courses", "quizzes (course_id, title)", "questions (quiz_id, text, choices, answer)", "attempts (quiz_id, user_id, score, submitted_at)"],
        "mvp": ["Teacher creates a quiz", "Student takes it and sees the score", "Teacher sees results", "Progress per student"],
        "skip": ["video hosting (link to YouTube instead)", "chat between users"],
    },
    {
        "id": "inventory",
        "title": "Inventory / point of sale",
        "keywords": ["inventory", "stock", "pos", "point of sale", "sari-sari", "warehouse", "sales report"],
        "features": ["Products and stock levels", "Sales entry", "Low-stock alerts", "Daily/weekly reports and charts"],
        "stacks": [
            {"name": "PHP: Laravel + Filament", "langs": ["php"], "tech": ["laravel", "filament", "mysql", "shared-php"], "structure": "laravel-cms"},
            {"name": "Python: FastAPI + React", "langs": ["python"], "tech": ["fastapi", "postgresql", "react", "render"], "structure": "fastapi-react"},
        ],
        "data": ["products (sku, name, price, cost, stock, reorder_level)", "sales (total, created_at, user_id)", "sale_items (sale_id, product_id, quantity, unit_price)", "stock_movements (product_id, change, reason, created_at)"],
        "mvp": ["Products CRUD", "Record a sale (stock decreases in a transaction)", "Low-stock list", "Reports"],
        "skip": ["barcode hardware integration until the basics work"],
    },
    {
        "id": "chatbot",
        "title": "Chatbot / AI assistant",
        "keywords": ["chatbot", "chat bot", "ai assistant", "assistant", "faq", "messenger bot", "llm", "gpt"],
        "features": ["Answers from your own data (FAQ, menu, policies)", "Hand-off to a human", "Conversation log to improve answers"],
        "stacks": [
            {"name": "Start rule-based, add AI later", "langs": ["any"], "tech": ["faq-bot", "messenger", "telegram"], "structure": "fastapi-react"},
            {"name": "Python: FastAPI + an LLM API", "langs": ["python"], "tech": ["fastapi", "postgresql", "gemini", "openai", "anthropic"], "structure": "fastapi-react"},
            {"name": "JavaScript/TypeScript: Next.js route handler + an LLM API", "langs": ["js", "ts"], "tech": ["nextjs", "supabase", "gemini", "openai", "anthropic"], "structure": "next-supabase"},
        ],
        "data": ["faqs (question, answer, tags)", "conversations (channel, user_ref, started_at)", "messages (conversation_id, role, text, created_at)"],
        "mvp": ["FAQ matching (keywords) with a fallback 'ask a human'", "Log unanswered questions", "Add an LLM that may ONLY answer from your FAQ/menu text (send it as context)", "Connect to Messenger/Telegram"],
        "skip": ["training your own model", "voice"],
    },
    {
        "id": "dashboard",
        "title": "Dashboard / reports / analytics",
        "keywords": ["dashboard", "analytics", "report", "reports", "charts", "kpi", "monitoring"],
        "features": ["Import or collect data", "Charts that answer specific questions", "Filters by date", "Export"],
        "stacks": [
            {"name": "Python: FastAPI + React (or Django)", "langs": ["python"], "tech": ["fastapi", "postgresql", "react", "render"], "structure": "fastapi-react"},
            {"name": "JavaScript/TypeScript: Next.js + Supabase", "langs": ["js", "ts"], "tech": ["nextjs", "supabase", "netlify"], "structure": "next-supabase"},
        ],
        "data": ["the raw events or records (with created_at)", "precomputed daily summaries if queries get slow"],
        "mvp": ["One chart that answers the most important question", "Date filter", "Two or three more charts", "Export CSV"],
        "skip": ["real-time streaming until people ask for it"],
    },
    {
        "id": "mobile",
        "title": "Mobile app",
        "keywords": ["mobile app", "android app", "ios app", "iphone app", "phone app", "flutter", "react native"],
        "features": ["Screens for the core task", "Login", "Data sync with a backend", "Push notifications (later)"],
        "stacks": [
            {"name": "JavaScript/TypeScript: Expo + Supabase", "langs": ["js", "ts"], "tech": ["expo", "supabase"], "structure": "expo"},
            {"name": "Flutter + Firebase", "langs": ["any"], "tech": ["flutter", "firebase"], "structure": "expo"},
        ],
        "data": ["users", "the main items your app manages", "devices (push tokens) later"],
        "mvp": ["One core flow on one phone", "Login + sync", "Test with 5 real users", "Store release later"],
        "skip": ["a separate web admin until you need it"],
    },
    {
        "id": "network",
        "title": "Network automation (DevNet)",
        "keywords": ["network", "router", "switch", "cisco", "netconf", "restconf", "dna center", "meraki", "automation", "devnet"],
        "features": ["Inventory of devices", "Read state (interfaces, versions)", "Push safe config changes", "Reports and alerts"],
        "stacks": [
            {"name": "Python: Netmiko / ncclient / requests + FastAPI", "langs": ["python"], "tech": ["netmiko", "ncclient", "pyats", "fastapi", "sqlite", "devnet-sandbox"], "structure": "python-automation"},
        ],
        "data": ["devices (hostname, ip, platform, site)", "snapshots (device_id, taken_at, data)", "changes (device_id, diff, applied_by, status)"],
        "mvp": ["Connect to a DevNet Sandbox device and print its interfaces", "Save snapshots", "A report page", "A dry-run config change with a diff"],
        "skip": ["changing production devices before you have dry runs and rollbacks"],
    },
]

STRUCTURES: dict[str, str] = {
    "laravel-cms": """restaurant-cms/
├── app/
│   ├── Filament/Resources/      # admin screens: MenuItemResource.php, CategoryResource.php
│   ├── Http/Controllers/        # public pages: MenuController.php
│   ├── Models/                  # Restaurant.php, Category.php, MenuItem.php
│   └── Services/                # rules: OrderPolicy.php, Pricing.php
├── database/migrations/         # create_menu_items_table.php ...
├── database/seeders/            # sample menu for demos
├── resources/views/             # menu.blade.php, layouts/app.blade.php
├── routes/web.php               # public routes   (routes/api.php for a JSON API)
├── public/                      # the only folder the web server exposes
├── tests/Feature/               # MenuPageTest.php
├── .env.example                 # never commit .env
└── composer.json""",
    "next-supabase": """restaurant-site/
├── app/
│   ├── page.tsx                 # home
│   ├── menu/page.tsx            # public menu (server component reads Supabase)
│   ├── admin/                   # protected admin pages
│   └── api/chat/route.ts        # chatbot endpoint
├── components/                  # MenuList.tsx, MenuItemCard.tsx
├── lib/supabase.ts              # one client, created once
├── lib/rules.ts                 # business rules (pure functions)
├── supabase/migrations/         # SQL for tables and row-level security
├── public/                      # images, favicon
├── tests/
├── .env.local.example           # never commit .env.local
└── package.json""",
    "static-site": """menu-site/
├── index.html                   # one page: hero, menu, hours, map, contact
├── menu.json                    # menu data (easy to update)
├── assets/                      # photos (compressed), logo
├── styles.css
└── README.md                    # how to update the menu""",
    "django": """booking/
├── manage.py
├── config/                      # settings.py, urls.py
├── bookings/                    # one app per feature
│   ├── models.py  admin.py  views.py  urls.py  forms.py
│   ├── templates/bookings/
│   └── tests.py
├── requirements.txt
└── .env.example""",
    "fastapi-react": """project/
├── backend/
│   ├── app/main.py  routers/  services/  models.py  schemas.py
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/pages/  components/  api/
│   └── package.json
└── README.md""",
    "expo": """mobile-app/
├── app/                         # screens (Expo Router): index.tsx, item/[id].tsx
├── components/
├── lib/                         # api.ts (one place for requests), supabase.ts
├── assets/
└── app.json""",
    "python-automation": """netauto/
├── inventory.yaml               # devices (no passwords here)
├── netauto/
│   ├── connect.py               # Netmiko/ncclient sessions
│   ├── collect.py               # read state -> snapshots
│   ├── change.py                # dry-run diff, then apply
│   └── api.py                   # FastAPI report endpoints
├── tests/
├── .env.example                 # credentials come from environment variables
└── requirements.txt""",
}


def detect(idea: str) -> dict:
    text = idea.lower()
    scored = []
    for bp in BLUEPRINTS:
        score = sum(1 for k in bp["keywords"] if k in text)
        if score:
            scored.append((score, bp))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored else FALLBACK


def offline_data() -> dict:
    """Everything the phone needs to make the same plans without Jarvis (static/build.js)."""
    return {"blueprints": BLUEPRINTS, "fallback": FALLBACK, "tech": TECH, "structures": STRUCTURES}


FALLBACK = {  # when nothing in the idea matches a blueprint
        "id": "web", "title": "Web app", "keywords": [],
        "features": ["The one core flow your users need", "Login if users have their own data", "An admin view"],
        "stacks": [
            {"name": "PHP: Laravel", "langs": ["php"], "tech": ["laravel", "filament", "mysql", "shared-php"], "structure": "laravel-cms"},
            {"name": "Python: FastAPI + React", "langs": ["python"], "tech": ["fastapi", "postgresql", "react", "render"], "structure": "fastapi-react"},
            {"name": "JavaScript/TypeScript: Next.js + Supabase", "langs": ["js", "ts"], "tech": ["nextjs", "supabase", "netlify"], "structure": "next-supabase"},
        ],
        "data": ["users", "the main thing your app manages", "its history (created_at, updated_at)"],
        "mvp": ["The core flow end to end", "Deploy it", "Show 5 real users", "Fix what they trip on"],
        "skip": ["features nobody asked for yet"],
    }


def plan(idea: str, language: str = "any") -> dict:
    """A deterministic build plan for an idea: blueprint, stacks (preferred language first), techs, file trees."""
    bp = detect(idea)
    stacks = sorted(bp["stacks"], key=lambda st: 0 if language in st["langs"] else (1 if "any" in st["langs"] else 2))
    out = []
    for st in stacks:
        out.append({"name": st["name"], "tech": [TECH[t] for t in st["tech"] if t in TECH],
                    "structure": STRUCTURES.get(st["structure"], "")})
    return {"blueprint": bp["id"], "title": bp["title"], "features": bp["features"], "stacks": out,
            "data": bp["data"], "mvp": bp["mvp"], "skip": bp["skip"]}


def context_for(idea: str, language: str = "any", budget: int = 2600) -> str:
    """Compact notes for the model (stack/business/hackathon modes) so it recommends real, reliable tools."""
    p = plan(idea, language)
    lines = [f"## Jarvis catalog notes for this idea (well-established tools; costs change, so say 'check pricing')",
             f"Closest app type: {p['title']}", "Typical features: " + "; ".join(p["features"])]
    for st in p["stacks"]:
        lines.append(f"- Stack option '{st['name']}': " + "; ".join(f"{t['name']} ({t['for']}; {t['cost']})" for t in st["tech"]))
    lines.append("MVP order: " + " -> ".join(p["mvp"]))
    lines.append("Skip at first: " + "; ".join(p["skip"]))
    text = "\n".join(lines)
    return text[:budget]
