/* English / Japanese for Study Buddy, Coding Focus, check-ins, notifications, the Build page and the main
 * navigation. Other screens are still English for now. The language is saved per device. */
(function (root) {
  "use strict";

  const KEY = "jarvis.lang";
  const D = {
    en: {
      "nav.chat": "Chat", "nav.tasks": "Tasks", "nav.study": "Study", "nav.learn": "Learn", "nav.build": "Build",
      "nav.progress": "Progress", "nav.project": "Project", "nav.activity": "Activity", "nav.settings": "Settings",
      "nav.help": "Help", "nav.more": "More",
      "sb.name": "Study Buddy", "sb.quick": "Study Buddy — quick actions", "sb.close": "Close",
      "sb.morning": "Good morning!", "sb.afternoon": "Good afternoon!", "sb.evening": "Good evening!",
      "sb.late": "Still up? Rest matters too.", "sb.tap": "Tap me any time.",
      "sb.word": "✨ Today's word", "sb.review": "📚 Review flashcards", "sb.practice": "💻 Practice coding",
      "sb.ask": "💬 Ask Jarvis", "sb.progress": "📈 My progress", "sb.checkin": "💜 How I feel",
      "sb.session": "⏱ Start a focus session", "sb.endSession": "⏹ End the focus session",
      "sb.break": "☕ Take a 5-minute break", "sb.endBreak": "⏹ End the break", "sb.hide": "Hide Study Buddy",
      "sb.focusOn": "🎯 Coding Focus: on", "sb.focusOff": "🎯 Coding Focus: off", "sb.snooze": "💤 Snooze 15 minutes",
      "sb.hidden": "Study Buddy is hidden. Turn her back on in Settings.",
      "sb.breakTick": "Break: {t} — stand up, drink water, look far away.",
      "sb.welcomeBack": "Welcome back! Ready for one small step?", "sb.breakEnded": "Break ended. One small step at a time.",
      "sb.longWork": "You've been at it for about 50 minutes. A 5-minute break helps you keep going — tap me to start one.",
      "sb.passed": "All tests pass! That's real progress. ✨", "sb.failed": "Not yet — read the first failing test, fix one thing, try again.",
      "sb.reviewsDone": "Reviews done. Your future self says thanks.", "sb.thinking": "Hmm, let me think…",
      "sb.sessionTick": "Focus: {t} left. You've got this.", "sb.sessionDone": "Focus session done! 🎉 Take a short break.",
      "sb.distracted": "Hmph! You've been away from coding for {m} min. Come back? 😤",
      "sb.notifTitle": "Study Buddy", "sb.dragHint": "Drag me anywhere. Tap me for quick actions.",
      "sb.codingSession": "💻 Start a coding session", "sb.studySession": "📖 Start a study session",
      "sb.pauseSession": "⏸ Pause the session", "sb.resumeSession": "▶ Resume the session",
      "sb.snoozeNudges": "💤 No reminders for 15 minutes", "sb.kind.coding": "Coding", "sb.kind.study": "Study",
      "sb.sessionLine": "{kind} session · {t} left", "sb.sessionPaused": "{kind} session paused · {t} left",
      "sb.sessionStart": "{kind} session: {m} minutes. Let's go! ✨",
      "sb.sessionDoneKind": "{kind} session done! 🎉 Take a short break.",
      "sb.nudge": "Hmph! Nothing's happened in Jarvis for {m} min. Still with me? 😤",
      "sb.back": "You're back! Let's keep going. ✨",
      "word.verse": "A verse for you", "word.quote": "A quote for you", "word.note": "From Jarvis",
      "word.stoic": "From the Stoics", "word.philosophy": "From philosophy", "word.another": "Another",
      "word.thanks": "Thanks", "word.because": "{r}, so this one felt right.", "word.dialog": "Your word for today",
      "ci.title": "Before we start: how are you right now?", "ci.mood": "Mood", "ci.energy": "Energy", "ci.stress": "Stress",
      "ci.sleep": "Sleep last night (hours)", "ci.body": "My body feels", "ci.note": "Anything on your mind? (optional, stays on your devices)",
      "ci.skip": "Skip", "ci.save": "Save", "ci.savedOffline": "Saved on this device. Jarvis adds it when it's reachable again.", "ci.need": "Pick your mood, energy and stress first (one face each).", "ci.why": "Jarvis uses this to suggest how long and how hard to work today, and to show you later when you learn best.",
      "ci.planTitle": "Today's plan", "ci.startSession": "Start a {m}-minute focus session", "ci.breathe": "Breathe for one minute",
      "ci.coach": "Talk it through with the coach", "ci.done": "Done",
      "ci.body.rested": "rested", "ci.body.energetic": "energetic", "ci.body.tired": "tired", "ci.body.sleepy": "sleepy",
      "ci.body.hungry": "hungry", "ci.body.thirsty": "thirsty", "ci.body.headache": "headache", "ci.body.eye_strain": "tired eyes",
      "ci.body.sore": "sore / stiff", "ci.body.sick": "unwell", "ci.body.restless": "restless",
      "ci.breatheIn": "Breathe in…", "ci.hold": "Hold…", "ci.breatheOut": "Breathe out…",
      "set.title": "Study Buddy and encouragement", "set.show": "Show Study Buddy", "set.pack": "Which Study Buddy",
      "set.size": "Size", "set.small": "Small", "set.medium": "Medium", "set.large": "Large", "set.tips": "Gentle tips (breaks after about 50 minutes)",
      "set.wordWhen": "When I open Jarvis, show", "set.wordEvery": "A verse or quote every time", "set.wordDaily": "A verse or quote once a day",
      "set.wordOff": "Nothing", "set.kind": "Kind", "set.both": "Stoicism and philosophy, Bible verses and quotes", "set.philosophy": "Only Stoicism and philosophy", "set.verses": "Only Bible verses",
      "set.quotes": "Only quotes and notes", "set.focusWhat": "What matters most to you right now", "set.checkin": "Check-in (mood, energy, body)",
      "set.ciDaily": "Once a day, when I open Jarvis", "set.ciSession": "Before every focus session", "set.ciOff": "Off",
      "set.lang": "Language", "set.showNow": "Show a verse or quote now", "set.checkNow": "Check in now",
      "set.focusTitle": "Coding Focus", "set.focusOnLabel": "Coding Focus (Study Buddy gets pouty if you stay away from coding apps)",
      "set.grace": "Grace period (minutes away before she reacts)", "set.cooldown": "At most one reminder every (minutes)",
      "set.apps": "Apps that count as coding", "set.recent": "Recently used (tap to add)", "set.addApp": "Add an app (e.g. code.exe)",
      "set.overlay": "Float over other apps (Windows)", "set.notify": "Allow reminders as notifications",
      "set.focusPrivacy": "Jarvis only checks which program is in front (for example Code.exe). It never reads your keystrokes, window titles, screen or code.",
      "set.focusManual": "This device can't see other apps, so Coding Focus counts time away from Jarvis while a focus session is running.",
      "set.snooze15": "Snooze 15 min", "set.snooze60": "Snooze 1 hour", "set.pause": "Pause", "set.resume": "Resume",
      "set.state.off": "off", "set.state.coding": "coding — great", "set.state.away": "away (grace period)",
      "set.state.distracted": "away too long", "set.state.snoozed": "snoozed", "set.state.paused": "paused",
      "set.sessionsTitle": "Focus sessions", "set.sessionLength": "Session length (minutes)",
      "set.sessionGrace": "Remind me after this many minutes with no activity in Jarvis",
      "set.sessionCooldown": "At most one reminder every (minutes)",
      "set.sessionPrivacy": "During a session Study Buddy only notices whether you're using Jarvis (tapping, typing, scrolling here, or Jarvis being in the background). She doesn't look at other apps, your screen or what you type. One reminder per quiet stretch; pause or snooze any time.",
      "set.watchTitle": "Optional (Windows): count time in your coding apps",
      "set.phoneOverlay": "Float over other apps (Android)", "set.phoneOverlayHint": "Android asks you to allow “Display over other apps” once.",
      "set.usage": "Know which app is open (for coding apps like Termux)", "set.usageHint": "Android asks for “Usage access”. Jarvis reads only the app name.",
      "build.title": "Build", "build.plan": "Plan an idea", "build.decide": "Decide", "build.numbers": "Numbers", "build.hackathon": "Hackathon",
      "build.idea": "Your idea", "build.lang": "I'm best at", "build.makePlan": "Plan it", "build.ask": "Ask Jarvis to refine this plan",
    },
    ja: {
      "nav.chat": "チャット", "nav.tasks": "タスク", "nav.study": "学習", "nav.learn": "学ぶ",
      "nav.build": "つくる", "nav.progress": "進捗", "nav.project": "プロジェクト",
      "nav.activity": "履歴", "nav.settings": "設定", "nav.help": "ヘルプ", "nav.more": "その他",
      "sb.name": "スタディバディ", "sb.quick": "スタディバディ — クイック操作",
      "sb.close": "閉じる", "sb.morning": "おはよう！", "sb.afternoon": "こんにちは！",
      "sb.evening": "こんばんは！", "sb.late": "まだ起きてるの？休むのも大事だよ。",
      "sb.tap": "いつでもタップしてね。",
      "sb.word": "✨ 今日のことば", "sb.review": "📚 単語カードを復習",
      "sb.practice": "💻 コーディング練習", "sb.ask": "💬 Jarvisに聞く",
      "sb.progress": "📈 進捗を見る", "sb.checkin": "💜 今の気分",
      "sb.session": "⏱ 集中セッションを始める", "sb.endSession": "⏹ 集中セッションを終わる",
      "sb.break": "☕ 5分休憩する", "sb.endBreak": "⏹ 休憩を終わる",
      "sb.hide": "スタディバディを隠す", "sb.focusOn": "🎯 コーディング集中：オン",
      "sb.focusOff": "🎯 コーディング集中：オフ", "sb.snooze": "💤 15分スヌーズ",
      "sb.hidden": "スタディバディを隠しました。設定から戻せます。",
      "sb.breakTick": "休憩：{t} — 立ち上がって、水を飲んで、遠くを見よう。",
      "sb.welcomeBack": "おかえり！小さな一歩から始めよう。",
      "sb.breakEnded": "休憩おしまい。一歩ずついこう。",
      "sb.longWork": "もう約50分、集中してるよ。5分休むと続けやすくなるよ。タップして休憩しよう。",
      "sb.passed": "テスト全部合格！すごい進歩だよ ✨",
      "sb.failed": "まだだよ — 最初の失敗を読んで、1つ直して、もう一度。",
      "sb.reviewsDone": "復習完了！未来の自分がありがとうって。",
      "sb.thinking": "うーん、考え中…", "sb.sessionTick": "集中：あと{t}。がんばって！",
      "sb.sessionDone": "集中セッション完了！🎉 少し休憩しよう。",
      "sb.distracted": "むー！{m}分もコーディングから離れてるよ。戻ってきて？ 😤",
      "sb.notifTitle": "スタディバディ", "sb.dragHint": "ドラッグで動かせるよ。タップでメニュー。",
      "sb.codingSession": "💻 コーディングセッションを始める", "sb.studySession": "📖 学習セッションを始める",
      "sb.pauseSession": "⏸ セッションを一時停止", "sb.resumeSession": "▶ セッションを再開",
      "sb.snoozeNudges": "💤 15分間リマインドしない", "sb.kind.coding": "コーディング", "sb.kind.study": "学習",
      "sb.sessionLine": "{kind}セッション・残り{t}", "sb.sessionPaused": "{kind}セッション一時停止中・残り{t}",
      "sb.sessionStart": "{kind}セッション：{m}分。がんばろう！✨",
      "sb.sessionDoneKind": "{kind}セッション完了！🎉 少し休憩しよう。",
      "sb.nudge": "むー！{m}分もJarvisで何もしてないよ。まだいる？ 😤",
      "sb.back": "おかえり！続けよう。✨",
      "word.verse": "あなたへの聖句", "word.quote": "あなたへの名言", "word.note": "Jarvisより",
      "word.stoic": "ストア派のことば", "word.philosophy": "哲学のことば",
      "word.another": "もう一つ", "word.thanks": "ありがとう", "word.because": "{r}ので、これを選びました。",
      "word.dialog": "今日のことば",
      "ci.title": "始める前に：今の調子は？", "ci.mood": "気分", "ci.energy": "元気",
      "ci.stress": "ストレス", "ci.sleep": "昨夜の睡眠（時間）", "ci.body": "体の調子",
      "ci.note": "気になることは？（任意、あなたの端末だけに保存）",
      "ci.skip": "スキップ", "ci.save": "保存", "ci.savedOffline": "この端末に保存しました。Jarvisにつながったら追加します。", "ci.need": "まず気分・元気・ストレスを選んでね（それぞれ1つ）。",
      "ci.why": "今日どれくらいの長さ・強さで取り組むかを提案し、あとでいつ一番学べるかを見せます。",
      "ci.planTitle": "今日のプラン", "ci.startSession": "{m}分の集中セッションを始める",
      "ci.breathe": "1分間、呼吸する", "ci.coach": "コーチに話す", "ci.done": "完了",
      "ci.body.rested": "よく休めた", "ci.body.energetic": "元気", "ci.body.tired": "疲れている",
      "ci.body.sleepy": "眠い", "ci.body.hungry": "おなかがすいた", "ci.body.thirsty": "のどが渇いた",
      "ci.body.headache": "頭が痛い", "ci.body.eye_strain": "目が疲れた", "ci.body.sore": "体がこっている",
      "ci.body.sick": "体調が悪い", "ci.body.restless": "落ち着かない",
      "ci.breatheIn": "吸って…", "ci.hold": "止めて…", "ci.breatheOut": "吐いて…",
      "set.title": "スタディバディと応援のことば", "set.show": "スタディバディを表示",
      "set.pack": "どのスタディバディ", "set.size": "大きさ", "set.small": "小", "set.medium": "中",
      "set.large": "大", "set.tips": "やさしいヒント（約50分ごとに休憩）",
      "set.wordWhen": "Jarvisを開いたとき", "set.wordEvery": "毎回、聖句か名言を表示",
      "set.wordDaily": "1日1回、聖句か名言を表示", "set.wordOff": "表示しない", "set.kind": "種類",
      "set.both": "ストア派・哲学、聖句、名言", "set.philosophy": "ストア派と哲学のみ", "set.verses": "聖句のみ", "set.quotes": "名言とメモのみ",
      "set.focusWhat": "今、一番大切なもの", "set.checkin": "チェックイン（気分・元気・体）",
      "set.ciDaily": "1日1回、Jarvisを開いたとき", "set.ciSession": "集中セッションの前に毎回",
      "set.ciOff": "オフ", "set.lang": "言語", "set.showNow": "今、聖句か名言を表示", "set.checkNow": "今チェックイン",
      "set.focusTitle": "コーディング集中",
      "set.focusOnLabel": "コーディング集中（コーディングアプリから離れすぎるとスタディバディがむくれます）",
      "set.grace": "反応までの猶予（分）", "set.cooldown": "通知は最大で何分に1回",
      "set.apps": "コーディングに数えるアプリ", "set.recent": "最近使ったアプリ（タップで追加）",
      "set.addApp": "アプリを追加（例：code.exe）", "set.overlay": "他のアプリの上に表示（Windows）",
      "set.notify": "通知でお知らせする",
      "set.focusPrivacy": "Jarvisが確認するのは前面にあるプログラム名（例：Code.exe）だけです。キー入力・ウィンドウ名・画面・コードは読みません。",
      "set.focusManual": "この端末では他のアプリが見えないため、集中セッション中にJarvisから離れた時間を数えます。",
      "set.snooze15": "15分スヌーズ", "set.snooze60": "1時間スヌーズ", "set.pause": "一時停止", "set.resume": "再開",
      "set.state.off": "オフ", "set.state.coding": "コーディング中 — いい感じ",
      "set.state.away": "離席中（猶予内）", "set.state.distracted": "離れすぎ", "set.state.snoozed": "スヌーズ中",
      "set.state.paused": "一時停止中",
      "set.sessionsTitle": "集中セッション", "set.sessionLength": "セッションの長さ（分）",
      "set.sessionGrace": "Jarvisで何もしない時間がこの分数を超えたらお知らせ",
      "set.sessionCooldown": "お知らせは最大で何分に1回",
      "set.sessionPrivacy": "セッション中、スタディバディが気にするのはJarvisを使っているかどうか（ここでのタップ・入力・スクロール、またはJarvisがバックグラウンドにあるか）だけです。他のアプリ・画面・入力内容は見ません。静かな時間ごとにお知らせは1回だけ。いつでも一時停止・スヌーズできます。",
      "set.watchTitle": "任意（Windows）：コーディングアプリの時間も数える",
      "set.phoneOverlay": "他のアプリの上に表示（Android）",
      "set.phoneOverlayHint": "最初に「他のアプリの上に重ねて表示」の許可が必要です。",
      "set.usage": "開いているアプリを知る（Termuxなど）",
      "set.usageHint": "「使用状況へのアクセス」の許可が必要です。読むのはアプリ名だけです。",
      "build.title": "つくる", "build.plan": "アイデアを計画", "build.decide": "決める",
      "build.numbers": "数字", "build.hackathon": "ハッカソン", "build.idea": "あなたのアイデア",
      "build.lang": "得意な言語", "build.makePlan": "計画する", "build.ask": "Jarvisに計画を磨いてもらう",
    },
  };

  function get() { try { return localStorage.getItem(KEY) === "ja" ? "ja" : "en"; } catch (_) { return "en"; } }
  let lang = get();

  function t(key, vars) {
    let s = (D[lang] && D[lang][key]) || D.en[key] || key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace("{" + k + "}", v);
    return s;
  }

  function setLang(l) {
    lang = l === "ja" ? "ja" : "en";
    try { localStorage.setItem(KEY, lang); } catch (_) { /* storage blocked */ }
    document.documentElement.lang = lang;
    apply(document);
    for (const fn of listeners) { try { fn(lang); } catch (_) { /* ignore */ } }
  }

  /** Elements with data-i18n="key" get the translated text. */
  function apply(rootEl) {
    for (const el of (rootEl || document).querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  }

  const listeners = [];
  root.JarvisI18n = { t, lang: () => lang, setLang, apply, onChange: (fn) => listeners.push(fn) };
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => apply(document));
    else apply(document);
  }
})(this);
