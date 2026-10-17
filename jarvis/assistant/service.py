"""The assistant: builds prompts, talks to the local model, saves history."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from datetime import date
from typing import AsyncIterator, Callable

from ..activity import ActivityLog
from ..config import ConfigStore, EndpointNotLocalError, Settings, is_loopback_endpoint
from ..conversations import ConversationStore
from ..llm import ChatOptions, LLMProvider, ProviderError, create_provider, pick_model
from ..project import ProjectManager
from ..tasks import smart_sort
from .context import build_project_context
from ..build import catalog as build_catalog
from .router import route
from .prompts import (BREAKDOWN_PROMPT, BREAKDOWN_SCHEMA, FLASHCARD_PROMPT, FLASHCARD_SCHEMA, MODES,
                      PLAN_PROMPT, PLAN_SCHEMA, system_prompt)

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 3.2
ANSWER_RESERVE_TOKENS = 1500
CODE_MODES = {"implement", "test"}  # modes that use the code model when one is set
GROUNDED_MODES = {"business", "stack", "hackathon"}  # answers include guide notes + the tech catalog
# Models that can read images, best first (only installed ones are ever used).
VISION_PREFERRED = ["gemma3:12b", "qwen2.5vl:7b", "gemma3:4b", "llama3.2-vision:latest", "qwen3-vl:4b",
                    "qwen3-vl:2b", "minicpm-v:latest", "llava:7b", "llava:latest", "moondream:latest"]
EVIDENCE_CHARS = 5000  # how much real command output to show the model


class ProviderHolder:
    """Creates the provider from settings and recreates it when they change."""

    def __init__(self, config: ConfigStore, factory: Callable[[Settings], LLMProvider] = create_provider):
        self.config = config
        self.factory = factory
        self._provider: LLMProvider | None = None
        self._key: tuple | None = None
        self._lock = threading.Lock()

    def get(self) -> LLMProvider:
        s = self.config.get()
        key = (s.provider, s.endpoint, s.request_timeout, s.allow_remote_endpoint)
        with self._lock:
            if self._provider is None or key != self._key:
                self._provider = self.factory(s)  # raises EndpointNotLocalError for remote endpoints
                self._key = key
            return self._provider

    async def status(self) -> dict:
        s = self.config.get()
        base = {"provider": s.provider, "endpoint": s.endpoint, "configured_model": s.model,
                "local": is_loopback_endpoint(s.endpoint), "models": [], "version": "",
                "model": "", "hint": "", "message": ""}
        try:
            provider = self.get()
        except EndpointNotLocalError as exc:
            return {**base, "state": "blocked", "message": str(exc),
                    "hint": "Change the endpoint in Settings to a local address."}
        st = await provider.status()
        if not st.reachable:
            from ..llm.ollama import NOT_RUNNING_HINT as OLLAMA_HINT
            from ..llm.openai_compat import NOT_RUNNING_HINT as OAI_HINT
            return {**base, "state": "not_running", "message": st.error,
                    "hint": OLLAMA_HINT if s.provider == "ollama" else OAI_HINT}
        names = [m.name for m in st.models]
        models = [{"name": m.name, "size_bytes": m.size_bytes, "parameter_size": m.parameter_size,
                   "capabilities": m.capabilities} for m in st.models]
        base.update(models=models, version=st.version)
        if not names:
            return {**base, "state": "no_models",
                    "message": "The model server is running but has no models installed.",
                    "hint": ("Download one model once while online, e.g. 'ollama pull qwen3:1.7b' (small, ~1.4 GB) "
                             "or 'ollama pull qwen2.5-coder:7b' (better for code, ~4.7 GB, needs 8+ GB RAM).")
                    if s.provider == "ollama" else "Load a model in your model server."}
        model = pick_model(s.model, names)
        base["vision_model"] = pick_vision_model(s.vision_model, model, models)
        if s.model and s.model not in names and not (s.provider == "ollama" and f"{s.model}:latest" in names):
            return {**base, "state": "model_missing", "model": s.model,
                    "message": f"The model '{s.model}' is not installed.",
                    "hint": (f"Run 'ollama pull {s.model}' once while online, or choose one of the installed "
                             f"models in Settings: {', '.join(names[:6])}.")}
        return {**base, "state": "ready", "model": model,
                "message": f"Ready: {model}" + ("" if s.model else " (picked automatically)")}

    async def aclose(self) -> None:
        if self._provider:
            await self._provider.aclose()


def pick_vision_model(configured: str, chat_model: str, models: list[dict]) -> str:
    """The model used to look at images: the configured one, else the chat model if it can see,
    else the best installed model with the 'vision' capability. Empty if none can."""
    can_see = {m["name"] for m in models if "vision" in (m.get("capabilities") or [])}
    names = {m["name"] for m in models}
    if configured and (configured in names or f"{configured}:latest" in names):
        return configured
    if chat_model in can_see:
        return chat_model
    for name in VISION_PREFERRED:
        if name in can_see:
            return name
    return sorted(can_see)[0] if can_see else ""


class ChatCancelled(Exception):
    pass


async def _with_cancel(agen: AsyncIterator, cancel: asyncio.Event) -> AsyncIterator:
    """Iterate `agen`, but stop immediately (even mid-wait) when `cancel` is set."""
    it = agen.__aiter__()
    cancel_wait = asyncio.ensure_future(cancel.wait())
    try:
        while True:
            nxt = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({nxt, cancel_wait}, return_when=asyncio.FIRST_COMPLETED)
            if nxt not in done:
                nxt.cancel()
                try:
                    await nxt
                except (asyncio.CancelledError, StopAsyncIteration, Exception):
                    pass
                raise ChatCancelled()
            try:
                yield nxt.result()
            except StopAsyncIteration:
                return
    finally:
        cancel_wait.cancel()
        aclose = getattr(it, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass


def parse_json_reply(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


class Assistant:
    def __init__(self, config: ConfigStore, holder: ProviderHolder, conversations: ConversationStore,
                 projects: ProjectManager, activity: ActivityLog, runner=None, images=None, guides=None):
        self.config = config
        self.holder = holder
        self.conversations = conversations
        self.projects = projects
        self.activity = activity
        self.runner = runner
        self.images = images
        self.guides = guides
        self._streams: dict[str, asyncio.Event] = {}

    def cancel(self, stream_id: str) -> bool:
        event = self._streams.get(stream_id)
        if event:
            event.set()
            return True
        return False

    async def _ready_model(self, mode: str = "general", images: bool = False) -> tuple[LLMProvider, str, str]:
        """Return (provider, model, note). Code modes use the code model when one is set;
        messages with images use a model that can see them."""
        status = await self.holder.status()
        if status["state"] != "ready":
            raise ProviderError(status["message"], status["hint"], status["state"])
        if images:
            vision = status.get("vision_model", "")
            if not vision:
                raise ProviderError(
                    "None of your installed models can look at images.",
                    "Download one once while online, for example 'ollama pull gemma3:4b' (it is also a good chat model).",
                    "no_vision")
            note = "" if vision == status["model"] else f"Using {vision} to look at the image."
            return self.holder.get(), vision, note
        code_model = self.config.get().code_model
        if mode in CODE_MODES and code_model and code_model != status["model"]:
            installed = {m["name"] for m in status["models"]}
            if code_model in installed or f"{code_model}:latest" in installed:
                return self.holder.get(), code_model, ""
            return self.holder.get(), status["model"], (
                f"The code model '{code_model}' isn't installed, so {status['model']} answered instead.")
        return self.holder.get(), status["model"], ""

    # ------------------------------------------------------------ evidence from real runs
    def _test_preset(self) -> dict | None:
        for preset in self.projects.presets:
            if preset.get("category") == "test" and preset.get("level") == "safe":
                return preset
        return None

    def _latest_run(self, root: str):
        if not self.runner:
            return None
        runs = [r for r in list(self.runner.runs.values()) if r.cwd == root and r.status != "running"]
        return max(runs, key=lambda r: r.started) if runs else None

    @staticmethod
    def _describe_run(run) -> str:
        minutes = int((time.time() - (run.ended or run.started)) // 60)
        when = "just now" if minutes < 1 else f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        output = run.output.strip() or "(no output)"
        if len(output) > EVIDENCE_CHARS:
            output = "...(earlier output cut)...\n" + output[-EVIDENCE_CHARS:]
        return (f"## Real result of running `{run.command}` in the project ({when})\n"
                f"Status: {run.status}, exit code {run.exit_code}. This is actual output, not a guess; "
                "base your answer on it (it may be outdated if files changed since).\n"
                f"```text\n{output}\n```")

    def _history(self, conv_id: int, exclude_id: int, budget_chars: int) -> list[dict]:
        msgs = [m for m in self.conversations.messages(conv_id) if m["id"] != exclude_id and m["content"].strip()]
        picked: list[dict] = []
        used = 0
        for m in reversed(msgs):
            content = m["content"]
            if len(content) > 4000:
                content = content[:4000] + "\n...(earlier message shortened)"
            if used + len(content) > budget_chars:
                break
            if m.get("images"):
                content += f"\n(The user attached {len(m['images'])} image(s) here.)"
            picked.append({"role": m["role"], "content": content})
            used += len(content)
        picked.reverse()
        while picked and picked[0]["role"] != "user":  # history should start with the user
            picked.pop(0)
        return picked

    async def chat(self, *, message: str, conversation_id: int | None, mode: str, detail: str | None,
                   use_project: bool, attached: list[str], stream_id: str,
                   origin: str = "", run_tests: bool = False,
                   images: list[str] | None = None, use_guides: bool = False, lang: str = "en",
                   wellbeing: str = "") -> AsyncIterator[dict]:
        """Yields events: meta, status, sources, thinking, content, done | stopped | error."""
        s = self.config.get()
        mode = mode if mode in MODES else "general"
        routed_note = ""
        if mode == "auto":  # pick the mode from the question, and say which (see router.py)
            mode, _ = route(message)
            routed_note = f"Auto: answering as {MODES[mode]['label']}"
        if mode in GROUNDED_MODES:
            use_guides = True  # business, stack and hackathon answers lean on the guides and the tech catalog
        detail = detail or s.detail
        ws = self.projects.workspace
        cancel = asyncio.Event()
        self._streams[stream_id] = cancel
        if conversation_id:
            conv = self.conversations.get(conversation_id)
        else:
            title = re.sub(r"\s+", " ", message).strip()[:60] or "New chat"
            conv = self.conversations.create(title, mode, str(ws.root) if ws else "")
        images = images or []
        user_msg = self.conversations.add_message(conv["id"], "user", message, mode=mode, images=images)
        yield {"type": "meta", "conversation_id": conv["id"], "conversation_title": conv["title"],
               "user_message_id": user_msg["id"], "mode": mode}
        if routed_note:
            yield {"type": "status", "text": routed_note}

        content_parts: list[str] = []
        sources: list[dict] = []
        model = ""
        saved = False

        def save(stopped: bool) -> dict | None:
            nonlocal saved
            if saved:
                return None
            saved = True
            text = "".join(content_parts)
            if not text.strip():
                return None
            return self.conversations.add_message(conv["id"], "assistant", text, mode=mode,
                                                  sources=sources, model=model, stopped=stopped)

        try:
            provider, model, note = await self._ready_model(mode, images=bool(images))
            if note:
                yield {"type": "status", "text": note}
            ctx_chars = int(s.context_window * CHARS_PER_TOKEN)
            sys_text = system_prompt(mode, detail, model, lang)
            if wellbeing and mode in ("coach", "study", "business", "hackathon", "general"):
                sys_text += ("\n\nHow the user said they feel today (from their check-in; take it into account gently, "
                             "e.g. smaller steps when tired or stressed, but don't dwell on it): " + wellbeing[:300])
            project_text = ""
            evidence = ""
            run = None
            if ws and run_tests and self.runner:
                preset = self._test_preset()
                if not preset:
                    yield {"type": "status", "text": "This project has no one-click test command, so no tests were run."}
                else:
                    yield {"type": "status", "text": f"Running {preset['command']} first\u2026"}
                    run = self.runner.start(preset["command"], preset["argv"], ws, "safe", s.command_timeout)
                    self.activity.record("command_started", f"Ran '{preset['command']}' in {ws.name} before answering",
                                         command=preset["command"], level="safe", run_id=run.id)
                    while run.status == "running":
                        if cancel.is_set():
                            self.runner.cancel(run.id)
                            raise ChatCancelled()
                        await asyncio.sleep(0.25)
                    seconds = round((run.ended or time.time()) - run.started, 1)
                    yield {"type": "status", "text": f"Tests {run.status.replace('_', ' ')} "
                                                     f"(exit code {run.exit_code}) in {seconds}s"}
            elif ws and mode == "test":
                run = self._latest_run(str(ws.root))  # use the last real test run as evidence
            if run is not None:
                evidence = self._describe_run(run)
            if ws and (use_project or attached):
                budget = max(1000, min(s.max_context_chars, int(ctx_chars * 0.5)))
                overview = await asyncio.to_thread(ws.overview, 1500)
                project_text, sources, redactions = await asyncio.to_thread(
                    build_project_context, ws, self.projects.index, message, attached, budget,
                    use_project, overview)
                yield {"type": "sources", "sources": sources, "redactions": redactions}
                if sources:
                    self.activity.record(
                        "files_shared", f"Shared {len(sources)} file excerpt(s) from {ws.name} with the local model{origin}",
                        files=sorted({src['path'] for src in sources}), redactions=redactions)
            if evidence:
                sources = [*sources, {"path": "$ " + run.command, "start_line": 0, "end_line": 0, "kind": "command"}]
                yield {"type": "sources", "sources": sources, "redactions": 0}
            guide_text = ""
            if use_guides and self.guides is not None:
                guide_budget = max(800, min(4500, int(ctx_chars * 0.3)))
                guide_text, guide_sources = await asyncio.to_thread(self.guides.context_for, message, guide_budget)
                if guide_sources:
                    sources = [*sources, *guide_sources]
                    yield {"type": "sources", "sources": sources, "redactions": 0}
            catalog_text = ""
            if mode in GROUNDED_MODES:
                recent = " ".join(m["content"] for m in self.conversations.messages(conv["id"])[-6:] if m["role"] == "user")
                catalog_text = build_catalog.context_for(recent + " " + message, budget=2400)
            context = "\n\n".join(part for part in (project_text, guide_text, catalog_text, evidence) if part)
            user_text = message if not context else (
                f"{context}\n\n---\nUsing the project context above where relevant, respond to:\n{message}")
            history_budget = ctx_chars - len(sys_text) - len(user_text) - int(ANSWER_RESERVE_TOKENS * CHARS_PER_TOKEN)
            history = self._history(conv["id"], user_msg["id"], max(history_budget, 0))
            final = {"role": "user", "content": user_text}
            if images and self.images:
                final["images"] = [await asyncio.to_thread(self.images.base64, name) for name in images]
            messages = [{"role": "system", "content": sys_text}, *history, final]
            options = ChatOptions(model=model, temperature=s.temperature, context_window=s.context_window,
                                  think=s.think)
            stats: dict = {}
            async for chunk in _with_cancel(provider.chat_stream(messages, options), cancel):
                if chunk.kind == "content":
                    content_parts.append(chunk.text)
                    yield {"type": "content", "text": chunk.text}
                elif chunk.kind == "thinking":
                    yield {"type": "thinking", "text": chunk.text}
                elif chunk.kind == "done":
                    stats = chunk.stats
            msg = save(False)
            if msg is None:
                yield {"type": "error", "message": "The model returned an empty answer.",
                       "hint": "Try again, rephrase the question, or pick a larger model in Settings."}
            else:
                yield {"type": "done", "message_id": msg["id"], "model": model, "stats": stats}
        except ChatCancelled:
            msg = save(True)
            yield {"type": "stopped", "message_id": msg["id"] if msg else None}
        except ProviderError as exc:
            save(True)
            yield {"type": "error", "message": exc.message, "hint": exc.hint, "code": exc.code}
        except EndpointNotLocalError as exc:
            yield {"type": "error", "message": str(exc), "code": "blocked"}
        except (asyncio.CancelledError, GeneratorExit):
            save(True)  # browser went away mid-answer: keep what we have
            raise
        except Exception as exc:  # unexpected: report clearly instead of hanging
            log.exception("Chat failed")
            save(True)
            yield {"type": "error", "message": f"Something went wrong: {exc}",
                   "hint": "Check the log file in the Jarvis data folder for details."}
        finally:
            self._streams.pop(stream_id, None)

    # ------------------------------------------------------------ structured helpers
    async def complete_json(self, prompt: str, schema: dict, images: list[str] | None = None) -> dict:
        provider, model, _ = await self._ready_model(images=bool(images))
        s = self.config.get()
        user = {"role": "user", "content": prompt}
        if images and self.images:
            user["images"] = [await asyncio.to_thread(self.images.base64, name) for name in images]
        messages = [
            {"role": "system", "content": "You are Jarvis, a practical study and planning assistant. Reply with valid JSON only."},
            user,
        ]
        options = ChatOptions(model=model, temperature=0.2, context_window=s.context_window, json_schema=schema)
        last_error = ""
        for _ in range(2):
            text = await provider.chat(messages, options)
            try:
                return parse_json_reply(text)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
        raise ProviderError(f"The model did not return a usable answer ({last_error}).",
                            "Try again, or choose a larger model in Settings.", "bad_output")

    async def practice_hint(self, exercise: dict, code: str, results: list[dict], question: str = "") -> str:
        """A short hint for a practice exercise that nudges without giving the whole solution."""
        provider, model, _ = await self._ready_model("study")
        s = self.config.get()
        failing = [r for r in results if isinstance(r, dict) and not r.get("ok")][:5]
        lines = "\n".join(f"- {r.get('name')}: {str(r.get('detail') or 'failed')[:400]}" for r in failing) or (
            "- (the student hasn't run the tests yet)" if not results else "- (all tests pass)")
        lang = exercise["language"]
        prompt = (
            f"Exercise ({lang}): {exercise['title']}\n\nTask:\n{exercise['task']}\n\n"
            f"The student's code:\n```{lang}\n{code[:6000]}\n```\n\nFailing tests:\n{lines}\n\n"
            + (f"The student asks: {question}\n\n" if question.strip() else "")
            + "Give ONE short hint (2-4 sentences) that points to the most important problem and what to look at next. "
              "Do not write the full solution or complete function bodies; a tiny snippet of at most one line is fine. "
              "If all tests pass, praise briefly and suggest one way to make the code cleaner.")
        messages = [{"role": "system", "content": "You are a patient programming tutor for a student. Be encouraging, "
                                                  "concrete and brief. Never give away complete solutions."},
                    {"role": "user", "content": prompt}]
        text = await provider.chat(messages, ChatOptions(model=model, temperature=0.3, context_window=s.context_window))
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

    async def breakdown_task(self, task: dict) -> dict:
        prompt = BREAKDOWN_PROMPT.format(
            title=task["title"], description=task.get("description") or "(none)",
            notes=task.get("notes") or "(none)", project=task.get("project") or "(none)",
            due=task.get("due_date") or "(none)")
        data = await self.complete_json(prompt, BREAKDOWN_SCHEMA)
        steps = []
        for step in data.get("steps") or []:
            if isinstance(step, dict) and str(step.get("title", "")).strip():
                steps.append({"title": str(step["title"]).strip()[:300],
                              "description": str(step.get("description", "")).strip()[:2000]})
        if not steps:
            raise ProviderError("The model did not suggest any steps.", "Try again or add more detail to the task.", "bad_output")
        return {"steps": steps[:12], "notes": str(data.get("notes") or "")[:2000]}

    async def read_images(self, images: list[str]) -> str:
        """Transcribe the text in photos (notes, slides, book pages) with a model that can see."""
        provider, model, _ = await self._ready_model(images=True)
        s = self.config.get()
        b64 = [await asyncio.to_thread(self.images.base64, name) for name in images]
        messages = [
            {"role": "system", "content": "You read images for a student. Transcribe ALL the text in the image(s) "
             "exactly, keeping the original language, line breaks and bullet points. Then, if there are diagrams, "
             "tables or formulas, describe each in one short line. Do not add anything else."},
            {"role": "user", "content": "Transcribe this.", "images": b64},
        ]
        text = await provider.chat(messages, ChatOptions(model=model, temperature=0.0, context_window=s.context_window))
        return text.strip()

    async def make_flashcards(self, text: str, images: list[str], count: int) -> dict:
        count = max(1, min(count, 40))
        # Two steps work better than one: small vision models asked for flashcards directly tend to copy
        # each line onto the front (giving the answer away). Reading first, then writing cards, avoids that.
        transcript = await self.read_images(images) if images else ""
        material_text = "\n\n".join(part for part in (text.strip(), transcript) if part)[:12000]
        data = await self.complete_json(
            FLASHCARD_PROMPT.format(count=count, where="below", material=f"\nMaterial:\n{material_text}"),
            FLASHCARD_SCHEMA)
        cards = []
        for card in data.get("cards") or []:
            if not isinstance(card, dict):
                continue
            front, back = str(card.get("front", "")).strip(), str(card.get("back", "")).strip()
            if front and back:
                cards.append({"front": front[:2000], "back": back[:4000]})
        if not cards:
            raise ProviderError("The model didn't produce any flashcards.",
                                "Try again, add more text, or use a clearer photo.", "bad_output")
        title = str(data.get("title") or "").strip()
        if not title:  # fall back to the first line of the material, e.g. "Biology notes - Cell parts"
            first = next((line.strip(" #*-\t") for line in material_text.splitlines() if line.strip(" #*-\t")), "")
            title = first[:60]
        return {"title": title[:120], "cards": cards[:count], "transcript": transcript}

    async def plan_tasks(self, tasks: list[dict]) -> dict:
        open_tasks = smart_sort([t for t in tasks if t["status"] != "done"])
        if not open_tasks:
            return {"order": [], "advice": "There are no open tasks."}
        listing = "\n".join(
            f"- id {t['id']}: {t['title']} | priority {t['priority']} | status {t['status']} | "
            f"due {t.get('due_date') or 'none'}" + (f" | {t['description'][:150]}" if t.get("description") else "")
            for t in open_tasks[:40])
        data = await self.complete_json(PLAN_PROMPT.format(today=date.today().isoformat(), tasks=listing), PLAN_SCHEMA)
        by_id = {t["id"]: t for t in open_tasks[:40]}
        order, seen = [], set()
        for item in data.get("order") or []:
            try:
                tid = int(item.get("id"))
            except (TypeError, ValueError, AttributeError):
                continue
            if tid in by_id and tid not in seen:
                seen.add(tid)
                order.append({"id": tid, "title": by_id[tid]["title"], "reason": str(item.get("reason", ""))[:300]})
        for t in open_tasks[:40]:  # anything the model skipped keeps the default order
            if t["id"] not in seen:
                order.append({"id": t["id"], "title": t["title"], "reason": "(not ranked by the model; default order)"})
        return {"order": order, "advice": str(data.get("advice") or "")[:1000]}
