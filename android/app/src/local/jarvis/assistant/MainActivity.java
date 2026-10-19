package local.jarvis.assistant;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.pm.PackageManager;
import android.content.ClipData;
import android.content.ContentValues;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslCertificate;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.Settings;
import android.text.InputType;
import android.webkit.JavascriptInterface;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.Socket;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.HttpsURLConnection;

/**
 * Jarvis for Android: shows the Jarvis mobile app served by your computer.
 *
 * The app only talks to the address you configure (your computer), only over HTTPS,
 * and only trusts the certificate authority created by that computer's Jarvis
 * (see res/xml/network_security_config.xml). Links to anything else open in your browser.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "jarvis";
    private static final int PICK_PICTURES = 41;
    private static final int TERMUX_PERMISSION = 42;
    private static final int POCKET_TOKEN = 43;
    private static final int POCKET_START = 44;
    private static final int NOTIFICATIONS = 45;
    private static final String TERMUX = "com.termux";
    private static final String RUN_COMMAND = "com.termux.permission.RUN_COMMAND";
    private static final String POCKET_DIR = "/data/data/com.termux/files/home/jarvis-pocket";
    private static final String POCKET_HOST = "localhost:8766";
    private static final String POCKET_URL = "http://" + POCKET_HOST + "/m/";
    private long pausedAt = 0;
    private boolean pocketPending = false;
    private WebView web;
    private SharedPreferences prefs;
    private SharedPreferences data; // the web app's pairing and offline copies (see Bridge)
    private X509Certificate jarvisCa;
    private ValueCallback<Uri[]> pictureCallback;
    private Uri cameraUri;
    private volatile String currentUrl = "";
    private volatile boolean scanning = false;
    private volatile String pocketProblem = null; // set when Termux reports that starting Jarvis failed

    @Override
    protected void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        // 1.6.2: the phone is independent: "Automatic" (laptop when reachable) becomes "This phone" once.
        // Choosing Laptop or Automatic again in More > Where Jarvis runs still works.
        if (!prefs.getBoolean("independent_since_1_6_2", false)) {
            SharedPreferences.Editor e = prefs.edit().putBoolean("independent_since_1_6_2", true);
            if (termuxInstalled() && !"laptop".equals(prefs.getString("mode", ""))) {
                e.putString("mode", "phone");
            }
            e.apply();
        }
        data = getSharedPreferences("jarvis_web_data", MODE_PRIVATE);
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true); // only in test builds
        }
        web = new WebView(this);
        web.setBackgroundColor(isNight() ? Color.parseColor("#12151b") : Color.parseColor("#f6f7f9"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setMediaPlaybackRequiresUserGesture(false); // Study Buddy's recorded voice (only Jarvis pages load here)
        s.setSupportMultipleWindows(false);
        s.setUserAgentString(s.getUserAgentString() + " JarvisApp/" + versionName());
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.addJavascriptInterface(new Bridge(), "JarvisNative");
        FrameLayout root = new FrameLayout(this);
        root.addView(web);
        setContentView(root);
        if (savedState == null || web.restoreState(savedState) == null) {
            chooseAndOpen();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        pausedAt = System.currentTimeMillis();
        CompanionService.setAppVisible(false); // the floating Study Buddy appears over other apps
    }

    @Override
    protected void onResume() {
        super.onResume();
        CompanionService.setAppVisible(true);
        if (prefs.getBoolean("overlay", false) || prefs.getBoolean("overlay_wanted", false)) {
            if (Settings.canDrawOverlays(this)) {
                prefs.edit().remove("overlay_wanted").apply();
                if (!CompanionService.running()) {
                    companion(new Intent(CompanionService.ACTION_SHOW));
                }
            } else {
                prefs.edit().putBoolean("overlay", false).remove("overlay_wanted").apply(); // permission not given
            }
        }
        if (pausedAt <= 0) {
            return;
        }
        // Back after a while: check again whether the laptop or this phone should answer.
        long away = System.currentTimeMillis() - pausedAt;
        if (away > 10 * 60 * 1000) {
            chooseAndOpen();
        } else {
            if (onPocket() && away > 20000) {
                wakePocket(); // Android may have frozen Termux meanwhile
            }
            if ("auto".equals(mode()) && onPocket()) {
                switchToLaptopIfReachable(); // e.g. the laptop was off and has been turned on since
            }
        }
    }

    private long lastWake = 0;

    /**
     * Runs the start script quietly, without changing the page. Android (HyperOS especially) freezes
     * Termux in the background, and a frozen Jarvis takes connections but never answers: this wakes
     * Termux up, and the script replaces a Jarvis that is still stuck. At most every 15 seconds.
     */
    private void wakePocket() {
        long now = System.currentTimeMillis();
        if (now - lastWake < 15000 || !termuxInstalled() || checkSelfPermission(RUN_COMMAND) != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        lastWake = now;
        Intent start = new Intent("com.termux.RUN_COMMAND");
        start.setClassName(TERMUX, "com.termux.app.RunCommandService");
        start.putExtra("com.termux.RUN_COMMAND_PATH", POCKET_DIR + "/start");
        start.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
        start.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
        start.putExtra("com.termux.RUN_COMMAND_COMMAND_LABEL", "Jarvis");
        try {
            startForegroundService(start);
        } catch (Exception ignored) {
            // Termux couldn't be asked; the page keeps retrying
        }
    }

    // ---------------------------------------------------------------- laptop or this phone
    private String mode() {
        // auto | laptop | phone. With Termux set up, this phone's own Jarvis answers unless you choose otherwise.
        return prefs.getString("mode", termuxInstalled() ? "phone" : "auto");
    }

    // ---------------------------------------------------------------- Study Buddy over other apps
    private void companion(final Intent intent) {
        intent.setClass(this, CompanionService.class);
        intent.putExtra("lang", prefs.getString("lang", "en"));
        runOnUiThread(new Runnable() { // the page calls in from its own thread
            @Override
            public void run() {
                try {
                    startForegroundService(intent);
                } catch (Exception e) {
                    Toast.makeText(MainActivity.this, "Study Buddy couldn't start: " + e.getMessage(), Toast.LENGTH_LONG).show();
                }
            }
        });
    }

    private void askForNotifications() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, NOTIFICATIONS);
        }
    }

    /** Runs one allowed request against Jarvis on this phone (Termux), starting it first if needed. */
    private void pocketRequest(String method, String path, String body, String id) {
        String token = data.getString("phone/jarvis.deviceToken", "");
        if (token.isEmpty()) {
            answer(id, 409, "{\"detail\":\"Jarvis on this phone isn't set up in the app yet. Open the menu and choose 'This phone' once.\"}");
            return;
        }
        if (!canConnect("127.0.0.1:8766", 500)) {
            if (!termuxInstalled() || checkSelfPermission(RUN_COMMAND) != PackageManager.PERMISSION_GRANTED) {
                answer(id, 409, "{\"detail\":\"Jarvis on this phone needs Termux and the permission to start it. Choose 'This phone' once in the menu.\"}");
                return;
            }
            Intent start = new Intent("com.termux.RUN_COMMAND");
            start.setClassName(TERMUX, "com.termux.app.RunCommandService");
            start.putExtra("com.termux.RUN_COMMAND_PATH", POCKET_DIR + "/start");
            start.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
            start.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
            try {
                startForegroundService(start);
            } catch (Exception e) {
                answer(id, 503, "{\"detail\":\"Couldn't start Jarvis on this phone.\"}");
                return;
            }
            long deadline = System.currentTimeMillis() + 75000;
            while (!canConnect("127.0.0.1:8766", 500)) {
                if (System.currentTimeMillis() > deadline) {
                    answer(id, 504, "{\"detail\":\"Jarvis on this phone didn't start within 75 seconds.\"}");
                    return;
                }
                try {
                    Thread.sleep(700);
                } catch (InterruptedException e) {
                    return;
                }
            }
        }
        try {
            HttpURLConnection c = (HttpURLConnection) new URL("http://localhost:8766" + path).openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(3000);
            c.setReadTimeout(90000);
            c.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null && !body.isEmpty()) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                try (OutputStream out = c.getOutputStream()) {
                    out.write(body.getBytes(StandardCharsets.UTF_8));
                }
            }
            int code = c.getResponseCode();
            InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            if (in != null) {
                byte[] chunk = new byte[8192];
                int n;
                while ((n = in.read(chunk)) > 0) {
                    buf.write(chunk, 0, n);
                }
                in.close();
            }
            c.disconnect();
            answer(id, code, new String(buf.toByteArray(), StandardCharsets.UTF_8));
        } catch (Exception e) {
            answer(id, 503, "{\"detail\":\"Jarvis on this phone didn't answer: " + e.getClass().getSimpleName() + "\"}");
        }
    }

    private void answer(final String id, final int status, final String text) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                web.evaluateJavascript("window.__jarvisPocketDone && window.__jarvisPocketDone(" + org.json.JSONObject.quote(id) + ","
                        + status + "," + org.json.JSONObject.quote(text) + ")", null);
            }
        });
    }

    private boolean termuxInstalled() {
        try {
            getPackageManager().getPackageInfo(TERMUX, 0);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private boolean onPocket() {
        try {
            return POCKET_HOST.equalsIgnoreCase(Uri.parse(currentUrl).getAuthority());
        } catch (Exception e) {
            return false;
        }
    }

    /** Auto mode: the laptop when it's reachable (bigger models), otherwise Jarvis on this phone. */
    private void chooseAndOpen() {
        final String m = mode();
        if ("laptop".equals(m) || !termuxInstalled()) {
            openHome();
            return;
        }
        if ("phone".equals(m)) {
            openPocket();
            return;
        }
        final String saved = address();
        new Thread(new Runnable() {
            @Override
            public void run() {
                final boolean laptop = laptopReachable(saved);
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (laptop) {
                            openHome();
                        } else {
                            openPocket();
                        }
                    }
                });
            }
        }, "jarvis-choose").start();
    }

    /** Two tries: a phone's Wi-Fi waking from power saving can be slow to make the first connection. */
    private static boolean laptopReachable(String hostPort) {
        return canConnect(hostPort, 1500) || canConnect(hostPort, 1500);
    }

    private void switchToLaptopIfReachable() {
        final String saved = address();
        new Thread(new Runnable() {
            @Override
            public void run() {
                if (!laptopReachable(saved)) {
                    return;
                }
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if ("auto".equals(mode()) && onPocket()) {
                            Toast.makeText(MainActivity.this, "Your laptop is reachable again, so it will answer (bigger models).",
                                    Toast.LENGTH_LONG).show();
                            openHome();
                        }
                    }
                });
            }
        }, "jarvis-laptop-check").start();
    }

    private static boolean canConnect(String hostPort, int timeoutMs) {
        Socket socket = new Socket();
        try {
            int colon = hostPort.lastIndexOf(':');
            socket.connect(new InetSocketAddress(hostPort.substring(0, colon), Integer.parseInt(hostPort.substring(colon + 1))), timeoutMs);
            return true;
        } catch (Exception e) {
            return false;
        } finally {
            try {
                socket.close();
            } catch (Exception ignored) {
                // closed
            }
        }
    }

    private void openPocket() {
        if (!termuxInstalled()) {
            Toast.makeText(this, "Jarvis on this phone needs Termux. See the README.", Toast.LENGTH_LONG).show();
            openHome();
            return;
        }
        if (checkSelfPermission(RUN_COMMAND) != PackageManager.PERMISSION_GRANTED) {
            pocketPending = true;
            requestPermissions(new String[]{RUN_COMMAND}, TERMUX_PERMISSION);
            return;
        }
        showStarting();
        pocketProblem = null;
        // Termux answers through these if a command can't start or ends (the start script normally keeps running).
        if (!runInTermux(POCKET_DIR + "/start", true, resultFor(POCKET_START))) { // starts Ollama + Jarvis if needed
            return;
        }
        if (data.getString("phone/jarvis.deviceToken", "").isEmpty()) {
            runInTermux(POCKET_DIR + "/pair", true, resultFor(POCKET_TOKEN)); // a key for this app, no pairing code needed
        } else {
            waitForPocketThenLoad();
        }
    }

    private PendingIntent resultFor(int requestCode) {
        return createPendingResult(requestCode, new Intent(),
                PendingIntent.FLAG_ONE_SHOT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0));
    }

    /** Termux's answer: its own error (e.g. permission), or the script's exit code and output. Empty if all is well. */
    private static String termuxProblem(Intent intent) {
        Bundle result = intent == null ? null : intent.getBundleExtra("result");
        if (result == null) {
            return "Termux didn't answer.";
        }
        int err = result.getInt("err", -1);
        if (err != -1) { // -1 means Termux started the command fine
            return "Termux refused to start it: " + result.getString("errmsg", "error " + err);
        }
        int exit = result.getInt("exitCode", 0);
        if (exit != 0) {
            String detail = (result.getString("stderr", "") + "\n" + result.getString("stdout", "")).trim();
            if (detail.length() > 400) {
                detail = "…" + detail.substring(detail.length() - 400);
            }
            return "It stopped with exit code " + exit + (detail.isEmpty() ? "." : ": " + detail);
        }
        return "";
    }

    private boolean runInTermux(String path, boolean background, PendingIntent result) {
        Intent intent = new Intent("com.termux.RUN_COMMAND");
        intent.setClassName(TERMUX, "com.termux.app.RunCommandService");
        intent.putExtra("com.termux.RUN_COMMAND_PATH", path);
        intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
        intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", background);
        intent.putExtra("com.termux.RUN_COMMAND_COMMAND_LABEL", "Jarvis");
        if (result != null) {
            intent.putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", result);
        }
        try {
            // Android 8+ only lets an app start another app's service while that app runs in the background
            // as a foreground service (Termux shows its notification right away).
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(intent);
            } else {
                startService(intent);
            }
            return true;
        } catch (Exception e) {
            showPocketProblem("The app couldn't ask Termux to start Jarvis: " + e.getMessage());
            return false;
        }
    }

    private void showPocketProblem(String reason) {
        pocketProblem = reason;
        boolean night = isNight();
        web.loadDataWithBaseURL(null, "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
                + "<body style='font-family:sans-serif;margin:0;padding:32px 22px;line-height:1.5;background:"
                + (night ? "#12151b;color:#e5e9f0" : "#f6f7f9;color:#1c2330") + "'>"
                + "<h2>Jarvis on this phone didn't start</h2>"
                + "<p style='padding:10px 12px;border-radius:12px;border:1px solid #8884;word-break:break-word'>" + escape(reason) + "</p>"
                + "<ul><li>Open Termux once and check that it starts normally.</li>"
                + "<li>Settings › Apps › Termux › Battery saver › <b>No restrictions</b>.</li>"
                + "<li>Details are in <code>jarvis-pocket/jarvis.log</code> inside Termux.</li></ul>"
                + "<a href='jarvisapp:use-phone' style='display:block;text-align:center;padding:13px;border-radius:12px;"
                + "background:#2f6fde;color:#fff;text-decoration:none;font-weight:600;margin-top:10px'>Try again</a>"
                + "<a href='jarvisapp:choose' style='display:block;text-align:center;padding:13px;border-radius:12px;"
                + "border:1px solid #8886;color:inherit;text-decoration:none;font-weight:600;margin-top:10px'>Check for the laptop</a>"
                + "</body></html>", "text/html", "utf-8", null);
    }

    private void waitForPocketThenLoad() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                long begin = System.currentTimeMillis();
                long deadline = begin + 90000; // first start loads Python and the model server
                // After the first visit the app's own copy of the page is saved on the phone (service worker),
                // so it can open at once, even offline, and connect when Jarvis has started.
                final boolean saved = prefs.getBoolean("pocket_shell", false);
                boolean up = false;
                while (!up && pocketProblem == null && System.currentTimeMillis() < deadline) {
                    if (saved && System.currentTimeMillis() - begin > 4000) {
                        runOnUiThread(new Runnable() {
                            @Override
                            public void run() {
                                web.clearHistory();
                                web.loadUrl(POCKET_URL);
                            }
                        });
                        return;
                    }
                    up = canConnect(POCKET_HOST.replace("localhost", "127.0.0.1"), 500);
                    if (!up) {
                        try {
                            Thread.sleep(700);
                        } catch (InterruptedException e) {
                            return;
                        }
                    }
                }
                final boolean ready = up;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (ready) {
                            prefs.edit().putBoolean("pocket_shell", true).apply();
                            web.clearHistory();
                            web.loadUrl(POCKET_URL);
                        } else if (pocketProblem == null) { // a reported problem is already on screen
                            showPocketProblem("It didn't answer within 90 seconds.");
                        }
                    }
                });
            }
        }, "jarvis-wait").start();
    }

    private void showStarting() {
        web.loadDataWithBaseURL(null, "<html><body style='font-family:sans-serif;background:" + (isNight() ? "#12151b;color:#e5e9f0" : "#f6f7f9;color:#1c2330")
                + ";display:flex;align-items:center;justify-content:center;height:90vh;text-align:center'><div><h2>Starting Jarvis on this phone\u2026</h2>"
                + "<p style='opacity:.7'>" + ("phone".equals(mode()) ? "You chose to use the Jarvis on this phone."
                        : "Couldn't reach Jarvis on your laptop (it may be off, asleep, or on another Wi-Fi), "
                        + "so this phone's own Jarvis will answer.") + "</p>"
                + "<p style='opacity:.7;font-size:14px'>The first start can take up to a minute.</p>"
                + "<p><a href='jarvisapp:choose' style='color:#5b93f0'>Check for the laptop again</a></p></div></body></html>",
                "text/html", "utf-8", null);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        if (requestCode == TERMUX_PERMISSION) {
            boolean granted = results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED;
            if (granted && pocketPending) {
                pocketPending = false;
                openPocket();
            } else if (!granted) {
                Toast.makeText(this, "Without that permission the app can't start Jarvis on this phone.", Toast.LENGTH_LONG).show();
                openHome();
            }
            return;
        }
        if (requestCode == NOTIFICATIONS) {
            return; // without it Study Buddy still shows on screen; reminders just won't appear as notifications
        }
        super.onRequestPermissionsResult(requestCode, permissions, results);
    }

    private void setMode(String m) {
        prefs.edit().putString("mode", m).apply();
        Toast.makeText(this, "laptop".equals(m) ? "Using Jarvis on your laptop" : "phone".equals(m)
                ? "Using Jarvis on this phone" : "Automatic: laptop when reachable, otherwise this phone", Toast.LENGTH_SHORT).show();
        if ("laptop".equals(m)) {
            openHome();
        } else if ("phone".equals(m)) {
            openPocket();
        } else {
            chooseAndOpen();
        }
    }

    private boolean isNight() {
        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "1";
        }
    }

    private String address() {
        return prefs.getString("address", getString(R.string.default_address));
    }

    private void openHome() {
        web.loadUrl("https://" + address() + "/m/");
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }

    private boolean isJarvis(Uri uri) {
        if ("https".equals(uri.getScheme()) && address().equalsIgnoreCase(uri.getAuthority())) {
            return true; // Jarvis on the laptop
        }
        return "http".equals(uri.getScheme()) && POCKET_HOST.equalsIgnoreCase(uri.getAuthority()); // on this phone
    }

    private class Client extends WebViewClient {
        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            currentUrl = url == null ? "" : url;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            currentUrl = url == null ? "" : url;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if ("jarvisapp".equals(uri.getScheme())) {
                String what = uri.getSchemeSpecificPart();
                if ("address".equals(what)) {
                    askForAddress();
                } else if (what != null && what.startsWith("use-")) {
                    setMode(what.substring(4));
                } else if ("find".equals(what)) {
                    findComputer(true);
                } else if ("choose".equals(what)) {
                    chooseAndOpen();
                } else {
                    openHome();
                }
                return true;
            }
            if (isJarvis(uri)) {
                return false;
            }
            try { // links in answers open in the phone's own browser, never inside the app
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (Exception ignored) {
                // no app can open it
            }
            return true;
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (!request.isForMainFrame()) {
                return;
            }
            if (POCKET_HOST.equalsIgnoreCase(request.getUrl().getAuthority())) {
                showPocketProblem("Jarvis on this phone stopped answering (" + error.getDescription() + ").");
                return;
            }
            showOffline(String.valueOf(error.getDescription()));
            findComputer(false); // maybe the computer got a new address on the Wi-Fi
        }

        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
            // Normally never reached: the network security config already trusts this computer's
            // Jarvis CA. As a fallback, accept only certificates signed by that same CA.
            if (isJarvis(Uri.parse(error.getUrl())) && issuedByJarvis(error.getCertificate())) {
                handler.proceed();
            } else {
                handler.cancel();
                showOffline("The server's security certificate was not issued by Jarvis on your computer, "
                        + "so the app refused to connect.");
            }
        }
    }

    /**
     * Lets the Jarvis page keep its pairing and offline copies in the app's own storage, so they
     * survive if the computer's address changes (browser storage is tied to the address).
     * Only the Jarvis page (the configured computer address) can use it.
     */
    private class Bridge {
        private boolean allowed() {
            try {
                return isJarvis(Uri.parse(currentUrl));
            } catch (Exception e) {
                return false;
            }
        }

        /** Jarvis on the laptop and Jarvis on this phone each keep their own key and offline copies. */
        private String ns(String key) {
            return (onPocket() ? "phone/" : "") + key;
        }

        @JavascriptInterface
        public String load(String key) {
            return allowed() && key != null ? data.getString(ns(key), "") : "";
        }

        @JavascriptInterface
        public void save(String key, String value) {
            if (allowed() && key != null) {
                data.edit().putString(ns(key), value).apply();
            }
        }

        @JavascriptInterface
        public void remove(String key) {
            if (allowed() && key != null) {
                data.edit().remove(ns(key)).apply();
            }
        }

        @JavascriptInterface
        public String where() {
            return onPocket() ? "phone" : "laptop";
        }

        @JavascriptInterface
        public String mode() {
            return MainActivity.this.mode();
        }

        @JavascriptInterface
        public void findComputer() {
            if (allowed()) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        MainActivity.this.findComputer(true);
                    }
                });
            }
        }

        // ---- Study Buddy over other apps, and Coding Focus on the phone (see CompanionService)
        @JavascriptInterface
        public boolean overlayEnabled() {
            return allowed() && prefs.getBoolean("overlay", false) && Settings.canDrawOverlays(MainActivity.this);
        }

        @JavascriptInterface
        public void setOverlay(final boolean on, final String pack) {
            if (!allowed()) {
                return;
            }
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (pack != null && pack.matches("study-buddy-\\d")) {
                        prefs.edit().putString("overlay_pack", pack).apply();
                    }
                    if (!on) {
                        prefs.edit().putBoolean("overlay", false).apply();
                        if (CompanionService.running()) {
                            companion(new Intent(CompanionService.ACTION_HIDE));
                        }
                        return;
                    }
                    askForNotifications();
                    if (Settings.canDrawOverlays(MainActivity.this)) {
                        prefs.edit().putBoolean("overlay", true).apply();
                        companion(new Intent(CompanionService.ACTION_SHOW).putExtra("pack", prefs.getString("overlay_pack", "study-buddy-2")));
                        Toast.makeText(MainActivity.this, "Study Buddy will float over other apps when you leave Jarvis.", Toast.LENGTH_LONG).show();
                    } else {
                        prefs.edit().putBoolean("overlay_wanted", true).apply();
                        Toast.makeText(MainActivity.this, "Allow \"Display over other apps\" for Jarvis, then come back.", Toast.LENGTH_LONG).show();
                        try {
                            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
                        } catch (Exception e) {
                            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION));
                        }
                    }
                }
            });
        }

        @JavascriptInterface
        public void companionPose(String pack, String pose) {
            if (allowed() && CompanionService.running()) {
                companion(new Intent(CompanionService.ACTION_POSE).putExtra("pack", pack).putExtra("pose", pose));
            }
        }

        /** Study Buddy's voice on or off (Settings), for the floating Study Buddy too. */
        @JavascriptInterface
        public void setVoice(boolean on) {
            if (allowed()) {
                prefs.edit().putBoolean("voice", on).apply();
            }
        }

        /** The language her recorded voice speaks: "app" (the app's), "ja" or "en". */
        @JavascriptInterface
        public void setVoiceLanguage(String lang) {
            if (allowed()) {
                prefs.edit().putString("voice_lang", "ja".equals(lang) || "en".equals(lang) ? lang : "app").apply();
            }
        }

        @JavascriptInterface
        public void setLanguage(String lang) {
            if (allowed()) {
                prefs.edit().putString("lang", "ja".equals(lang) ? "ja" : "en").apply();
            }
        }

        // ---- focus sessions (FocusSession.java): they keep going while Jarvis is in the background
        @JavascriptInterface
        public void sessionStart(String kind, int minutes, String settings) {
            if (!allowed()) {
                return;
            }
            int grace = 5, cooldown = 15;
            try {
                org.json.JSONObject s = new org.json.JSONObject(settings == null || settings.isEmpty() ? "{}" : settings);
                grace = Math.max(1, Math.min(120, s.optInt("grace", 5)));
                cooldown = Math.max(1, Math.min(240, s.optInt("cooldown", 15)));
                if (s.has("lang")) {
                    setLanguage(s.optString("lang"));
                }
            } catch (Exception ignored) {
                // defaults
            }
            askForNotifications();
            companion(new Intent(CompanionService.ACTION_SESSION).putExtra("kind", "study".equals(kind) ? "study" : "coding")
                    .putExtra("minutes", Math.max(1, Math.min(minutes, 240))).putExtra("grace", grace).putExtra("cooldown", cooldown));
        }

        @JavascriptInterface
        public void sessionStop() {
            if (allowed()) {
                companion(new Intent(CompanionService.ACTION_STOP_SESSION));
            }
        }

        @JavascriptInterface
        public void sessionPause(boolean paused) {
            if (allowed()) {
                companion(new Intent(CompanionService.ACTION_PAUSE).putExtra("paused", paused));
            }
        }

        @JavascriptInterface
        public void sessionSnooze(int minutes) {
            if (allowed()) {
                companion(new Intent(CompanionService.ACTION_SNOOZE).putExtra("minutes", Math.max(1, Math.min(minutes, 240))));
            }
        }

        @JavascriptInterface
        public void sessionBreak(int minutes) {
            if (allowed()) {
                companion(new Intent(CompanionService.ACTION_BREAK).putExtra("minutes", Math.max(0, Math.min(minutes, 60))));
            }
        }

        /** You did something in Jarvis (tap, typing, scrolling); the page sends this at most every few seconds. */
        @JavascriptInterface
        public void sessionActivity() {
            if (allowed()) {
                CompanionService.activity(MainActivity.this);
            }
        }

        @JavascriptInterface
        public String sessionState() {
            return allowed() ? CompanionService.stateJson(MainActivity.this) : "{}";
        }

        /** The page can't reach Jarvis on this phone: wake Termux up (see MainActivity.wakePocket). */
        @JavascriptInterface
        public void wakePocket() {
            if (allowed() && onPocket()) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        MainActivity.this.wakePocket();
                    }
                });
            }
        }

        // ---- checking code on this phone while the laptop's Jarvis is on screen
        @JavascriptInterface
        public boolean hasPocket() {
            return allowed() && termuxInstalled();
        }

        @JavascriptInterface
        public void pocketCall(final String method, final String path, final String body, final String id) {
            if (!allowed() || id == null || !id.matches("[A-Za-z0-9_-]{1,40}") || path == null) {
                return;
            }
            // Only the practice exercises: reading them and running your answer's tests on this phone.
            boolean ok = ("GET".equals(method) && path.matches("/api/learn/exercises(/[A-Za-z0-9_.-]+)?"))
                    || ("POST".equals(method) && path.matches("/api/learn/exercises/[A-Za-z0-9_.-]+/run"));
            if (!ok) {
                answer(id, 403, "{\"detail\":\"Not allowed.\"}");
                return;
            }
            new Thread(new Runnable() {
                @Override
                public void run() {
                    pocketRequest(method, path, body, id);
                }
            }, "jarvis-pocket-call").start();
        }
    }

    // ---------------------------------------------------------------- find my computer
    private void findComputer(final boolean userAsked) {
        if (scanning) {
            return;
        }
        scanning = true;
        if (userAsked) {
            Toast.makeText(this, "Looking for Jarvis on this Wi-Fi\u2026", Toast.LENGTH_SHORT).show();
        }
        final String saved = address();
        new Thread(new Runnable() {
            @Override
            public void run() {
                final String found = scanForJarvis(saved);
                scanning = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (found == null) {
                            if (!onPocket() && "auto".equals(mode()) && termuxInstalled()) {
                                Toast.makeText(MainActivity.this, "Your laptop isn't reachable, so Jarvis on this phone will answer.",
                                        Toast.LENGTH_LONG).show();
                                openPocket();
                                return;
                            }
                            if (userAsked) {
                                Toast.makeText(MainActivity.this, "Couldn't find Jarvis on this Wi-Fi. Is it running with phone access on?",
                                        Toast.LENGTH_LONG).show();
                            }
                        } else if (!found.equalsIgnoreCase(address())) {
                            prefs.edit().putString("address", found).apply();
                            Toast.makeText(MainActivity.this, "Found your computer at " + found, Toast.LENGTH_LONG).show();
                            web.clearHistory();
                            openHome();
                        } else if (userAsked) {
                            openHome();
                        }
                    }
                });
            }
        }, "jarvis-find").start();
    }

    /** Checks every address on this phone's Wi-Fi network (x.x.x.1-254) for Jarvis. */
    private String scanForJarvis(String saved) {
        final int port = portOf(saved);
        String mine = wifiAddress();
        if (mine == null) {
            return null; // not on Wi-Fi (never scan mobile data networks)
        }
        String prefix = mine.substring(0, mine.lastIndexOf('.') + 1);
        ExecutorService pool = Executors.newFixedThreadPool(48);
        List<Future<String>> results = new ArrayList<Future<String>>();
        for (int i = 1; i < 255; i++) {
            final String host = prefix + i;
            if (host.equals(mine)) {
                continue;
            }
            results.add(pool.submit(new Callable<String>() {
                @Override
                public String call() {
                    return isJarvisAt(host, port) ? host + ":" + port : null;
                }
            }));
        }
        String found = null;
        long deadline = System.currentTimeMillis() + 15000;
        for (Future<String> f : results) {
            try {
                String r = f.get(Math.max(1, deadline - System.currentTimeMillis()), TimeUnit.MILLISECONDS);
                if (r != null) {
                    found = r;
                    break;
                }
            } catch (Exception ignored) {
                // no answer from that address
            }
        }
        pool.shutdownNow();
        return found;
    }

    private static int portOf(String address) {
        try {
            return Integer.parseInt(address.substring(address.lastIndexOf(':') + 1));
        } catch (Exception e) {
            return 8766;
        }
    }

    private static String wifiAddress() {
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                String name = ni.getName();
                if (!ni.isUp() || ni.isLoopback() || !(name.startsWith("wlan") || name.startsWith("swlan")
                        || name.startsWith("ap") || name.startsWith("eth"))) {
                    continue;
                }
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address && a.isSiteLocalAddress()) {
                        return a.getHostAddress();
                    }
                }
            }
        } catch (Exception ignored) {
            // no network information
        }
        return null;
    }

    /** True only if the address answers over HTTPS with a certificate from this computer's Jarvis. */
    private static boolean isJarvisAt(String host, int port) {
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(host, port), 400);
        } catch (Exception e) {
            return false;
        } finally {
            try {
                socket.close();
            } catch (Exception ignored) {
                // already closed
            }
        }
        try {
            HttpsURLConnection c = (HttpsURLConnection) new URL("https://" + host + ":" + port + "/m/manifest.webmanifest").openConnection();
            c.setConnectTimeout(2000);
            c.setReadTimeout(2000);
            int code = c.getResponseCode();
            c.disconnect();
            return code == 200; // TLS only succeeds with the Jarvis CA (network security config)
        } catch (Exception e) {
            return false;
        }
    }

    // ---------------------------------------------------------------- pictures (camera or gallery)
    private class Chrome extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (pictureCallback != null) {
                pictureCallback.onReceiveValue(null);
            }
            pictureCallback = callback;
            Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
            pick.addCategory(Intent.CATEGORY_OPENABLE);
            pick.setType("image/*");
            pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
            Intent chooser = Intent.createChooser(pick, "Add a picture");
            cameraUri = null;
            try { // offer the camera too; the photo is saved in Pictures/Jarvis
                ContentValues values = new ContentValues();
                values.put(MediaStore.Images.Media.DISPLAY_NAME, "jarvis_" + System.currentTimeMillis() + ".jpg");
                values.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                if (Build.VERSION.SDK_INT >= 29) {
                    values.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Jarvis");
                }
                cameraUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
                Intent camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                camera.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri);
                camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{camera});
            } catch (Exception e) {
                cameraUri = null; // gallery only
            }
            try {
                startActivityForResult(chooser, PICK_PICTURES);
            } catch (Exception e) {
                pictureCallback = null;
                return false;
            }
            return true;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent intent) {
        if (requestCode == POCKET_START) {
            String problem = termuxProblem(intent); // empty: it exited normally because Jarvis was already running
            if (!problem.isEmpty() && pocketProblem == null) {
                showPocketProblem(problem);
            }
            return;
        }
        if (requestCode == POCKET_TOKEN) {
            String token = "";
            String problem = termuxProblem(intent);
            try {
                Bundle result = intent.getBundleExtra("result");
                String stdout = result == null ? "" : result.getString("stdout", "");
                token = new org.json.JSONObject(stdout.trim()).getString("token");
            } catch (Exception ignored) {
                // no usable answer from Termux
            }
            if (token.isEmpty()) {
                showPocketProblem("Couldn't get a key for this app from Jarvis on the phone. "
                        + (problem.isEmpty() ? "Check that Termux is set up (see the README)." : problem));
            } else {
                data.edit().putString("phone/jarvis.deviceToken", token).apply();
                waitForPocketThenLoad();
            }
            return;
        }
        if (requestCode != PICK_PICTURES || pictureCallback == null) {
            super.onActivityResult(requestCode, resultCode, intent);
            return;
        }
        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            ClipData clip = intent == null ? null : intent.getClipData();
            if (clip != null && clip.getItemCount() > 0) {
                result = new Uri[clip.getItemCount()];
                for (int i = 0; i < clip.getItemCount(); i++) {
                    result[i] = clip.getItemAt(i).getUri();
                }
            } else if (intent != null && intent.getData() != null) {
                result = new Uri[]{intent.getData()};
            } else if (cameraUri != null) {
                result = new Uri[]{cameraUri}; // photo just taken with the camera
            }
        }
        boolean usedCamera = result != null && cameraUri != null && result.length == 1 && cameraUri.equals(result[0]);
        if (cameraUri != null && !usedCamera) {
            try { // remove the unused, empty camera placeholder
                getContentResolver().delete(cameraUri, null, null);
            } catch (Exception ignored) {
                // nothing to remove
            }
        }
        pictureCallback.onReceiveValue(result);
        pictureCallback = null;
        cameraUri = null;
    }

    private X509Certificate jarvisCa() throws Exception {
        if (jarvisCa == null) {
            try (InputStream in = getResources().openRawResource(R.raw.jarvis_ca)) {
                jarvisCa = (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(in);
            }
        }
        return jarvisCa;
    }

    private boolean issuedByJarvis(SslCertificate cert) {
        try {
            X509Certificate leaf;
            if (Build.VERSION.SDK_INT >= 29) {
                leaf = cert.getX509Certificate();
            } else {
                byte[] der = SslCertificate.saveState(cert).getByteArray("x509-certificate");
                leaf = (X509Certificate) CertificateFactory.getInstance("X.509")
                        .generateCertificate(new ByteArrayInputStream(der));
            }
            if (leaf == null) {
                return false;
            }
            leaf.checkValidity();
            leaf.verify(jarvisCa().getPublicKey());
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private void showOffline(String reason) {
        String html = readAsset("offline.html")
                .replace("{{ADDRESS}}", escape(address()))
                .replace("{{REASON}}", escape(reason));
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    private void askForAddress() {
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(address());
        input.setSelectAllOnFocus(true);
        new AlertDialog.Builder(this)
                .setTitle("Computer address")
                .setMessage("Shown on your computer in Jarvis → Settings → Phone access, e.g. 192.168.1.23:8766")
                .setView(input)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Save", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        String value = input.getText().toString().trim()
                                .replaceFirst("^https?://", "").replaceFirst("/.*$", "");
                        if (!value.matches("[A-Za-z0-9.\\-\\[\\]:]+")) {
                            return;
                        }
                        if (!value.contains(":")) {
                            value = value + ":8766";
                        }
                        prefs.edit().putString("address", value).apply();
                        web.clearHistory();
                        openHome();
                    }
                })
                .show();
    }

    private String readAsset(String name) {
        try (InputStream in = getAssets().open(name)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "<p>Can't reach Jarvis. <a href=\"jarvisapp:retry\">Try again</a></p>";
        }
    }

    private static String escape(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;");
    }
}
