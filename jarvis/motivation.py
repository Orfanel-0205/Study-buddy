"""A Bible verse or a quote when you open Jarvis, picked for what you're likely facing right now.

Verses are from the King James Version (public domain). Quotes are only included when the
attribution is well documented. Stoicism and philosophy (marked "school") are quoted exactly from
public-domain translations named in the source: Marcus Aurelius (George Long), Epictetus (Elizabeth
Carter, T. W. Higginson, George Long), Seneca's letters (Richard M. Gummere), Aristotle (W. D. Ross),
Plato (Benjamin Jowett), Pascal (W. F. Trotter) and Confucius (James Legge). They come up more often
than the rest (PHILOSOPHY_WEIGHT), or on their own with kinds="philosophy". "Jarvis" notes are short
reminders written for this app.

Each entry has themes. The pick leans on:
- the time of day (late at night: rest; morning: purpose and courage),
- what you've been doing (a long day of work, overdue tasks, failing practice or tests, a streak),
- what matters most to you (your choice in the app: success, security, freedom, recognition or peace),
and avoids repeating the ones you saw recently.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from .db import Database

V, Q, J = "verse", "quote", "note"

ENTRIES: list[dict] = [
    # ---- rest, overwork, limits
    {"id": "mt-11-28", "kind": V, "source": "Matthew 11:28 (KJV)", "themes": ["rest", "peace"],
     "text": "Come unto me, all ye that labour and are heavy laden, and I will give you rest."},
    {"id": "ps-127-2", "kind": V, "source": "Psalm 127:2 (KJV)", "themes": ["rest"],
     "text": "It is vain for you to rise up early, to sit up late, to eat the bread of sorrows: for so he giveth his beloved sleep."},
    {"id": "mk-6-31", "kind": V, "source": "Mark 6:31 (KJV)", "themes": ["rest"],
     "text": "Come ye yourselves apart into a desert place, and rest a while."},
    {"id": "ps-23-1", "kind": V, "source": "Psalm 23:1–2 (KJV)", "themes": ["rest", "security", "peace"],
     "text": "The LORD is my shepherd; I shall not want. He maketh me to lie down in green pastures: he leadeth me beside the still waters."},
    {"id": "lubbock-rest", "kind": Q, "source": "John Lubbock, The Use of Life", "themes": ["rest"],
     "text": "Rest is not idleness, and to lie sometimes on the grass under trees on a summer's day, listening to the murmur of the water, or watching the clouds float across the sky, is by no means a waste of time."},
    {"id": "lamott-unplug", "kind": Q, "source": "Anne Lamott", "themes": ["rest"],
     "text": "Almost everything will work again if you unplug it for a few minutes, including you."},
    {"id": "j-capacity", "kind": J, "source": "Jarvis", "themes": ["rest", "focus"],
     "text": "Resilience isn't tolerating unlimited stress. It's noticing your limit before you reach it. A break now is part of the plan."},
    {"id": "j-sleep", "kind": J, "source": "Jarvis", "themes": ["rest"],
     "text": "It's late. Write down where you stopped and the next step, then rest. Tomorrow-you will solve it faster."},
    # ---- peace, worry, overthinking
    {"id": "php-4-6", "kind": V, "source": "Philippians 4:6–7 (KJV)", "themes": ["peace"],
     "text": "Be careful for nothing; but in every thing by prayer and supplication with thanksgiving let your requests be made known unto God. And the peace of God, which passeth all understanding, shall keep your hearts and minds through Christ Jesus."},
    {"id": "mt-6-34", "kind": V, "source": "Matthew 6:34 (KJV)", "themes": ["peace", "focus"],
     "text": "Take therefore no thought for the morrow: for the morrow shall take thought for the things of itself. Sufficient unto the day is the evil thereof."},
    {"id": "1pe-5-7", "kind": V, "source": "1 Peter 5:7 (KJV)", "themes": ["peace", "help"],
     "text": "Casting all your care upon him; for he careth for you."},
    {"id": "ps-46-10", "kind": V, "source": "Psalm 46:10 (KJV)", "themes": ["peace"],
     "text": "Be still, and know that I am God."},
    {"id": "seneca-imagination", "kind": Q, "source": "Seneca, Letters to Lucilius 13 (tr. Richard M. Gummere)", "themes": ["peace"], "school": "stoic",
     "text": "There are more things, Lucilius, likely to frighten us than there are to crush us; we suffer more often in imagination than in reality."},
    {"id": "curie-understood", "kind": Q, "source": "Marie Curie", "themes": ["peace", "growth"],
     "text": "Nothing in life is to be feared, it is only to be understood."},
    {"id": "j-control", "kind": J, "source": "Jarvis", "themes": ["peace", "focus"],
     "text": "List what you can control today and what you can't. Give your energy to the first list."},
    # ---- perseverance after failure
    {"id": "gal-6-9", "kind": V, "source": "Galatians 6:9 (KJV)", "themes": ["perseverance"],
     "text": "And let us not be weary in well doing: for in due season we shall reap, if we faint not."},
    {"id": "isa-40-31", "kind": V, "source": "Isaiah 40:31 (KJV)", "themes": ["perseverance", "rest"],
     "text": "But they that wait upon the LORD shall renew their strength; they shall mount up with wings as eagles; they shall run, and not be weary; and they shall walk, and not faint."},
    {"id": "pr-24-16", "kind": V, "source": "Proverbs 24:16 (KJV)", "themes": ["perseverance", "worth"],
     "text": "For a just man falleth seven times, and riseth up again."},
    {"id": "lam-3-22", "kind": V, "source": "Lamentations 3:22–23 (KJV)", "themes": ["perseverance", "peace"],
     "text": "It is of the LORD's mercies that we are not consumed, because his compassions fail not. They are new every morning: great is thy faithfulness."},
    {"id": "2co-12-9", "kind": V, "source": "2 Corinthians 12:9 (KJV)", "themes": ["perseverance", "worth"],
     "text": "My grace is sufficient for thee: for my strength is made perfect in weakness."},
    {"id": "aurelius-obstacle", "kind": Q, "source": "Marcus Aurelius, Meditations 5.20 (tr. Gregory Hays)", "themes": ["perseverance"], "school": "stoic",
     "text": "The impediment to action advances action. What stands in the way becomes the way."},
    {"id": "j-outcome", "kind": J, "source": "Jarvis", "themes": ["perseverance", "worth"],
     "text": "Being disappointed in an outcome is not the same as being disappointed in yourself. Keep the lesson, drop the verdict."},
    {"id": "j-failing-tests", "kind": J, "source": "Jarvis", "themes": ["perseverance"],
     "text": "A failing test is information, not a judgement. Read the first error, fix one thing, run it again."},
    # ---- purpose, building, ambition
    {"id": "pr-16-3", "kind": V, "source": "Proverbs 16:3 (KJV)", "themes": ["purpose", "success"],
     "text": "Commit thy works unto the LORD, and thy thoughts shall be established."},
    {"id": "jer-29-11", "kind": V, "source": "Jeremiah 29:11 (KJV)", "themes": ["purpose", "security"],
     "text": "For I know the thoughts that I think toward you, saith the LORD, thoughts of peace, and not of evil, to give you an expected end."},
    {"id": "pr-3-5", "kind": V, "source": "Proverbs 3:5–6 (KJV)", "themes": ["purpose", "peace"],
     "text": "Trust in the LORD with all thine heart; and lean not unto thine own understanding. In all thy ways acknowledge him, and he shall direct thy paths."},
    {"id": "hab-2-2", "kind": V, "source": "Habakkuk 2:2 (KJV)", "themes": ["purpose", "focus"],
     "text": "Write the vision, and make it plain upon tables, that he may run that readeth it."},
    {"id": "lk-14-28", "kind": V, "source": "Luke 14:28 (KJV)", "themes": ["purpose", "focus"],
     "text": "For which of you, intending to build a tower, sitteth not down first, and counteth the cost, whether he have sufficient to finish it?"},
    {"id": "rom-8-28", "kind": V, "source": "Romans 8:28 (KJV)", "themes": ["purpose", "security"],
     "text": "And we know that all things work together for good to them that love God, to them who are the called according to his purpose."},
    {"id": "kay-invent", "kind": Q, "source": "Alan Kay", "themes": ["purpose", "freedom"],
     "text": "The best way to predict the future is to invent it."},
    {"id": "j-builder", "kind": J, "source": "Jarvis", "themes": ["purpose", "success"],
     "text": "You don't need ten goals today. Pick the one that deserves your energy first, and finish it."},
    # ---- diligence, skill, growth
    {"id": "col-3-23", "kind": V, "source": "Colossians 3:23 (KJV)", "themes": ["diligence", "worth"],
     "text": "And whatsoever ye do, do it heartily, as to the Lord, and not unto men."},
    {"id": "pr-22-29", "kind": V, "source": "Proverbs 22:29 (KJV)", "themes": ["diligence", "recognition", "success"],
     "text": "Seest thou a man diligent in his business? he shall stand before kings; he shall not stand before mean men."},
    {"id": "ecc-9-10", "kind": V, "source": "Ecclesiastes 9:10 (KJV)", "themes": ["diligence"],
     "text": "Whatsoever thy hand findeth to do, do it with thy might."},
    {"id": "zec-4-10", "kind": V, "source": "Zechariah 4:10 (KJV)", "themes": ["growth", "worth"],
     "text": "For who hath despised the day of small things?"},
    {"id": "ps-90-12", "kind": V, "source": "Psalm 90:12 (KJV)", "themes": ["growth", "focus"],
     "text": "So teach us to number our days, that we may apply our hearts unto wisdom."},
    {"id": "durant-habit", "kind": Q, "source": "Will Durant, on Aristotle", "themes": ["growth", "diligence"], "school": "philosophy",
     "text": "We are what we repeatedly do. Excellence, then, is not an act, but a habit."},
    {"id": "beck-work", "kind": Q, "source": "Kent Beck", "themes": ["growth", "focus"],
     "text": "Make it work, make it right, make it fast."},
    {"id": "fowler-humans", "kind": Q, "source": "Martin Fowler, Refactoring", "themes": ["growth", "diligence"],
     "text": "Any fool can write code that a computer can understand. Good programmers write code that humans can understand."},
    {"id": "dijkstra-simple", "kind": Q, "source": "Edsger W. Dijkstra", "themes": ["growth", "focus"],
     "text": "Simplicity is prerequisite for reliability."},
    {"id": "j-progress", "kind": J, "source": "Jarvis", "themes": ["growth", "worth"],
     "text": "Compare yourself with you three months ago, not with someone else's highlight reel. You've come further than you feel."},
    # ---- courage, freedom
    {"id": "jos-1-9", "kind": V, "source": "Joshua 1:9 (KJV)", "themes": ["courage", "security"],
     "text": "Have not I commanded thee? Be strong and of a good courage; be not afraid, neither be thou dismayed: for the LORD thy God is with thee whithersoever thou goest."},
    {"id": "php-4-13", "kind": V, "source": "Philippians 4:13 (KJV)", "themes": ["courage", "success"],
     "text": "I can do all things through Christ which strengtheneth me."},
    {"id": "j-apply", "kind": J, "source": "Jarvis", "themes": ["courage", "freedom", "success"],
     "text": "If you meet most of the requirements, apply. Waiting to feel 100% ready is how good chances pass by."},
    # ---- help, connection, not carrying everything alone
    {"id": "gal-6-2", "kind": V, "source": "Galatians 6:2 (KJV)", "themes": ["help", "connection"],
     "text": "Bear ye one another's burdens, and so fulfil the law of Christ."},
    {"id": "ecc-4-9", "kind": V, "source": "Ecclesiastes 4:9–10 (KJV)", "themes": ["help", "connection"],
     "text": "Two are better than one; because they have a good reward for their labour. For if they fall, the one will lift up his fellow."},
    {"id": "pr-15-22", "kind": V, "source": "Proverbs 15:22 (KJV)", "themes": ["help", "focus"],
     "text": "Without counsel purposes are disappointed: but in the multitude of counsellors they are established."},
    {"id": "j-ask", "kind": J, "source": "Jarvis", "themes": ["help"],
     "text": "You don't have to carry every responsibility alone. Ask one person for help or advice today."},
    {"id": "j-people", "kind": J, "source": "Jarvis", "themes": ["connection", "rest"],
     "text": "Success is better shared. Send a message to someone you care about before you dive back in."},
    # ---- Stoicism: Marcus Aurelius (tr. George Long, 1862)
    {"id": "ma-8-47", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 8.47 (tr. George Long)", "themes": ["peace"],
     "text": "If thou art pained by any external thing, it is not this thing that disturbs thee, but thy own judgement about it. And it is in thy power to wipe out this judgement now."},
    {"id": "ma-5-1", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 5.1 (tr. George Long)", "themes": ["purpose", "diligence"],
     "text": "In the morning when thou risest unwillingly, let this thought be present\u2014I am rising to the work of a human being."},
    {"id": "ma-5-16", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 5.16 (tr. George Long)", "themes": ["growth", "focus"],
     "text": "Such as are thy habitual thoughts, such also will be the character of thy mind; for the soul is dyed by the thoughts."},
    {"id": "ma-10-16", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 10.16 (tr. George Long)", "themes": ["diligence", "courage"],
     "text": "No longer talk at all about the kind of man that a good man ought to be, but be such."},
    {"id": "ma-4-17", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 4.17 (tr. George Long)", "themes": ["purpose", "focus"],
     "text": "Do not act as if thou wert going to live ten thousand years. Death hangs over thee. While thou livest, while it is in thy power, be good."},
    {"id": "ma-7-59", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 7.59 (tr. George Long)", "themes": ["worth", "peace"],
     "text": "Look within. Within is the fountain of good, and it will ever bubble up, if thou wilt ever dig."},
    {"id": "ma-4-49", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 4.49 (tr. George Long)", "themes": ["perseverance", "security"],
     "text": "Be like the promontory against which the waves continually break, but it stands firm and tames the fury of the water around it."},
    {"id": "ma-8-36", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 8.36 (tr. George Long)", "themes": ["peace", "focus"],
     "text": "Do not disturb thyself by thinking of the whole of thy life. Let not thy thoughts at once embrace all the various troubles which thou mayest expect to befall thee: but on every occasion ask thyself, What is there in this which is intolerable and past bearing?"},
    {"id": "ma-9-29", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 9.29 (tr. George Long)", "themes": ["growth", "perseverance"],
     "text": "Do not expect Plato's Republic: but be content if the smallest thing goes on well, and consider such an event to be no small matter."},
    {"id": "ma-12-4", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 12.4 (tr. George Long)", "themes": ["recognition", "worth"],
     "text": "I have often wondered how it is that every man loves himself more than all the rest of men, but yet sets less value on his own opinion of himself than on the opinion of others."},
    {"id": "ma-7-8", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 7.8 (tr. George Long)", "themes": ["peace", "security"],
     "text": "Let not future things disturb thee, for thou wilt come to them, if it shall be necessary, having with thee the same reason which now thou usest for present things."},
    {"id": "ma-4-3", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 4.3 (tr. George Long)", "themes": ["rest", "peace"],
     "text": "For nowhere either with more quiet or more freedom from trouble does a man retire than into his own soul."},
    {"id": "ma-6-6", "kind": Q, "school": "stoic", "source": "Marcus Aurelius, Meditations 6.6 (tr. George Long)", "themes": ["peace", "worth"],
     "text": "The best way of avenging thyself is not to become like the wrong doer."},
    # ---- Stoicism: Epictetus
    {"id": "ep-ench-1", "kind": Q, "school": "stoic", "source": "Epictetus, Enchiridion 1 (tr. T. W. Higginson)", "themes": ["peace", "focus", "freedom"],
     "text": "There are things which are within our power, and there are things which are beyond our power. Within our power are opinion, aim, desire, aversion, and, in one word, whatever affairs are our own."},
    {"id": "ep-ench-5", "kind": Q, "school": "stoic", "source": "Epictetus, Enchiridion 5 (tr. Elizabeth Carter)", "themes": ["peace"],
     "text": "Men are disturbed, not by things, but by the principles and notions which they form concerning things."},
    {"id": "ep-ench-8", "kind": Q, "school": "stoic", "source": "Epictetus, Enchiridion 8 (tr. T. W. Higginson)", "themes": ["peace", "freedom"],
     "text": "Demand not that events should happen as you wish; but wish them to happen as they do happen, and you will go on well."},
    {"id": "ep-disc-1-15", "kind": Q, "school": "stoic", "source": "Epictetus, Discourses 1.15 (tr. T. W. Higginson)", "themes": ["growth", "perseverance"],
     "text": "No great thing is created suddenly, any more than a bunch of grapes or a fig. If you tell me that you desire a fig, I answer you that there must be time. Let it first blossom, then bear fruit, then ripen."},
    {"id": "ep-disc-2-18", "kind": Q, "school": "stoic", "source": "Epictetus, Discourses 2.18 (tr. George Long)", "themes": ["diligence", "growth"],
     "text": "Every habit and faculty is maintained and increased by the corresponding actions: the habit of walking by walking, the habit of running by running."},
    # ---- Stoicism: Seneca, Letters to Lucilius (tr. Richard M. Gummere)
    {"id": "sen-1", "kind": Q, "school": "stoic", "source": "Seneca, Letters to Lucilius 1 (tr. Richard M. Gummere)", "themes": ["focus", "purpose"],
     "text": "Nothing, Lucilius, is ours, except time."},
    {"id": "sen-2-6", "kind": Q, "school": "stoic", "source": "Seneca, Letters to Lucilius 2 (tr. Richard M. Gummere)", "themes": ["security", "peace"],
     "text": "It is not the man who has too little, but the man who craves more, that is poor."},
    {"id": "sen-2-2", "kind": Q, "school": "stoic", "source": "Seneca, Letters to Lucilius 2 (tr. Richard M. Gummere)", "themes": ["focus"],
     "text": "Everywhere means nowhere."},
    {"id": "sen-7-8", "kind": Q, "school": "stoic", "source": "Seneca, Letters to Lucilius 7 (tr. Richard M. Gummere)", "themes": ["help", "growth"],
     "text": "Men learn while they teach."},
    {"id": "sen-28-1", "kind": Q, "school": "stoic", "source": "Seneca, Letters to Lucilius 28 (tr. Richard M. Gummere)", "themes": ["peace", "growth"],
     "text": "You need a change of soul rather than a change of climate."},
    {"id": "sen-71-3", "kind": Q, "school": "stoic", "source": "Seneca, Letters to Lucilius 71 (tr. Richard M. Gummere)", "themes": ["purpose", "focus"],
     "text": "When a man does not know what harbour he is making for, no wind is the right wind."},
    # ---- philosophy
    {"id": "aristotle-swallow", "kind": Q, "school": "philosophy", "source": "Aristotle, Nicomachean Ethics I.7 (tr. W. D. Ross)", "themes": ["perseverance", "growth"],
     "text": "For one swallow does not make a summer, nor does one day; and so too one day, or a short time, does not make a man blessed and happy."},
    {"id": "aristotle-doing", "kind": Q, "school": "philosophy", "source": "Aristotle, Nicomachean Ethics II.1 (tr. W. D. Ross)", "themes": ["diligence", "growth"],
     "text": "For the things we have to learn before we can do them, we learn by doing them, e.g. men become builders by building and lyreplayers by playing the lyre."},
    {"id": "socrates-examined", "kind": Q, "school": "philosophy", "source": "Socrates, in Plato's Apology (tr. Benjamin Jowett)", "themes": ["purpose", "growth"],
     "text": "The unexamined life is not worth living."},
    {"id": "pascal-room", "kind": Q, "school": "philosophy", "source": "Blaise Pascal, Pens\u00e9es 139 (tr. W. F. Trotter)", "themes": ["rest", "peace"],
     "text": "I have discovered that all the unhappiness of men arises from one single fact, that they cannot stay quietly in their own chamber."},
    {"id": "confucius-know", "kind": Q, "school": "philosophy", "source": "Confucius, Analects 2.17 (tr. James Legge)", "themes": ["growth", "help"],
     "text": "When you know a thing, to hold that you know it; and when you do not know a thing, to allow that you do not know it;\u2014this is knowledge."},
]

PHILOSOPHY_WEIGHT = 2.5  # Stoicism and philosophy come up more often than the other kinds
PHILOSOPHY = "philosophy"  # kinds: only Stoicism and philosophy

FOCUS_THEMES = {  # what matters most to you -> themes to show more often
    "success": ["success", "growth", "diligence", "perseverance"],
    "security": ["security", "purpose", "peace"],
    "freedom": ["freedom", "courage", "purpose"],
    "recognition": ["recognition", "diligence", "worth"],
    "peace": ["peace", "rest", "worth"],
}


def _context(db: Database, now: datetime) -> dict:
    """Signals from today's activity, used to pick a fitting message."""
    start_today = datetime.combine(now.date(), datetime.min.time()).astimezone().astimezone(timezone.utc).isoformat()
    recent = (now - timedelta(days=2)).astimezone(timezone.utc).isoformat()
    with db.connect() as conn:
        actions_today = conn.execute("SELECT COUNT(*) FROM actions WHERE created_at >= ? AND kind NOT IN "
                                     "('session_started', 'backup', 'sync', 'phone_access')", (start_today,)).fetchone()[0]
        first = conn.execute("SELECT MIN(created_at) FROM actions WHERE created_at >= ? AND kind NOT IN "
                             "('session_started', 'backup', 'sync', 'phone_access')", (start_today,)).fetchone()[0]
        overdue = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done' AND due_date IS NOT NULL AND due_date < ?",
                               (now.date().isoformat(),)).fetchone()[0]
        fails = 0
        for r in conn.execute("SELECT kind, details FROM actions WHERE created_at >= ? AND kind IN ('practice', 'command_finished')",
                              (recent,)):
            try:
                d = json.loads(r["details"] or "{}")
            except ValueError:
                continue
            if (r["kind"] == "practice" and d.get("passed", 0) < d.get("total", 0)) or \
                    (r["kind"] == "command_finished" and d.get("exit_code") not in (0, None)):
                fails += 1
        reviews_today = conn.execute("SELECT COUNT(*) FROM study_reviews WHERE reviewed_at >= ?", (start_today,)).fetchone()[0]
        felt = conn.execute("SELECT mood, energy, stress FROM checkins WHERE at >= ? ORDER BY at DESC LIMIT 1",
                            (start_today,)).fetchone()
    hours = 0.0
    if first:
        try:
            hours = (now - datetime.fromisoformat(first).astimezone()).total_seconds() / 3600
        except ValueError:
            hours = 0.0
    return {"hour": now.hour, "actions_today": actions_today, "hours_active": round(hours, 1), "overdue": overdue,
            "recent_failures": fails, "reviews_today": reviews_today, "weekend": now.weekday() >= 5,
            "checkin": dict(felt) if felt else None}


