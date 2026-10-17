package local.jarvis.assistant;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;

/**
 * Study Buddy floating over other apps, and focus sessions (coding or study) that keep going while
 * Jarvis is in the background.
 *
 * Runs only while you use it: the floating Study Buddy (after you turn it on and allow "Display over
 * other apps"), or a focus session or break. Android requires a notification while it runs.
 * Reminders come from Jarvis's own activity only (FocusSession.java): taps, typing and scrolling in
 * Jarvis, reported by the page. It never looks at other apps, the screen, keystrokes or notifications.
 */
public class CompanionService extends Service {
    static final String ACTION_SHOW = "show", ACTION_HIDE = "hide", ACTION_POSE = "pose", ACTION_SESSION = "session",
            ACTION_STOP_SESSION = "stop-session", ACTION_PAUSE = "pause", ACTION_SNOOZE = "snooze", ACTION_BREAK = "break",
            ACTION_APP = "app";
    private static final String CH_RUNNING = "companion", CH_FOCUS = "focus";
    private static final int ID_RUNNING = 1, ID_FOCUS = 2;

    static volatile boolean appVisible = false;
    private static FocusSession session;
    private static long lastSaved = 0;
    private static volatile CompanionService instance;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Random random = new Random();
    private SharedPreferences prefs;
    private WindowManager wm;
    private LinearLayout window;
    private ImageView pet;
    private TextView bubble;
    private LinearLayout menu;
    private WindowManager.LayoutParams lp;
    private boolean overlay = false;
    private String pack = "study-buddy-2", pose = "", basePose = "study";
    private final Map<String, Bitmap> bitmaps = new HashMap<String, Bitmap>();
    private JSONObject packs;
    private Bitmap open, half, shut;
    private final long started = System.currentTimeMillis();
    private long reactionAt = 0, overrideUntil = 0, nextBlink = 0, blinkAt = -1, nextNod = 0, nodAt = -1;
    private String reaction = "", overridePose = "";
    private float tilt = 0;
    private String lang = "en";

    // ---------------------------------------------------------------- the session, shared with the page (MainActivity.Bridge)
    static synchronized FocusSession session(Context c) {
        if (session == null) {
            session = FocusSession.restore(c.getSharedPreferences("jarvis", MODE_PRIVATE).getString("focus_session", null));
        }
        return session;
    }

    static synchronized void saveSession(Context c, boolean now) {
        long t = System.currentTimeMillis();
        if (session != null && (now || t - lastSaved > 15000)) {
            lastSaved = t;
            c.getSharedPreferences("jarvis", MODE_PRIVATE).edit().putString("focus_session", session.save()).apply();
        }
    }

    /** The page reports that you did something in Jarvis (throttled there). */
    static void activity(Context c) {
        int back;
        synchronized (CompanionService.class) {
            back = session(c).activity(System.currentTimeMillis());
        }
        saveSession(c, false);
        final CompanionService s = instance;
        if (back != 0 && s != null) {
            s.ui.post(new Runnable() {
                @Override
                public void run() {
                    s.cancelAlert();
                    s.flash("cheer", 3000);
                }
            });
        }
    }

    static synchronized String stateJson(Context c) {
        return session(c).toJson(System.currentTimeMillis());
    }

    static boolean running() {
        return instance != null;
    }

