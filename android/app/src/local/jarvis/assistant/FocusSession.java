package local.jarvis.assistant;

/**
 * A focus session (coding or study) with breaks, pause, snooze and one gentle reminder when you've been
 * inactive in Jarvis for the grace period: the same rules as jarvis/static/sessions.js.
 *
 * "Inactive" means no taps, typing or scrolling in Jarvis (the page reports them), or Jarvis in the
 * background. Nothing here looks at other apps, the screen or what you type. Plain Java (no Android
 * classes), so it can be tested on the computer: android/test/FocusSessionTest.java.
 */
final class FocusSession {
    static final long MIN = 60000L, POUT_MS = 45000L;
    static final int NUDGE = 1, DONE = 2, BREAK_OVER = 4, BACK = 8;

    String kind = "", lastKind = "";
    long total, endsAt, pausedLeft = -1, snoozeUntil, breakEnds, lastActivity, lastAlertAt = -1000000000000L, poutUntil;
    boolean alerted, pausedByBreak;
    long graceMs = 5 * MIN, cooldownMs = 15 * MIN;
    int alertSeq, doneSeq, breakSeq, backSeq;

    boolean active() {
        return !kind.isEmpty();
    }

    boolean paused() {
        return active() && pausedLeft >= 0;
    }

    void start(String k, int minutes, int graceMinutes, int cooldownMinutes, long now) {
        kind = "study".equals(k) ? "study" : "coding";
        total = minutes * MIN;
        endsAt = now + total;
        pausedLeft = -1;
        pausedByBreak = false;
        snoozeUntil = 0;
        breakEnds = 0;
        lastActivity = now;
        alerted = false;
        poutUntil = 0;
        graceMs = Math.max(1, graceMinutes) * MIN;
        cooldownMs = Math.max(1, cooldownMinutes) * MIN;
    }

    void stop() {
        kind = "";
        pausedLeft = -1;
        pausedByBreak = false;
        poutUntil = 0;
        alerted = false;
    }

    void pause(boolean pause, long now) {
        if (pause && active() && !paused()) {
            pausedLeft = Math.max(0, endsAt - now);
            poutUntil = 0;
        } else if (!pause && paused()) {
            endsAt = now + pausedLeft;
            pausedLeft = -1;
            pausedByBreak = false;
            lastActivity = now;
            alerted = false;
        }
    }

    void snooze(int minutes, long now) {
        snoozeUntil = now + minutes * MIN;
        poutUntil = 0;
    }

    void startBreak(int minutes, long now) {
        if (minutes <= 0) {
            endBreak(now);
            return;
        }
        breakEnds = now + minutes * MIN;
        poutUntil = 0;
        if (active() && !paused()) {
            pause(true, now);
            pausedByBreak = true;
        }
    }

    private void endBreak(long now) {
        breakEnds = 0;
        if (pausedByBreak) {
            pause(false, now);
        }
    }

    /** The user did something in Jarvis. Returns BACK if that ended a stretch she had reminded you about. */
    int activity(long now) {
        int back = 0;
        if (alerted && active()) {
            backSeq++;
            back = BACK;
        }
        alerted = false;
        poutUntil = 0;
        lastActivity = now;
        return back;
    }

    /** Moves the clock on; returns what happened (NUDGE, DONE, BREAK_OVER bits). */
    int tick(long now) {
        int events = 0;
        if (breakEnds > 0 && now >= breakEnds) {
            endBreak(now);
            breakSeq++;
            events |= BREAK_OVER;
        }
        if (active() && !paused() && now >= endsAt) {
            lastKind = kind;
            stop();
            doneSeq++;
            events |= DONE;
        }
        if (active() && !paused() && breakEnds == 0 && now >= snoozeUntil) {
            long idle = now - lastActivity;
            if (idle >= graceMs && !alerted && now - lastAlertAt >= cooldownMs) {
                alerted = true; // one reminder per stretch: the next needs you back first, and the cooldown
                lastAlertAt = now;
                poutUntil = now + POUT_MS;
                alertSeq++;
                events |= NUDGE;
            }
        }
        return events;
    }

    boolean pouting(long now) {
        return active() && now < poutUntil;
    }

    boolean inBreak(long now) {
        return breakEnds > 0 && now < breakEnds;
    }

    long left(long now) {
        return paused() ? pausedLeft : Math.max(0, endsAt - now);
    }

    long inactiveFor(long now) {
        return now - lastActivity;
    }

    /** For the page (JarvisSessions.native): what the session looks like now. */
    String toJson(long now) {
        return "{\"active\":" + active() + ",\"kind\":\"" + kind + "\",\"lastKind\":\"" + lastKind + "\",\"total\":" + total
                + ",\"left\":" + left(now) + ",\"paused\":" + paused() + ",\"snoozed\":" + Math.max(0, snoozeUntil - now)
                + ",\"breakLeft\":" + (breakEnds > 0 ? Math.max(0, breakEnds - now) : 0) + ",\"inactiveFor\":" + inactiveFor(now)
                + ",\"pouting\":" + pouting(now) + ",\"alertSeq\":" + alertSeq + ",\"doneSeq\":" + doneSeq
                + ",\"breakSeq\":" + breakSeq + ",\"backSeq\":" + backSeq + "}";
    }

    /** Saved between app restarts (SharedPreferences), as simple key=value pairs. */
    String save() {
        return "kind=" + kind + ";lastKind=" + lastKind + ";total=" + total + ";endsAt=" + endsAt + ";pausedLeft=" + pausedLeft
                + ";snoozeUntil=" + snoozeUntil + ";breakEnds=" + breakEnds + ";lastActivity=" + lastActivity
                + ";lastAlertAt=" + lastAlertAt + ";alerted=" + alerted + ";pausedByBreak=" + pausedByBreak
                + ";graceMs=" + graceMs + ";cooldownMs=" + cooldownMs;
    }

    static FocusSession restore(String saved) {
        FocusSession s = new FocusSession();
        if (saved == null) {
            return s;
        }
        for (String part : saved.split(";")) {
            int eq = part.indexOf('=');
            if (eq <= 0) {
                continue;
            }
            String k = part.substring(0, eq), v = part.substring(eq + 1);
            try {
                if ("kind".equals(k)) {
                    s.kind = "study".equals(v) || "coding".equals(v) ? v : "";
                } else if ("lastKind".equals(k)) {
                    s.lastKind = v;
                } else if ("alerted".equals(k)) {
                    s.alerted = Boolean.parseBoolean(v);
                } else if ("pausedByBreak".equals(k)) {
                    s.pausedByBreak = Boolean.parseBoolean(v);
                } else {
                    long n = Long.parseLong(v);
                    if ("total".equals(k)) s.total = n;
                    else if ("endsAt".equals(k)) s.endsAt = n;
                    else if ("pausedLeft".equals(k)) s.pausedLeft = n;
                    else if ("snoozeUntil".equals(k)) s.snoozeUntil = n;
                    else if ("breakEnds".equals(k)) s.breakEnds = n;
                    else if ("lastActivity".equals(k)) s.lastActivity = n;
                    else if ("lastAlertAt".equals(k)) s.lastAlertAt = n;
                    else if ("graceMs".equals(k)) s.graceMs = n;
                    else if ("cooldownMs".equals(k)) s.cooldownMs = n;
                }
            } catch (NumberFormatException ignored) {
                // keep the default
            }
        }
        return s;
    }
}