def pick(db: Database, *, kinds: str = "both", focus: str = "", exclude: list[str] | None = None,
         now: datetime | None = None, rng: random.Random | None = None) -> dict:
    now = now or datetime.now().astimezone()
    rng = rng or random.Random()
    ctx = _context(db, now)
    if kinds == PHILOSOPHY:
        pool = [e for e in ENTRIES if e.get("school")]
    else:
        wanted = {"both": {V, Q, J}, "verses": {V}, "quotes": {Q, J}}.get(kinds, {V, Q, J})
        pool = [e for e in ENTRIES if e["kind"] in wanted] or ENTRIES
    weights: dict[str, float] = {}
    reason = ""
    boost: list[tuple[list[str], float, str]] = []
    felt = ctx["checkin"]  # today's check-in comes first: it's what you told Jarvis
    if felt and felt["mood"] <= 2:
        boost.append((["worth", "peace", "help"], 4.0, "You said today feels heavy"))
    if felt and felt["stress"] >= 4:
        boost.append((["peace", "rest"], 3.5, "You said you're stressed"))
    if felt and felt["energy"] <= 2:
        boost.append((["rest"], 3.0, "You said your energy is low"))
    if ctx["hour"] >= 22 or ctx["hour"] < 4:
        boost.append((["rest", "peace"], 4.0, "It's late"))
    elif ctx["hour"] < 10:
        boost.append((["purpose", "courage", "diligence"], 2.0, "A new day"))
    if ctx["hours_active"] >= 6 and ctx["actions_today"] >= 20:
        boost.append((["rest", "help"], 3.0, "You've been working for hours"))
    if ctx["overdue"] >= 3:
        boost.append((["focus", "peace", "help"], 2.5, f"{ctx['overdue']} tasks are overdue"))
    if ctx["recent_failures"] >= 3:
        boost.append((["perseverance", "worth"], 3.0, "Some tests didn't pass lately"))
    if ctx["weekend"]:
        boost.append((["rest", "connection"], 1.5, "It's the weekend"))
    if focus in FOCUS_THEMES:
        boost.append((FOCUS_THEMES[focus], 2.0, ""))
    for e in pool:
        w = PHILOSOPHY_WEIGHT if e.get("school") and kinds != PHILOSOPHY else 1.0
        for themes, factor, _ in boost:
            if any(t in e["themes"] for t in themes):
                w *= factor
        weights[e["id"]] = w
    recent = set(exclude or [])
    choices = [e for e in pool if e["id"] not in recent] or pool
    entry = rng.choices(choices, weights=[weights[e["id"]] for e in choices], k=1)[0]
    for themes, _, why in boost:
        if why and any(t in entry["themes"] for t in themes):
            reason = why
            break
    return {**entry, "reason": reason, "context": ctx}