    /** Called by MainActivity when Jarvis comes to the front or goes to the background. */
    static void setAppVisible(boolean visible) {
        appVisible = visible;
        final CompanionService s = instance;
        if (s != null) {
            s.ui.post(new Runnable() {
                @Override
                public void run() {
                    s.updateVisibility();
                }
            });
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("jarvis", MODE_PRIVATE);
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        pack = prefs.getString("overlay_pack", pack);
        overlay = prefs.getBoolean("overlay", false);
        channels();
        instance = this;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        foreground();
        String action = intent == null ? ACTION_SHOW : String.valueOf(intent.getAction());
        if (intent != null && intent.hasExtra("lang")) {
            lang = "ja".equals(intent.getStringExtra("lang")) ? "ja" : "en";
        }
        long now = System.currentTimeMillis();
        FocusSession s = session(this);
        synchronized (CompanionService.class) {
            if (ACTION_SHOW.equals(action)) {
                if (intent != null && intent.hasExtra("pack")) {
                    setPack(intent.getStringExtra("pack"));
                }
                overlay = true;
                prefs.edit().putBoolean("overlay", true).apply();
                showWindow();
            } else if (ACTION_HIDE.equals(action)) {
                overlay = false;
                prefs.edit().putBoolean("overlay", false).apply();
                removeWindow();
            } else if (ACTION_POSE.equals(action) && intent != null) {
                setPack(intent.getStringExtra("pack"));
                basePose = valid(intent.getStringExtra("pose"));
            } else if (ACTION_SESSION.equals(action) && intent != null) {
                s.start(intent.getStringExtra("kind"), Math.max(1, intent.getIntExtra("minutes", 25)),
                        intent.getIntExtra("grace", 5), intent.getIntExtra("cooldown", 15), now);
                cancelAlert();
            } else if (ACTION_STOP_SESSION.equals(action)) {
                s.stop();
                cancelAlert();
            } else if (ACTION_PAUSE.equals(action) && intent != null) {
                boolean pause = intent.hasExtra("paused") ? intent.getBooleanExtra("paused", true) : !s.paused(); // from a notification: toggle
                s.pause(pause, now);
                cancelAlert();
            } else if (ACTION_SNOOZE.equals(action) && intent != null) {
                s.snooze(intent.getIntExtra("minutes", 15), now);
                cancelAlert();
            } else if (ACTION_BREAK.equals(action) && intent != null) {
                s.startBreak(intent.getIntExtra("minutes", 5), now);
                cancelAlert();
                if (s.inBreak(now)) {
                    say(t("Break time! Stand up, drink water, look far away.", "休憩！立って、水を飲んで、遠くを見よう。"), 8000);
                }
            } else if (ACTION_APP.equals(action)) {
                updateVisibility();
            }
        }
        saveSession(this, true);
        if (!overlay && !s.active() && !s.inBreak(now)) {
            stopSelf(); // nothing to do: no floating Study Buddy, no session
            return START_NOT_STICKY;
        }
        foreground(); // refresh the notification text
        ui.removeCallbacks(focusTick);
        ui.post(focusTick);
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        instance = null;
        ui.removeCallbacksAndMessages(null);
        removeWindow();
        saveSession(this, true);
        super.onDestroy();
    }

    // ---------------------------------------------------------------- notifications
    private void channels() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel(CH_RUNNING, "Study Buddy", NotificationManager.IMPORTANCE_MIN));
        nm.createNotificationChannel(new NotificationChannel(CH_FOCUS, "Focus session reminders", NotificationManager.IMPORTANCE_DEFAULT));
    }

    private PendingIntent self(String action, int minutes, int code) {
        Intent i = new Intent(this, CompanionService.class).setAction(action).putExtra("minutes", minutes);
        return PendingIntent.getService(this, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private PendingIntent openApp() {
        Intent i = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(this, 10, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private Notification.Action action(String label, PendingIntent intent) {
        return new Notification.Action.Builder(null, label, intent).build();
    }

    private String kindName(String kind) {
        return "study".equals(kind) ? t("Study", "学習") : t("Coding", "コーディング");
    }

    private void foreground() {
        FocusSession s = session(this);
        long now = System.currentTimeMillis();
        String text;
        if (s.inBreak(now)) {
            text = t("Break: " + minutes(s.breakEnds - now) + " min left", "休憩：残り" + minutes(s.breakEnds - now) + "分");
        } else if (s.paused()) {
            text = t(kindName(s.kind) + " session paused", kindName(s.kind) + "セッション一時停止中");
        } else if (s.active()) {
            text = t(kindName(s.kind) + " session: " + minutes(s.left(now)) + " min left", kindName(s.kind) + "セッション：残り" + minutes(s.left(now)) + "分");
        } else {
            text = t("Study Buddy is floating. Tap to open Jarvis.", "スタディバディが表示中。タップでJarvisを開く。");
        }
        Notification.Builder b = new Notification.Builder(this, CH_RUNNING)
                .setSmallIcon(android.R.drawable.star_on)
                .setContentTitle(t("Study Buddy", "スタディバディ"))
                .setContentText(text)
                .setContentIntent(openApp())
                .setOngoing(true);
        if (s.active()) {
            b.addAction(action(s.paused() ? t("Resume", "再開") : t("Pause", "一時停止"), self(ACTION_PAUSE, 0, 2)));
            b.addAction(action(t("End session", "セッション終了"), self(ACTION_STOP_SESSION, 0, 3)));
        }
        if (overlay) {
            b.addAction(action(t("Hide", "隠す"), self(ACTION_HIDE, 0, 1)));
        }
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(ID_RUNNING, b.build(), 0x40000000); // ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        } else {
            startForeground(ID_RUNNING, b.build());
        }
    }

    private void alert(String text, boolean nudge) {
        Notification.Builder b = new Notification.Builder(this, CH_FOCUS)
                .setSmallIcon(android.R.drawable.star_on)
                .setContentTitle(t("Study Buddy", "スタディバディ"))
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(openApp())
                .setAutoCancel(true);
        if (nudge) {
            b.addAction(action(t("Snooze 15 min", "15分スヌーズ"), self(ACTION_SNOOZE, 15, 4)));
            b.addAction(action(t("Pause", "一時停止"), self(ACTION_PAUSE, 0, 5)));
            b.addAction(action(t("End session", "セッション終了"), self(ACTION_STOP_SESSION, 0, 6)));
        } else {
            b.addAction(action(t("5-minute break", "5分休憩"), self(ACTION_BREAK, 5, 7)));
        }
        try {
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(ID_FOCUS, b.build());
        } catch (SecurityException ignored) {
            // notifications not allowed: Study Buddy still reacts on screen
        }
    }

    private void cancelAlert() {
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).cancel(ID_FOCUS);
    }

    private String t(String en, String ja) {
        return "ja".equals(lang) ? ja : en;
    }

    private static long minutes(long ms) {
        return Math.max(0, (ms + 59999) / 60000);
    }

    /** Every 5 seconds while a session or break runs: timers, the one reminder, the end of the session. */
    private final Runnable focusTick = new Runnable() {
        @Override
        public void run() {
            long now = System.currentTimeMillis();
            FocusSession s = session(CompanionService.this);
            int events;
            String kind;
            synchronized (CompanionService.class) {
                kind = s.kind;
                events = s.tick(now);
            }
            if ((events & FocusSession.NUDGE) != 0) {
                long m = s.inactiveFor(now) / 60000;
                String msg = t("Hmph! Nothing's happened in Jarvis for " + m + " min. Still with me?",
                        "むー！" + m + "分もJarvisで何もしてないよ。まだいる？");
                alert(msg, true);
                say(msg, 15000);
                saveSession(CompanionService.this, true);
            }
            if ((events & FocusSession.DONE) != 0) {
                String msg = t(kindName(kind) + " session done! Take a short break.", kindName(kind) + "セッション完了！少し休憩しよう。");
                flash("celebrate", 8000);
                say(msg, 9000);
                if (!appVisible) {
                    alert(msg, false);
                }
                saveSession(CompanionService.this, true);
            }
            if ((events & FocusSession.BREAK_OVER) != 0) {
                flash("cheer", 4000);
                say(t("Break over. Ready for one small step?", "休憩おしまい。小さな一歩からいこう。"), 7000);
            }
            if (events != 0) {
                foreground();
            }
            if (s.active() || s.inBreak(now)) {
                ui.postDelayed(this, 5000);
            } else if (!overlay) {
                stopSelf();
            }
        }
    };

    // ---------------------------------------------------------------- the floating window
    private void showWindow() {
        if (window != null || !Settings.canDrawOverlays(this)) {
            updateVisibility();
            return;
        }
        int size = dp(84);
        pet = new ImageView(this);
        pet.setScaleType(ImageView.ScaleType.FIT_CENTER);
        pet.setContentDescription(t("Study Buddy. Tap for quick actions, drag to move.", "スタディバディ。タップでメニュー、ドラッグで移動。"));
        bubble = new TextView(this);
        bubble.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        bubble.setTextColor(Color.parseColor("#1c2330"));
        bubble.setPadding(dp(10), dp(7), dp(10), dp(7));
        bubble.setMaxWidth(dp(220));
        bubble.setBackground(round("#ffffff"));
        bubble.setVisibility(View.GONE);
        menu = new LinearLayout(this);
        menu.setOrientation(LinearLayout.VERTICAL);
        menu.setBackground(round("#ffffff"));
        menu.setPadding(dp(4), dp(4), dp(4), dp(4));
        menu.setVisibility(View.GONE);
        window = new LinearLayout(this);
        window.setOrientation(LinearLayout.VERTICAL);
        window.setGravity(Gravity.CENTER_HORIZONTAL);
        window.addView(pet, new LinearLayout.LayoutParams(size, size));
        LinearLayout.LayoutParams gap = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        gap.topMargin = dp(4);
        window.addView(bubble, gap);
        window.addView(menu, gap);
        lp = new WindowManager.LayoutParams(WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = prefs.getInt("overlay_x", getResources().getDisplayMetrics().widthPixels - size - dp(12));
        lp.y = prefs.getInt("overlay_y", getResources().getDisplayMetrics().heightPixels / 2);
        pet.setOnTouchListener(new Drag());
        try {
            wm.addView(window, lp);
        } catch (Exception e) {
            window = null; // permission was revoked
            return;
        }
        pose = "";
        updateVisibility();
    }

    /** Her quick actions, built fresh each time (they depend on the session). */
    private void fillMenu() {
        menu.removeAllViews();
        final FocusSession s = session(this);
        long now = System.currentTimeMillis();
        menu.addView(menuItem(t("Open Jarvis", "Jarvisを開く"), new Runnable() {
            @Override
            public void run() {
                try {
                    openApp().send();
                } catch (Exception ignored) {
                    // can't open
                }
            }
        }));
        if (s.active()) {
            menu.addView(menuItem(s.paused() ? t("Resume the session", "セッションを再開") : t("Pause the session", "セッションを一時停止"),
                    command(new Intent(ACTION_PAUSE).putExtra("paused", !s.paused()))));
            menu.addView(menuItem(t("No reminders for 15 min", "15分リマインドなし"), command(new Intent(ACTION_SNOOZE).putExtra("minutes", 15))));
            menu.addView(menuItem(t("End the session", "セッションを終わる"), command(new Intent(ACTION_STOP_SESSION))));
        }
        menu.addView(menuItem(s.inBreak(now) ? t("End the break", "休憩を終わる") : t("5-minute break", "5分休憩"),
                command(new Intent(ACTION_BREAK).putExtra("minutes", s.inBreak(now) ? 0 : 5))));
        menu.addView(menuItem(t("Hide Study Buddy", "スタディバディを隠す"), command(new Intent(ACTION_HIDE))));
    }

    private Runnable command(final Intent intent) {
        return new Runnable() {
            @Override
            public void run() {
                intent.setClass(CompanionService.this, CompanionService.class);
                startService(intent);
            }
        };
    }

    private void removeWindow() {
        ui.removeCallbacks(frame);
        if (window != null) {
            try {
                wm.removeView(window);
            } catch (Exception ignored) {
                // already gone
            }
        }
        window = null;
    }

    /** Inside Jarvis the page shows its own Study Buddy, so the floating one waits outside. */
    private void updateVisibility() {
        if (window == null) {
            return;
        }
        window.setVisibility(appVisible ? View.GONE : View.VISIBLE);
        ui.removeCallbacks(frame);
        if (!appVisible) {
            ui.post(frame);
        }
    }

    private GradientDrawable round(String color) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(Color.parseColor(color));
        d.setCornerRadius(dp(14));
        d.setStroke(dp(1), Color.parseColor("#dde1e7"));
        return d;
    }

    private TextView menuItem(String label, final Runnable action) {
        TextView v = new TextView(this);
        v.setText(label);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        v.setTextColor(Color.parseColor("#1c2330"));
        v.setPadding(dp(12), dp(10), dp(12), dp(10));
        v.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                menu.setVisibility(View.GONE);
                action.run();
            }
        });
        return v;
    }

    private void say(String text, long ms) {
        if (bubble == null) {
            return;
        }
        bubble.setText(text);
        bubble.setVisibility(View.VISIBLE);
        react("talk");
        ui.removeCallbacks(hideBubble);
        ui.postDelayed(hideBubble, ms);
    }

    private final Runnable hideBubble = new Runnable() {
        @Override
        public void run() {
            if (bubble != null) {
                bubble.setVisibility(View.GONE);
            }
        }
    };

    private void flash(String p, long ms) {
        overridePose = p;
        overrideUntil = System.currentTimeMillis() + ms;
    }

    private void react(String kind) {
        reaction = kind;
        reactionAt = System.currentTimeMillis();
    }

    private class Drag implements View.OnTouchListener {
        private float downX, downY, lastX;
        private int startX, startY;
        private long lastT;
        private boolean moved;

        @Override
        public boolean onTouch(View v, MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    downX = e.getRawX();
                    downY = e.getRawY();
                    lastX = downX;
                    lastT = System.currentTimeMillis();
                    startX = lp.x;
                    startY = lp.y;
                    moved = false;
                    return true;
                case MotionEvent.ACTION_MOVE:
                    float dx = e.getRawX() - downX, dy = e.getRawY() - downY;
                    if (!moved && Math.hypot(dx, dy) < dp(8)) {
                        return true;
                    }
                    moved = true;
                    long now = System.currentTimeMillis();
                    float vx = (e.getRawX() - lastX) / Math.max(8, now - lastT);
                    lastX = e.getRawX();
                    lastT = now;
                    tilt = Math.max(-20, Math.min(20, -vx * 18));
                    lp.x = startX + (int) dx;
                    lp.y = startY + (int) dy;
                    try {
                        wm.updateViewLayout(window, lp);
                    } catch (Exception ignored) {
                        // window gone
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    tilt = 0;
                    if (moved) {
                        prefs.edit().putInt("overlay_x", lp.x).putInt("overlay_y", lp.y).apply();
                        react("land");
                    } else if (e.getActionMasked() == MotionEvent.ACTION_UP) {
                        if (menu.getVisibility() == View.VISIBLE) {
                            menu.setVisibility(View.GONE);
                        } else {
                            fillMenu();
                            menu.setVisibility(View.VISIBLE);
                        }
                        bubble.setVisibility(View.GONE);
                        react("pop");
                        v.performClick();
                    }
                    return true;
                default:
                    return false;
            }
        }
    }

    // ---------------------------------------------------------------- her expression and motion (30 frames a second while visible)
    private String poseNow(long now) {
        if (now < overrideUntil) {
            return overridePose;
        }
        FocusSession s = session(this);
        if (s.inBreak(now)) {
            return "relax";
        }
        if (s.active()) {
            if (s.pouting(now)) {
                return "pouty";
            }
            return s.paused() ? "study" : "study".equals(s.kind) ? "study" : "code";
        }
        return basePose;
    }

    private final Runnable frame = new Runnable() {
        @Override
        public void run() {
            if (window == null || appVisible) {
                return;
            }
            long now = System.currentTimeMillis();
            String want = poseNow(now);
            if (!want.equals(pose)) {
                setPicture(want);
                if (!pose.isEmpty()) {
                    react("pouty".equals(want) ? "shake" : "celebrate".equals(want) ? "jump" : "pop");
                }
                pose = want;
                nextBlink = now + 1500 + random.nextInt(3000);
                nextNod = now + 4000 + random.nextInt(5000);
            }
            // blink: half closed, closed, half closed (about a fifth of a second), every few seconds
            if (half != null || shut != null) {
                if (blinkAt < 0 && now >= nextBlink) {
                    blinkAt = now;
                }
                if (blinkAt >= 0) {
                    long b = now - blinkAt;
                    Bitmap show = b < 60 ? (half != null ? half : shut) : b < 150 ? shut : b < 210 ? (half != null ? half : shut) : open;
                    pet.setImageBitmap(show);
                    if (b >= 210) {
                        blinkAt = -1;
                        nextBlink = now + 2500 + random.nextInt(4000) - (random.nextInt(5) == 0 ? 2300 : 0); // sometimes a double blink
                    }
                }
            }
            float t = (now - started) / 1000f;
            float breathe = "code".equals(pose) ? 2.4f : "relax".equals(pose) || "sleepy".equals(pose) ? 5.5f : "pouty".equals(pose) ? 1.8f
                    : "celebrate".equals(pose) ? 1.1f : 3.6f;
            float k = (float) (1 - Math.cos(2 * Math.PI * t / breathe)) / 2; // 0..1..0
            float sx = 1 - 0.01f * k, sy = 1 + 0.022f * k, ty = -dp(4) * k;
            float rot = (float) (1.6 * Math.sin(2 * Math.PI * t / 6));
            if ("code".equals(pose)) { // typing: a quick small bob, leaning toward the screen
                ty = (float) (-dp(2) * Math.abs(Math.sin(2 * Math.PI * t / 0.9)));
                rot = (float) (-1.5 + 0.8 * Math.sin(2 * Math.PI * t / 4.5));
            } else if ("celebrate".equals(pose) || "cheer".equals(pose)) {
                ty = -dp(10) * k;
            } else if ("pouty".equals(pose)) {
                rot = (float) (3 * Math.sin(2 * Math.PI * t / 1.8));
                sx = 1 + 0.04f * k;
                sy = 1 - 0.03f * k;
            } else if ("sleepy".equals(pose) || "relax".equals(pose)) {
                rot = (float) (-2.5 + 1.5 * Math.sin(2 * Math.PI * t / 7));
            } else if ("idea".equals(pose)) {
                rot = (float) (-4 * (1 - Math.cos(2 * Math.PI * t / 5)) / 2);
            }
            if ("study".equals(pose)) { // an occasional thoughtful nod
                if (nodAt < 0 && now >= nextNod) {
                    nodAt = now;
                }
                if (nodAt >= 0) {
                    float n = (now - nodAt) / 1000f;
                    rot += (float) (5 * Math.sin(Math.PI * Math.min(1, n / 0.9)));
                    if (n > 0.9) {
                        nodAt = -1;
                        nextNod = now + 6000 + random.nextInt(6000);
                    }
                }
            }
            float p = (now - reactionAt) / 1000f; // one-off reactions
            if ("pop".equals(reaction) || "talk".equals(reaction) || "land".equals(reaction)) {
                if (p < 0.6f) {
                    float s = (float) (Math.sin(p / 0.6 * 3 * Math.PI) * (1 - p / 0.6) * ("talk".equals(reaction) ? 0.04 : 0.13));
                    sx *= 1 + s;
                    sy *= 1 - s;
                }
            } else if ("jump".equals(reaction) && p < 0.9f) {
                ty -= (float) (dp(30) * Math.sin(Math.PI * p / 0.9));
            } else if ("shake".equals(reaction) && p < 0.55f) {
                rot += (float) (5 * Math.sin(p * 40) * (1 - p / 0.55));
            }
            pet.setPivotX(pet.getWidth() / 2f);
            pet.setPivotY(pet.getHeight() * 0.95f);
            pet.setScaleX(sx);
            pet.setScaleY(sy);
            pet.setTranslationY(ty);
            pet.setRotation(rot + tilt);
            ui.postDelayed(this, 33);
        }
    };

    // ---------------------------------------------------------------- pictures (assets/companion, the same as the page)
    private static String valid(String p) {
        return p != null && p.matches("cheer|code|study|idea|sleepy|celebrate|pouty|care|relax") ? p : "study";
    }

    private void setPack(String p) {
        if (p != null && p.matches("study-buddy-\\d") && !p.equals(pack)) {
            pack = p;
            prefs.edit().putString("overlay_pack", p).apply();
            pose = ""; // redraw
        }
    }

    /** Her picture for a pose, and its blink frames when the art has them. */
    private void setPicture(String want) {
        open = null;
        half = null;
        shut = null;
        blinkAt = -1;
        try {
            if (packs == null) {
                packs = new JSONObject(readAsset("companion/packs.json"));
            }
            String[] order = "care".equals(want) ? new String[]{"cheer", "idea"} : "celebrate".equals(want) ? new String[]{"celebrate", "cheer"}
                    : "relax".equals(want) ? new String[]{"relax", "sleepy"} : new String[]{want, "study"};
            JSONArray list = packs.getJSONArray("packs");
            for (int i = 0; i < list.length(); i++) {
                JSONObject pk = list.getJSONObject(i);
                if (!pk.getString("id").equals(pack)) {
                    continue;
                }
                JSONArray items = pk.getJSONArray("items");
                JSONObject found = items.getJSONObject(0);
                search:
                for (String o : order) {
                    for (int j = 0; j < items.length(); j++) {
                        if (o.equals(items.getJSONObject(j).getString("mood"))) {
                            found = items.getJSONObject(j);
                            break search;
                        }
                    }
                }
                open = bitmap(found.getString("file"));
                half = found.has("half") ? bitmap(found.getString("half")) : null;
                shut = found.has("blink") ? bitmap(found.getString("blink")) : null;
            }
        } catch (Exception ignored) {
            // missing or unreadable pictures
        }
        if (open != null) {
            pet.setImageBitmap(open);
        }
    }

    private Bitmap bitmap(String file) throws Exception {
        Bitmap b = bitmaps.get(file);
        if (b == null) {
            try (InputStream in = getAssets().open("companion/" + file)) {
                b = BitmapFactory.decodeStream(in);
            }
            bitmaps.put(file, b);
        }
        return b;
    }

    private String readAsset(String name) throws Exception {
        try (InputStream in = getAssets().open(name)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        }
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
