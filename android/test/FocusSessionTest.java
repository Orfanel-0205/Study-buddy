package local.jarvis.assistant;

/**
 * Tests the phone's focus-session rules (FocusSession.java) on the computer, with a fake clock:
 *   python android/test_focus_session.py
 * The same cases as tests/js/sessions.test.js, so the phone and the page behave alike.
 */
public final class FocusSessionTest {
    private static int failures = 0;
    private static long t = 1_800_000_000_000L;

    private static void check(boolean ok, String what) {
        System.out.println((ok ? "PASS  " : "FAIL  ") + what);
        if (!ok) {
            failures++;
        }
    }

    /** Advances the clock in 1-second steps; returns all the event bits that happened. */
    private static int run(FocusSession s, double minutes) {
        int events = 0;
        for (int i = 0; i < Math.round(minutes * 60); i++) {
            t += 1000;
            events |= s.tick(t);
        }
        return events;
    }

    public static void main(String[] args) {
        FocusSession s = new FocusSession();
        s.start("coding", 25, 5, 15, t);
        int ev = 0;
        for (int m = 0; m < 26; m++) {
            s.activity(t);
            ev |= run(s, 1);
        }
        check(ev == FocusSession.DONE && !s.active() && "coding".equals(s.lastKind), "a busy session ends with DONE only");

        s = new FocusSession();
        s.start("study", 50, 5, 15, t);
        check(run(s, 4.9) == 0, "nothing inside the grace period");
        check(run(s, 0.2) == FocusSession.NUDGE && s.pouting(t), "one reminder after 5 minutes, and she pouts");
        run(s, FocusSession.POUT_MS / 60000.0 + 0.05);
        check(!s.pouting(t), "she stops pouting after a while");
        check(run(s, 20) == 0, "no second reminder while you stay away");
        check(s.activity(t) == FocusSession.BACK, "coming back is noticed");
        check(run(s, 5.1) == FocusSession.NUDGE, "a new stretch away can be reminded again after the cooldown");

        s = new FocusSession();
        s.start("coding", 60, 1, 15, t);
        check(run(s, 1.1) == FocusSession.NUDGE, "grace 1 minute");
        s.activity(t);
        check(run(s, 3) == 0, "quiet within the cooldown");
        check(run(s, 12) == FocusSession.NUDGE, "reminded again after the cooldown");

        s = new FocusSession();
        s.start("coding", 30, 2, 1, t);
        s.pause(true, t);
        long left = s.left(t);
        check(run(s, 10) == 0 && s.left(t) == left, "paused: no reminders and the clock stops");
        s.pause(false, t);
        s.snooze(15, t);
        check(run(s, 10) == 0, "snoozed: no reminders");
        s.activity(t);
        s.startBreak(5, t);
        check(s.paused(), "a break pauses the session");
        check(run(s, 5.05) == FocusSession.BREAK_OVER && !s.paused(), "the break ends and the session resumes");

        FocusSession saved = FocusSession.restore(s.save());
        check("coding".equals(saved.kind) && saved.left(t) == s.left(t), "survives an app restart");
        String json = s.toJson(t);
        check(json.startsWith("{\"active\":true,\"kind\":\"coding\"") && json.contains("\"breakSeq\":1"), "state for the page: " + json);

        System.out.println(failures == 0 ? "\nall passed" : "\n" + failures + " failed");
        System.exit(failures == 0 ? 0 : 1);
    }
}
