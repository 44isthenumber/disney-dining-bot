import base64
import contextlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

import disney_bot
import monitor
import seed_disney_session


def make_jwt(exp):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.signature"


def make_token_blob(access_token, refresh_token=""):
    payload = {"access_token": access_token, "refresh_token": refresh_token}
    return base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def _tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


def _restaurant(**overrides):
    data = {
        "name": "Ohana",
        "facility_id": "90002606",
        "slug": "ohana",
        "party_size": 2,
        "dates": [_tomorrow()],
        "meal_periods": ["ALL"],
    }
    data.update(overrides)
    return data


def _restaurant_url():
    return "https://disneyworld.disney.go.com/dine-res/restaurant/ohana"


def _challenge_428(duration=15):
    body = json.dumps({
        "sec-cp-challenge": "true",
        "provider": "crypto",
        "chlg_duration": duration,
        "branding_type": "custom_branding",
        "branding_cust_url": "https://disneyworld.disney.go.com/prodksd/media/waiting-room-assets/processing_request.html",
        "difficulty": 7500,
        "verify_url": "https://disneyworld.disney.go.com/-UKSQh/rqROa/-14a5/Qrfw/DLuhSzYNuaQO/Wh9aIw/CTc2IW4-/CwUC",
    })
    return {"status": 428, "data": None, "body": body}


def _ok_200(day=None, offer_time="19:50"):
    day = day or _tomorrow()
    return {
        "status": 200,
        "data": {
            "restaurants": {
                day: [{
                    "mealPeriodType": "Dinner",
                    "offersByAccessibility": [{
                        "offers": [{
                            "time": f"{offer_time}:00",
                            "label": "07:50 PM",
                            "offerId": "offer-1",
                        }],
                    }],
                }],
            }
        },
    }


def _token_cookie(seconds_left):
    token = make_jwt(int(time.time()) + seconds_left)
    return {"name": monitor.TOKEN_COOKIE_NAME, "value": make_token_blob(token)}


class FakeLocator:
    @property
    def first(self):
        return self

    def wait_for(self, **kwargs):
        raise Exception("not visible")

    def fill(self, *args, **kwargs):
        raise Exception("not visible")

    def click(self, *args, **kwargs):
        raise Exception("not visible")

    def inner_text(self, **kwargs):
        raise Exception("not visible")


class FakePage:
    def __init__(self, context, name="page"):
        self.context = context
        self.name = name
        self.url = "about:blank"
        self._closed = False
        self.goto_calls = []
        self.wait_calls = []
        self.evaluate_calls = []
        self.crash_handlers = []
        self.always_fail_goto = None
        self.fail_first_n = 0
        self.fail_goto_message = "net::ERR_HTTP2_PROTOCOL_ERROR"
        self.crash_on_goto_index = None
        self._goto_n = 0
        self.response_handlers = []
        self.listener_log = []
        self._challenge_waits = 0
        self.route_calls = []
        self.main_frame = object()

    def route(self, pattern, handler):
        self.route_calls.append((pattern, handler))
        self.context.events.append(("route", pattern, self))

    def on(self, event, handler):
        if event == "crash":
            self.crash_handlers.append(handler)
        if event == "response":
            self.response_handlers.append(handler)
            self.listener_log.append("on")

    def remove_listener(self, event, handler):
        if event == "response" and handler in self.response_handlers:
            self.response_handlers.remove(handler)
            self.listener_log.append("remove")

    def is_closed(self):
        return self._closed

    def locator(self, selector):
        return FakeLocator()

    @property
    def frames(self):
        return [self]

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def wait_for_selector(self, *args, **kwargs):
        raise Exception("no selector")

    def wait_for_timeout(self, timeout):
        self.wait_calls.append(timeout)
        self.context.events.append(("wait_for_timeout", timeout, self))
        if self.context.clock is not None:
            self.context.clock.advance(timeout / 1000)
        if self.response_handlers:
            # Akamai's script reports the finished challenge while the page is being waited on.
            self._challenge_waits += 1
            if self.context.on_challenge_wait:
                self.context.on_challenge_wait(self._challenge_waits)
            if self._challenge_waits <= len(self.context.proof_responses_per_wait):
                for handler in list(self.response_handlers):
                    handler(FakeResponse("https://disneyworld.disney.go.com/_sec/verify?provider=crypto",
                                         self.context.proof_responses_per_wait[self._challenge_waits - 1]))
            if self._challenge_waits == self.context.verify_after_waits:
                for handler in list(self.response_handlers):
                    handler(FakeResponse("https://disneyworld.disney.go.com/_sec/verify?provider=crypto", 200))
                    handler(FakeResponse(
                        "https://disneyworld.disney.go.com/_sec/cp_challenge/verify", self.context.verify_status))

    def goto(self, url, wait_until="domcontentloaded", timeout=None):
        self._goto_n += 1
        call = {"url": url, "wait_until": wait_until, "timeout": timeout, "page": self}
        self.goto_calls.append(call)
        self.context.events.append(("goto", url, wait_until, self))
        self.context.gotos.append(call)
        self.url = url
        if self.context.on_goto:
            self.context.on_goto(self._goto_n)
        if self.crash_on_goto_index is not None and self._goto_n == self.crash_on_goto_index:
            raise Exception("Page.goto: Page crashed")
        if self.always_fail_goto:
            raise Exception(self.always_fail_goto)
        if self.fail_first_n > 0:
            self.fail_first_n -= 1
            raise Exception(self.fail_goto_message)

    def evaluate(self, script, arg=None):
        self.evaluate_calls.append((script, arg))
        self.context.events.append(("evaluate", arg, self))
        self.context.evaluates.append(arg)
        return self.context.next_evaluate(script, arg)


class FakeResponse:
    def __init__(self, url, status):
        self.url = url
        self.status = status


class FakeRequest:
    def __init__(self, url, navigation, frame):
        self.url = url
        self.frame = frame
        self._navigation = navigation

    def is_navigation_request(self):
        return self._navigation


class FakeRoute:
    def __init__(self, url, navigation=False, frame=None, fail=""):
        self._request = FakeRequest(url, navigation, frame)
        self._fail = fail
        self.outcome = None

    @property
    def request(self):
        if self._fail == "request":
            raise Exception("request is gone")
        return self._request

    def continue_(self):
        self.outcome = "continue"
        if self._fail == "continue":
            raise Exception("Route.continue: Target closed")

    def abort(self):
        self.outcome = "abort"
        if self._fail == "abort":
            raise Exception("Route.abort: Target closed")


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeGuard:
    """Stands in for monitor._BrowserGuard: no thread, scripted memory, fake clock."""

    instances = []
    clock = None
    mem_mb_default = 300
    budget_secs = 120
    largest = ""

    def __init__(self, name):
        self.name = name
        self.started = self.clock.monotonic() if self.clock else time.monotonic()
        self.deadline = self.started + self.budget_secs
        self.mem_mb = self.mem_mb_default
        self.peak_mb = self.mem_mb_default or 0
        self.tripped = ""
        self.start_calls = 0
        self.stop_calls = 0
        FakeGuard.instances.append(self)

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1

    def seconds_left(self):
        now = self.clock.monotonic() if self.clock else time.monotonic()
        return self.deadline - now


class FakeContext:
    def __init__(self, cookies=None, evaluate_results=None):
        self.clock = FakeGuard.clock
        self.verify_after_waits = None
        self.verify_status = 200
        self.on_challenge_wait = None
        self.on_goto = None
        self.proof_responses_per_wait = []
        self.close_error = None
        self._cookies = list(cookies or [])
        self.cookies_error = None
        self.events = []
        self.gotos = []
        self.evaluates = []
        self.launch_kwargs = None
        self.profile_dir = None
        self.closed = False
        self.new_page_calls = 0
        self.created_pages = []
        self._evaluate_results = list(evaluate_results or [])
        self._evaluate_always = None
        self.pages = [FakePage(self, name="initial")]

    def cookies(self, urls=None):
        if self.cookies_error:
            raise self.cookies_error
        return list(self._cookies)

    def next_evaluate(self, script, arg):
        if self._evaluate_always is not None:
            if callable(self._evaluate_always):
                return self._evaluate_always(script, arg)
            return dict(self._evaluate_always) if isinstance(self._evaluate_always, dict) else self._evaluate_always
        if self._evaluate_results:
            return self._evaluate_results.pop(0)
        return {"status": 200, "data": {"restaurants": {}}}

    def new_page(self):
        self.new_page_calls += 1
        self.events.append(("new_page", self.new_page_calls, None))
        page = FakePage(self, name=f"new-{self.new_page_calls}")
        self.created_pages.append(page)
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class FakeChromium:
    def __init__(self, context):
        self._context = context

    def launch_persistent_context(self, profile_dir, **kwargs):
        self._context.profile_dir = profile_dir
        self._context.launch_kwargs = kwargs
        return self._context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = FakeChromium(context)


class FakePlaywrightCM:
    def __init__(self, context_factory):
        self._context_factory = context_factory
        self.contexts = []

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        context = self._context_factory()
        self.contexts.append(context)
        return FakePlaywright(context)

    def __exit__(self, exc_type, exc, tb):
        return False


ENV_KEYS = (
    "DISNEY_AKAMAI_CHALLENGE_RETRIES",
    "DISNEY_AKAMAI_CHALLENGE_WAIT_MS",
    "DISNEY_AKAMAI_CHALLENGE_MEM_MB",
    "DISNEY_AKAMAI_WARMUP_MS",
    "DISNEY_BROWSER_MEM_LIMIT_MB",
    "DISNEY_PAGE_BUDGET_SECS",
    "DISNEY_POLL_BUDGET_SECS",
    "DISNEY_SEED_FORCE_LOGIN",
    "DISNEY_LOGIN_EMAIL",
    "DISNEY_LOGIN_PASSWORD",
)
ATTEMPT_ON = {"DISNEY_AKAMAI_CHALLENGE_RETRIES": "1"}


def _waits(ctx):
    return [event[1] for event in ctx.events if event[0] == "wait_for_timeout"]


class _MonitorTestBase(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        monitor._poll_deadline = None
        monitor._akamai_attempted_pages.clear()

    def tearDown(self):
        self._env.stop()
        monitor._poll_deadline = None
        monitor._akamai_attempted_pages.clear()


class AkamaiChallengeRecoveryTest(_MonitorTestBase):
    """check_slots_via_playwright with the guard faked: no threads, no real clock."""

    def setUp(self):
        super().setUp()
        self.clock = FakeClock()
        FakeGuard.instances = []
        FakeGuard.clock = self.clock
        FakeGuard.mem_mb_default = 300
        FakeGuard.budget_secs = 120
        self._patches = [
            mock.patch.object(monitor, "_token_from_playwright_context", return_value="BEARER t"),
            mock.patch.object(monitor, "_BrowserGuard", FakeGuard),
            mock.patch.object(monitor.time, "monotonic", self.clock.monotonic),
        ]
        self.mock_token = self._patches[0].start()
        for patcher in self._patches[1:]:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self._patches):
            patcher.stop()
        FakeGuard.clock = None
        super().tearDown()

    def _run_check(self, context_factory, env=None, restaurant=None, check=None):
        cm = FakePlaywrightCM(context_factory)
        buf = io.StringIO()
        check = check or monitor.check_slots_via_playwright
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                mock.patch("playwright.sync_api.sync_playwright", return_value=cm), \
                contextlib.redirect_stdout(buf):
            slots = check(restaurant or _restaurant())
        return slots, buf.getvalue(), cm

    def _run_check_expect_error(self, context_factory, env=None, error_type=RuntimeError, restaurant=None, check=None):
        cm = FakePlaywrightCM(context_factory)
        buf = io.StringIO()
        check = check or monitor.check_slots_via_playwright
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                mock.patch("playwright.sync_api.sync_playwright", return_value=cm), \
                contextlib.redirect_stdout(buf):
            with self.assertRaises(error_type) as caught:
                check(restaurant or _restaurant())
        return caught.exception, buf.getvalue(), cm

    # ── default: no challenge attempt ────────────────────────────────────

    def test_default_is_no_attempt_428_fails_after_one_load(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            ctx.verify_after_waits = 1
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory)
        ctx = cm.contexts[0]
        self.assertFalse(monitor._akamai_challenge_enabled())
        self.assertIn("HTTP 428 from availability API", str(exc))
        self.assertEqual(disney_bot._error_category(exc), "akamai")
        self.assertEqual(len(ctx.gotos), 1)
        self.assertEqual(_waits(ctx), [8000])
        self.assertEqual(len(ctx.evaluates), 1)
        self.assertEqual(ctx.pages[0].listener_log, [])
        self.assertEqual(ctx.pages[0].route_calls, [])
        self.assertEqual(ctx.new_page_calls, 0)
        self.assertTrue(ctx.closed)
        self.assertNotIn("waiting", stdout)
        self.assertNotIn("reloading", stdout)

    def test_challenge_enabled_parsing(self):
        for value, expected in (("0", False), ("1", True), ("2", True), ("9", True), ("-3", False), ("abc", False), ("", False)):
            with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_RETRIES": value}):
                self.assertEqual(monitor._akamai_challenge_enabled(), expected, value)

    # ── the single attempt ───────────────────────────────────────────────

    def test_attempt_reloads_without_the_app_then_refetches_once(self):
        day = _tomorrow()

        def factory():
            ctx = FakeContext(evaluate_results=[_challenge_428(15), _challenge_428(15), _ok_200(day)])
            ctx.verify_after_waits = 12
            return ctx

        slots, stdout, cm = self._run_check(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        page = ctx.pages[0]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].time, "19:50")
        self.assertEqual([(g["url"], g["wait_until"]) for g in ctx.gotos],
                         [(_restaurant_url(), "domcontentloaded"), (_restaurant_url(), "load")])
        self.assertEqual(ctx.new_page_calls, 0, "no second tab")
        self.assertEqual([p for p, _handler in page.route_calls], ["**/*"])
        kinds = [event[0] for event in ctx.events]
        self.assertLess(kinds.index("route"), [i for i, kind in enumerate(kinds) if kind == "goto"][1],
                        "the filter must be in place before the reload")
        self.assertEqual(_waits(ctx), [8000, 2000] + [1000] * 12 + [1000])
        self.assertEqual([args["token"] for args in ctx.evaluates], ["BEARER t"] * 3)
        self.assertEqual(ctx.evaluates[0], ctx.evaluates[2])
        self.assertEqual(self.mock_token.call_count, 1)
        self.assertEqual(page.listener_log, ["on", "remove"])
        self.assertTrue(ctx.closed)
        self.assertIn("reloading the page with only Akamai's scripts (browser at 300 MB)", stdout)
        self.assertIn("waiting up to 45s for the challenge to finish (browser at 300 MB, challenge ceiling 700 MB)", stdout)
        self.assertIn("Akamai challenge finished in 12s (1 proof rounds answered); availability API now returns HTTP 200", stdout)

    def test_attempt_gives_up_at_wait_cap_without_another_fetch(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertIn("HTTP 428 from availability API", str(exc))
        self.assertEqual(disney_bot._error_category(exc), "akamai")
        self.assertEqual(_waits(ctx), [8000, 2000] + [1000] * 45)
        self.assertEqual(len(ctx.evaluates), 2, "no further fetch when the challenge did not finish")
        self.assertEqual(len(ctx.gotos), 2)
        self.assertEqual(ctx.new_page_calls, 0)
        self.assertEqual(ctx.pages[0].listener_log, ["on", "remove"])
        self.assertTrue(ctx.closed)
        self.assertIn("abandoned after 45s: no verify call within 45s; 0 proof rounds answered.", stdout)

    def test_attempt_respects_wait_override(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        env = dict(ATTEMPT_ON, DISNEY_AKAMAI_CHALLENGE_WAIT_MS="20000")
        exc, stdout, cm = self._run_check_expect_error(factory, env=env)
        self.assertEqual(_waits(cm.contexts[0]), [8000, 2000] + [1000] * 20)

    def test_restaurant_page_memory_does_not_block_the_attempt(self):
        day = _tomorrow()

        def factory():
            ctx = FakeContext(evaluate_results=[_challenge_428(15), _challenge_428(15), _ok_200(day)])
            ctx.verify_after_waits = 3
            # 760 MB with the app loaded; the reload without it brings the browser down.
            ctx.on_goto = lambda n: setattr(FakeGuard.instances[-1], "mem_mb", 760 if n == 1 else 380)
            return ctx

        slots, stdout, cm = self._run_check(factory, env=ATTEMPT_ON)
        self.assertEqual(len(slots), 1)
        self.assertIn("(browser at 760 MB)", stdout)
        self.assertIn("(browser at 380 MB, challenge ceiling 700 MB)", stdout)

    def test_attempt_abandoned_when_browser_stays_over_ceiling_after_reload(self):
        FakeGuard.mem_mb_default = 720

        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(_waits(ctx), [8000, 2000, 1000])
        self.assertEqual(len(ctx.evaluates), 2)
        self.assertEqual(ctx.pages[0].listener_log, ["on", "remove"])
        self.assertIn("abandoned after 1s: the browser reached 720 MB (challenge ceiling 700 MB)", stdout)
        self.assertIn("HTTP 428 from availability API", str(exc))

    def test_challenge_ceiling_is_configurable(self):
        FakeGuard.mem_mb_default = 820
        day = _tomorrow()

        def factory():
            ctx = FakeContext(evaluate_results=[_challenge_428(15), _challenge_428(15), _ok_200(day)])
            ctx.verify_after_waits = 3
            return ctx

        env = dict(ATTEMPT_ON, DISNEY_AKAMAI_CHALLENGE_MEM_MB="900")
        slots, stdout, cm = self._run_check(factory, env=env)
        self.assertEqual(len(slots), 1)
        self.assertIn("challenge ceiling 900 MB", stdout)

    def test_attempt_abandoned_when_memory_crosses_ceiling_during_wait(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            ctx.verify_after_waits = 10

            def grow(wait_number):
                if wait_number == 4:
                    FakeGuard.instances[-1].mem_mb = 740
                    FakeGuard.instances[-1].largest = "renderer 610 MB"
            ctx.on_challenge_wait = grow
            ctx.proof_responses_per_wait = [200, 200, 403]
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(_waits(ctx), [8000, 2000] + [1000] * 4)
        self.assertEqual(len(ctx.evaluates), 2)
        self.assertEqual(ctx.pages[0].listener_log, ["on", "remove"])
        self.assertTrue(ctx.closed)
        self.assertIn("abandoned after 4s: the browser reached 740 MB (challenge ceiling 700 MB; largest process: renderer 610 MB); "
                      "3 proof rounds answered, 1 of them not HTTP 200.", stdout)

    def test_attempt_not_started_when_memory_cannot_be_measured(self):
        FakeGuard.mem_mb_default = None

        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(_waits(ctx), [8000])
        self.assertEqual(len(ctx.gotos), 1)
        self.assertEqual(ctx.pages[0].route_calls, [])
        self.assertIn("browser memory cannot be measured", stdout)

    def test_attempt_not_started_when_428_does_not_name_akamai_paths(self):
        for body in ('{"sec-cp-challenge": "true", "chlg_duration": 15}', "not json", "",
                     '{"verify_url": "https://elsewhere.example/-UKSQh/a/b"}', '{"verify_url": "/"}', '{"verify_url": 7}'):
            monitor._akamai_attempted_pages.clear()

            def factory():
                ctx = FakeContext()
                ctx._evaluate_always = {"status": 428, "data": None, "body": body}
                return ctx

            exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
            ctx = cm.contexts[0]
            self.assertEqual(_waits(ctx), [8000], body)
            self.assertEqual(len(ctx.gotos), 1, body)
            self.assertEqual(ctx.pages[0].route_calls, [], body)
            self.assertIn("does not name Akamai's script path", stdout, body)
            self.assertIn("HTTP 428 from availability API", str(exc))

    def test_failed_reload_abandons_the_attempt(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            ctx.pages[0].crash_on_goto_index = 2
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertIn("HTTP 428 from availability API", str(exc))
        self.assertEqual(len(ctx.evaluates), 1)
        self.assertEqual(_waits(ctx), [8000])
        self.assertEqual(ctx.pages[0].listener_log, [])
        self.assertTrue(ctx.closed)
        self.assertIn("attempt abandoned: the reload failed (Page.goto: Page crashed)", stdout)

    def test_reload_stopped_by_the_guard_reports_the_limit(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            ctx.pages[0].crash_on_goto_index = 2
            ctx.on_goto = lambda n: setattr(FakeGuard.instances[-1], "tripped", "ran past the 120s page time limit" if n == 2 else "")
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        self.assertEqual(str(exc), "[monitor] Ohana: browser stopped because it ran past the 120s page time limit.")
        self.assertNotIn("the reload failed", stdout)
        self.assertTrue(cm.contexts[0].closed)

    def test_no_wait_when_the_reloaded_page_is_not_challenged(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_challenge_428(15), _ok_200(day)])

        slots, stdout, cm = self._run_check(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(len(slots), 1)
        self.assertEqual(_waits(ctx), [8000, 2000])
        self.assertEqual(ctx.pages[0].listener_log, ["on", "remove"])
        self.assertIn("after the reload the availability API returns HTTP 200", stdout)

    def test_failed_verify_call_is_not_followed_by_a_refetch(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            ctx.verify_after_waits = 5
            ctx.verify_status = 403
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(len(ctx.evaluates), 2)
        self.assertEqual(_waits(ctx), [8000, 2000] + [1000] * 5)
        self.assertIn("verify call returned HTTP 403 after 5s (1 proof rounds answered); not re-fetching", stdout)

    def test_only_one_attempt_per_restaurant_per_poll(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        self._run_check_expect_error(factory, env=ATTEMPT_ON)
        # The same restaurant page again (another watch): no second attempt after a failed one.
        exc, stdout, cm = self._run_check_expect_error(
            factory, env=ATTEMPT_ON, restaurant=_restaurant(name="Ohana dinner", party_size=4))
        self.assertEqual(_waits(cm.contexts[0]), [8000])
        self.assertEqual(len(cm.contexts[0].gotos), 1)
        self.assertEqual(cm.contexts[0].pages[0].route_calls, [])
        self.assertIn("this restaurant's one attempt for this poll is already used", stdout)

        with mock.patch.dict(os.environ, ATTEMPT_ON):
            monitor.start_poll_budget()
        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        self.assertEqual(len(_waits(cm.contexts[0])), 47, "a new poll gets a new attempt")

    def test_each_restaurant_gets_its_own_attempt_in_one_poll(self):
        day = _tomorrow()

        def cleared():
            ctx = FakeContext(evaluate_results=[_challenge_428(15), _challenge_428(15), _ok_200(day)])
            ctx.verify_after_waits = 12
            return ctx

        def challenged():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        with mock.patch.dict(os.environ, ATTEMPT_ON):
            monitor.start_poll_budget()
        space = _restaurant(name="Space 220 Lounge", slug="space-220-lounge", facility_id="19634138")
        for restaurant in (_restaurant(), space):
            page_url = f"https://disneyworld.disney.go.com/dine-res/restaurant/{restaurant['slug']}"
            slots, stdout, cm = self._run_check(cleared, env=ATTEMPT_ON, restaurant=restaurant)
            ctx = cm.contexts[0]
            self.assertEqual(len(slots), 1, restaurant["name"])
            self.assertEqual([(g["url"], g["wait_until"]) for g in ctx.gotos],
                             [(page_url, "domcontentloaded"), (page_url, "load")])
            self.assertEqual(len(ctx.evaluates), 3, restaurant["name"])
            self.assertIn("Akamai challenge finished in 12s", stdout)
            self.assertNotIn("already used", stdout)

        # Either restaurant challenged again in the same poll does not get a second attempt.
        for restaurant in (_restaurant(), space):
            exc, stdout, cm = self._run_check_expect_error(challenged, env=ATTEMPT_ON, restaurant=restaurant)
            self.assertEqual(len(cm.contexts[0].gotos), 1, restaurant["name"])
            self.assertEqual(len(cm.contexts[0].evaluates), 1, restaurant["name"])
            self.assertIn("this restaurant's one attempt for this poll is already used", stdout)

    def test_wait_is_cut_to_fit_the_page_time_budget(self):
        FakeGuard.budget_secs = 48   # 8s warm-up and 2s settle leave 38s; 15s stay reserved for re-fetch and close

        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        self.assertEqual(_waits(cm.contexts[0]), [8000, 2000] + [1000] * 23)
        self.assertIn("waiting up to 23s", stdout)

    def test_attempt_not_started_when_page_budget_nearly_used(self):
        FakeGuard.budget_secs = 26   # 18s left after warm-up, under the 15s reserve + 5s minimum

        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(_waits(ctx), [8000])
        self.assertEqual(len(ctx.gotos), 1)
        self.assertIn("not attempting it because the page's time budget is nearly used", stdout)

    def test_attempt_abandoned_when_the_reload_uses_up_the_page_budget(self):
        FakeGuard.budget_secs = 29   # 21s left after warm-up is enough to start; 19s after the reload is not enough to wait

        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON)
        ctx = cm.contexts[0]
        self.assertEqual(_waits(ctx), [8000, 2000])
        self.assertEqual(len(ctx.evaluates), 2)
        self.assertEqual(ctx.pages[0].listener_log, ["on", "remove"])
        self.assertIn("attempt abandoned: the page's time budget is nearly used", stdout)

    # ── what the reload lets through ─────────────────────────────────────

    def _filter(self, body=None):
        page = FakePage(FakeContext())
        handler = monitor._akamai_only_route(page, _challenge_428(15) if body is None else {"status": 428, "body": body})
        return page, handler

    def _decide(self, handler, page, url, navigation=False, frame=None):
        route = FakeRoute(url, navigation=navigation, frame=page.main_frame if frame is None else frame)
        handler(route)
        return route.outcome

    def test_reload_filter_lets_only_akamai_through(self):
        page, handler = self._filter()
        host = "https://disneyworld.disney.go.com"
        allowed = [
            (_restaurant_url(), True),
            (host + "/-UKSQh/rqROa/-14a5/Qrfw/DLuh5r/Wh9aIw/PgQYM34S/VVso", False),
            (host + "/-UKSQh/rqROa/-14a5/Qrfw/1JuhSzbSuam0rLuXuD/E3tkIw/ZChsdToS/EhI", False),
            (host + "/_sec/verify?provider=crypto", False),
            (host + "/_sec/cp_challenge/verify", False),
            (host + "/dine-res/api/availability/2/2026-12-02,2026-12-02?facilityId=1&entityType=restaurant", False),
            (host + "/prodksd/media/waiting-room-assets/processing_request.html", False),
            (host + "/prodksd/media/waiting-room-assets/processing_request.html?x=1", False),
        ]
        blocked = [
            (host + "/dine-res/main-ABCDEF.js", False),
            (host + "/dine-res/polyfills-5FDKUQTZ.js", False),
            (host + "/dine-res/api/dine-detail/ohana?entityType=restaurant", False),
            (host + "/authenticator/authenticator-bundle.js?feature=dine-res-spa", False),
            (host + "/profile-api/authentication/get-client-token/", False),
            (host + "/prodksd/media/waiting-room-assets/other.html", False),
            ("https://cdn.registerdisney.go.com/v4/bundle/web/TPR-WDW-LBJS.WEB/en-US", False),
            ("https://k-aus1.clicktale.net/v2/recording", False),
            ("https://elsewhere.example/-UKSQh/rqROa/x", False),
            ("https://elsewhere.example/_sec/verify", False),
            ("https://secure.cdn1.wdpromedia.com/media/waiting-room-assets/_render_space_mountain_v1.jpg", False),
        ]
        for url, navigation in allowed:
            self.assertEqual(self._decide(handler, page, url, navigation), "continue", url)
        for url, navigation in blocked:
            self.assertEqual(self._decide(handler, page, url, navigation), "abort", url)

    def test_reload_filter_blocks_navigations_in_sub_frames(self):
        page, handler = self._filter()
        self.assertEqual(self._decide(handler, page, "https://disneyworld.disney.go.com/authenticator/responder.html",
                                      navigation=True, frame=object()), "abort")
        self.assertEqual(self._decide(handler, page, "https://elsewhere.example/", navigation=True), "abort")

    def test_reload_filter_reads_the_akamai_path_from_the_428(self):
        body = json.dumps({"verify_url": "/zQ9-new/a/b/c", "branding_cust_url": ""})
        page, handler = self._filter(body)
        self.assertEqual(self._decide(handler, page, "https://disneyworld.disney.go.com/zQ9-new/x/y"), "continue")
        self.assertEqual(self._decide(handler, page, "https://disneyworld.disney.go.com/-UKSQh/x/y"), "abort")
        self.assertEqual(self._decide(handler, page, "https://disneyworld.disney.go.com/"), "abort")

    def test_reload_filter_never_raises(self):
        page, handler = self._filter()
        for failing in ("continue", "abort", "request"):
            route = FakeRoute("https://disneyworld.disney.go.com/_sec/verify" if failing != "abort" else "https://x.example/",
                              frame=page.main_frame, fail=failing)
            handler(route)
        self.assertEqual(route.outcome, "abort", "a request that cannot be read is blocked")

    def test_wait_secs_parsing_and_clamps(self):
        self.assertEqual(monitor._akamai_challenge_wait_secs({"body": '{"chlg_duration":15}'}), 45)
        self.assertEqual(monitor._akamai_challenge_wait_secs({}), 45)
        self.assertEqual(monitor._akamai_challenge_wait_secs({"body": "not-json"}), 45)
        self.assertEqual(monitor._akamai_challenge_wait_secs({"body": "[1,2]"}), 45)
        self.assertEqual(monitor._akamai_challenge_wait_secs({"body": '{"chlg_duration":500}'}), 90)
        self.assertEqual(monitor._akamai_challenge_wait_secs({"body": '{"chlg_duration":1}'}), 35)
        for value, expected in (("1000", 5), ("30000", 30), ("999999", 90), ("abc", 45)):
            with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_WAIT_MS": value}):
                self.assertEqual(monitor._akamai_challenge_wait_secs({"body": '{"chlg_duration":15}'}), expected, value)

    # ── paths that must not change ───────────────────────────────────────

    def test_first_fetch_200_does_one_goto_and_only_warmup_wait(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_ok_200(day)])

        for env in ({}, ATTEMPT_ON):
            slots, stdout, cm = self._run_check(factory, env=env)
            ctx = cm.contexts[0]
            self.assertEqual(len(slots), 1)
            self.assertEqual(len(ctx.gotos), 1)
            self.assertEqual(ctx.gotos[0]["url"], _restaurant_url())
            self.assertEqual(_waits(ctx), [8000])
            self.assertEqual(ctx.pages[0].listener_log, [])
            self.assertEqual(ctx.pages[0].route_calls, [])
            self.assertNotIn("Akamai", stdout)
            self.assertIn("1 slot(s) found via Playwright", stdout)

    def test_first_fetch_404_returns_empty_after_one_goto(self):
        def factory():
            return FakeContext(evaluate_results=[{"status": 404, "data": None, "body": ""}])

        slots, stdout, cm = self._run_check(factory)
        ctx = cm.contexts[0]
        self.assertEqual(slots, [])
        self.assertEqual(len(ctx.gotos), 1)
        self.assertIn("no availability returned by Disney", stdout)

    def test_auth_required_propagates_and_closes_the_browser(self):
        self.mock_token.side_effect = monitor.DisneyAuthRequired("Disney auth required: missing")

        def factory():
            return FakeContext()

        exc, stdout, cm = self._run_check_expect_error(factory, env=ATTEMPT_ON, error_type=monitor.DisneyAuthRequired)
        ctx = cm.contexts[0]
        self.assertEqual(disney_bot._error_category(exc), "disney_auth")
        self.assertTrue(ctx.closed)
        self.assertEqual(len(ctx.evaluates), 0)
        self.assertEqual(FakeGuard.instances[-1].stop_calls, 1)

    def test_launch_args_are_unchanged(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_ok_200(day)])

        slots, stdout, cm = self._run_check(factory)
        kwargs = cm.contexts[0].launch_kwargs
        self.assertEqual(kwargs, {"headless": monitor._playwright_headless(), "args": ["--no-sandbox"]})
        self.assertEqual(cm.contexts[0].profile_dir, monitor._playwright_profile_dir())

    # ── guard wiring ─────────────────────────────────────────────────────

    def test_guard_runs_from_before_launch_until_after_close(self):
        def factory():
            return FakeContext(evaluate_results=[_ok_200(_tomorrow())])

        slots, stdout, cm = self._run_check(factory)
        guard = FakeGuard.instances[-1]
        self.assertEqual((guard.start_calls, guard.stop_calls), (1, 1))
        self.assertTrue(cm.contexts[0].closed)
        self.assertIn("browser memory peak 300 MB", stdout)

    def test_error_after_guard_trip_names_the_limit(self):
        def factory():
            ctx = FakeContext()

            def blocked_call_fails(script, arg):
                FakeGuard.instances[-1].tripped = "ran past the 120s page time limit"
                raise Exception("Page.evaluate: Target crashed")
            ctx._evaluate_always = blocked_call_fails
            ctx.close_error = Exception("Target page, context or browser has been closed")
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory)
        self.assertEqual(str(exc), "[monitor] Ohana: browser stopped because it ran past the 120s page time limit.")
        self.assertNotEqual(disney_bot._error_category(exc), "disney_auth")
        self.assertTrue(cm.contexts[0].closed)
        self.assertEqual(FakeGuard.instances[-1].stop_calls, 1)

    def test_untripped_errors_pass_through_unchanged(self):
        def factory():
            ctx = FakeContext()
            ctx.pages[0].always_fail_goto = "net::ERR_HTTP2_PROTOCOL_ERROR"
            return ctx

        exc, stdout, cm = self._run_check_expect_error(factory, error_type=Exception)
        self.assertEqual(str(exc), "net::ERR_HTTP2_PROTOCOL_ERROR")
        self.assertTrue(cm.contexts[0].closed)
        self.assertEqual(FakeGuard.instances[-1].stop_calls, 1)

    def test_poll_budget_used_up_skips_the_launch(self):
        with mock.patch.dict(os.environ, {"DISNEY_POLL_BUDGET_SECS": "360"}):
            monitor.start_poll_budget()
        self.clock.advance(361)

        def factory():
            return FakeContext(evaluate_results=[_ok_200(_tomorrow())])

        exc, stdout, cm = self._run_check_expect_error(factory)
        self.assertIn("this poll's browser time budget is used up", str(exc))
        self.assertIsNone(cm.contexts[0].launch_kwargs, "no browser may be launched")
        self.assertEqual(FakeGuard.instances, [])
        self.assertNotEqual(disney_bot._error_category(exc), "disney_auth")

        monitor.extend_poll_budget(120)   # time spent in login recovery is given back
        slots, stdout, cm = self._run_check(factory)
        self.assertEqual(len(slots), 1)

    def test_poll_budget_env_is_clamped(self):
        for value, expected in (("", 360), ("abc", 360), ("5", 60), ("240", 240), ("99999", 900)):
            with mock.patch.dict(os.environ, {"DISNEY_POLL_BUDGET_SECS": value}):
                monitor.start_poll_budget()
            self.assertEqual(monitor._poll_deadline - self.clock.now, expected, value)

    # ── scheduled activities (the path that still works today) ───────────

    def _activity(self):
        return _restaurant(name="Harmony Barber Shop", slug="harmony-barber-shop", booking_type="scheduled_activity")

    def test_scheduled_activity_check_runs_under_the_guard(self):
        def factory():
            return FakeContext(evaluate_results=[{"status": 200, "data": {}}, {"status": 404, "data": None}])

        slots, stdout, cm = self._run_check(factory, restaurant=self._activity(),
                                            check=monitor.check_scheduled_activity_slots_via_playwright)
        ctx = cm.contexts[0]
        guard = FakeGuard.instances[-1]
        self.assertEqual(slots, [])
        self.assertEqual(ctx.launch_kwargs, {"headless": monitor._playwright_headless(), "args": ["--no-sandbox"]})
        self.assertEqual(len(ctx.gotos), 1)
        self.assertEqual(_waits(ctx), [8000])
        self.assertTrue(ctx.closed)
        self.assertEqual((guard.start_calls, guard.stop_calls), (1, 1))
        self.assertIn("0 slot(s) found via scheduled-activity API", stdout)

    def test_scheduled_activity_early_return_and_errors_close_the_browser(self):
        far = (date.today() + timedelta(days=400)).isoformat()

        def early():
            return FakeContext(evaluate_results=[{"status": 200, "data": {"bookableStartDate": far}}])

        slots, stdout, cm = self._run_check(early, restaurant=self._activity(),
                                            check=monitor.check_scheduled_activity_slots_via_playwright)
        self.assertEqual(slots, [])
        self.assertTrue(cm.contexts[0].closed)
        self.assertEqual(FakeGuard.instances[-1].stop_calls, 1)

        def expired():
            return FakeContext(evaluate_results=[{"status": 401, "data": None}])

        exc, stdout, cm = self._run_check_expect_error(expired, restaurant=self._activity(),
                                                       check=monitor.check_scheduled_activity_slots_via_playwright)
        self.assertEqual(disney_bot._error_category(exc), "disney_auth")
        self.assertTrue(cm.contexts[0].closed)

    def test_poll_starts_the_budget_and_recovery_time_is_given_back(self):
        calls = []
        with mock.patch.object(monitor, "start_poll_budget", side_effect=lambda: calls.append("start")), \
                mock.patch.object(monitor, "extend_poll_budget", side_effect=lambda secs: calls.append(("extend", secs))), \
                mock.patch.object(disney_bot.storage, "read_json", return_value={}), \
                mock.patch.object(disney_bot.storage, "write_json"), \
                mock.patch.object(disney_bot.watch_store, "load_watches", return_value=[{"id": "w1"}]), \
                mock.patch.object(disney_bot.watch_store, "grouped_restaurant_requests",
                                  return_value=[{"name": "Ohana", "watches": []}]), \
                mock.patch.object(disney_bot, "check_slots_for_restaurant",
                                  side_effect=monitor.DisneyAuthRequired("Disney auth required: x")), \
                mock.patch.object(disney_bot, "attempt_disney_session_recovery",
                                  side_effect=lambda: self.clock.advance(200) or False), \
                mock.patch.object(disney_bot, "_load_open_keys", return_value=set()), \
                mock.patch.object(disney_bot, "_save_open_keys"), \
                mock.patch.object(disney_bot, "_configured_owner_phones", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()):
            disney_bot.poll({})
        self.assertEqual(calls, ["start", ("extend", 200.0)])


class BrowserGuardTest(_MonitorTestBase):
    """The real _BrowserGuard against a scripted process table."""

    PROCS = [
        (100, "/opt/chrome --user-data-dir=/opt/disney-dining-bot/.browser-profile --no-sandbox"),
        (101, "/opt/chrome --type=zygote"),
        (102, "/opt/chrome --type=gpu-process"),
        (103, "/opt/chrome --type=renderer --lang=en-US"),
        (104, "/opt/chrome --type=renderer --lang=en-US"),
    ]

    def setUp(self):
        super().setUp()
        self.memory_kb = {100: 90_000, 101: 10_000, 102: 40_000, 103: 250_000, 104: 30_000}
        self.kills = []
        self._patches = [
            mock.patch.object(monitor, "_browser_processes", side_effect=lambda: list(self.PROCS)),
            mock.patch.object(monitor, "_process_memory_kb", side_effect=lambda pid: self.memory_kb[pid]),
            mock.patch.object(monitor.os, "kill", side_effect=lambda pid, sig: self.kills.append((pid, sig))),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self._patches):
            patcher.stop()
        super().tearDown()

    def _check(self, guard):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            tripped = guard.check()
        return tripped, buf.getvalue()

    def test_defaults(self):
        guard = monitor._BrowserGuard("Ohana")
        self.assertEqual(guard.budget_secs, 120)
        self.assertEqual(guard.mem_limit_mb, 1000)
        self.assertAlmostEqual(guard.seconds_left(), 120, delta=1)

    def test_under_limits_samples_memory_and_kills_nothing(self):
        guard = monitor._BrowserGuard("Ohana")
        self.assertIsNone(guard.mem_mb)
        tripped, stdout = self._check(guard)
        self.assertFalse(tripped)
        self.assertEqual(guard.mem_mb, 420_000 // 1024)
        self.assertEqual(guard.peak_mb, guard.mem_mb)
        self.assertEqual(guard.largest, "renderer 244 MB")
        self.assertEqual(guard.tripped, "")
        self.assertEqual(self.kills, [])
        self.assertEqual(stdout, "")
        self.memory_kb[103] = 100_000
        self._check(guard)
        self.assertEqual(guard.mem_mb, 270_000 // 1024)
        self.assertEqual(guard.peak_mb, 420_000 // 1024, "peak is kept")
        self.assertEqual(guard.largest, "renderer 97 MB")
        self.memory_kb[100] = 300_000
        self._check(guard)
        self.assertEqual(guard.largest, "main 292 MB")

    def test_memory_over_limit_kills_only_the_renderers(self):
        with mock.patch.dict(os.environ, {"DISNEY_BROWSER_MEM_LIMIT_MB": "600"}):
            guard = monitor._BrowserGuard("Ohana")
        self.memory_kb[103] = 700_000
        tripped, stdout = self._check(guard)
        self.assertTrue(tripped)
        self.assertEqual(self.kills, [(103, signal.SIGKILL), (104, signal.SIGKILL)])
        self.assertEqual(guard.tripped, "used 849 MB of memory (limit 600 MB)")
        self.assertIn("stopping the browser: it used 849 MB of memory (limit 600 MB)", stdout)

    def test_past_deadline_kills_only_the_renderers(self):
        with mock.patch.dict(os.environ, {"DISNEY_PAGE_BUDGET_SECS": "90"}):
            guard = monitor._BrowserGuard("Ohana")
        guard.deadline = time.monotonic() - 1
        tripped, stdout = self._check(guard)
        self.assertTrue(tripped)
        self.assertEqual(self.kills, [(103, signal.SIGKILL), (104, signal.SIGKILL)])
        self.assertEqual(guard.tripped, "ran past the 90s page time limit")

    def test_stopped_guard_never_kills(self):
        guard = monitor._BrowserGuard("Ohana")
        guard.deadline = time.monotonic() - 1
        guard._stop.set()
        tripped, stdout = self._check(guard)
        self.assertFalse(tripped)
        self.assertEqual(self.kills, [], "a late sample must not kill the next check's browser")
        self.assertEqual(guard.tripped, "")
        self.assertEqual(stdout, "")

    def test_page_deadline_never_outlives_the_poll_deadline(self):
        monitor._poll_deadline = time.monotonic() + 20
        guard = monitor._BrowserGuard("Ohana")
        self.assertAlmostEqual(guard.seconds_left(), 20, delta=1)
        guard.deadline = time.monotonic() - 1
        self._check(guard)
        self.assertEqual(guard.tripped, "was still open when this poll's time budget ran out")
        monitor._poll_deadline = time.monotonic() + 500
        guard = monitor._BrowserGuard("Ohana")
        self.assertAlmostEqual(guard.seconds_left(), 120, delta=1)

    def test_limits_are_clamped(self):
        env = {"DISNEY_PAGE_BUDGET_SECS": "1", "DISNEY_BROWSER_MEM_LIMIT_MB": "5"}
        with mock.patch.dict(os.environ, env):
            guard = monitor._BrowserGuard("Ohana")
        self.assertEqual((guard.budget_secs, guard.mem_limit_mb), (30, 200))
        env = {"DISNEY_PAGE_BUDGET_SECS": "99999", "DISNEY_BROWSER_MEM_LIMIT_MB": "abc"}
        with mock.patch.dict(os.environ, env):
            guard = monitor._BrowserGuard("Ohana")
        self.assertEqual((guard.budget_secs, guard.mem_limit_mb), (300, 1000))

    def test_no_browser_visible_means_no_memory_reading_and_no_kill(self):
        with mock.patch.object(monitor, "_browser_processes", return_value=[]):
            guard = monitor._BrowserGuard("Ohana")
            tripped, _ = self._check(guard)
        self.assertFalse(tripped)
        self.assertIsNone(guard.mem_mb)
        self.assertEqual(self.kills, [])

    def test_kill_survives_processes_that_already_exited(self):
        with mock.patch.object(monitor.os, "kill", side_effect=ProcessLookupError):
            monitor._BrowserGuard._kill(list(self.PROCS), renderers_only=False)

    def _run_thread(self, stop_after_trip):
        self.profile = tempfile.mkdtemp(prefix="mtf-test-profile-")
        self.addCleanup(shutil.rmtree, self.profile, ignore_errors=True)
        for leftover in ("SingletonLock", "SingletonCookie", "SingletonSocket", "Cookies"):
            with open(os.path.join(self.profile, leftover), "w") as fh:
                fh.write("x")
        with mock.patch.object(monitor, "_GUARD_INTERVAL_SECS", 0.01), \
                mock.patch.object(monitor, "_GUARD_KILL_GRACE_SECS", 0.3), \
                mock.patch.dict(os.environ, {"DISNEY_BROWSER_MEM_LIMIT_MB": "200",
                                             "DISNEY_BROWSER_PROFILE_DIR": self.profile}), \
                contextlib.redirect_stdout(io.StringIO()):
            guard = monitor._BrowserGuard("Ohana")
            guard.start()
            deadline = time.monotonic() + 5
            while not guard.tripped and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(guard.tripped)
            if stop_after_trip:
                guard.stop()
            else:
                guard._thread.join(timeout=5)
            self.assertFalse(guard._thread.is_alive())
        return guard

    def test_thread_kills_everything_when_the_caller_stays_stuck(self):
        self._run_thread(stop_after_trip=False)
        self.assertEqual(self.kills[:2], [(103, signal.SIGKILL), (104, signal.SIGKILL)])
        self.assertEqual(sorted(pid for pid, _sig in self.kills[2:]), [100, 101, 102, 103, 104])
        self.assertEqual(os.listdir(self.profile), ["Cookies"], "stale locks removed, profile data kept")

    def test_thread_leaves_the_main_process_alone_when_the_caller_closes_in_time(self):
        self._run_thread(stop_after_trip=True)
        self.assertEqual(self.kills, [(103, signal.SIGKILL), (104, signal.SIGKILL)])
        self.assertEqual(len(os.listdir(self.profile)), 4, "a browser that closed by itself keeps its own files")

    def test_guarded_browser_reports_trip_and_swallows_close_error(self):
        ctx = FakeContext()
        ctx.close_error = Exception("Target page, context or browser has been closed")
        with mock.patch.dict(os.environ, {"DISNEY_BROWSER_MEM_LIMIT_MB": "200"}), \
                mock.patch.object(monitor, "_GUARD_INTERVAL_SECS", 0.01), \
                contextlib.redirect_stdout(io.StringIO()) as buf, \
                self.assertRaises(RuntimeError) as caught:
            with monitor._guarded_browser(FakePlaywright(ctx), "Ohana") as (context, guard):
                deadline = time.monotonic() + 5
                while not guard.tripped and time.monotonic() < deadline:
                    time.sleep(0.01)
                raise Exception("Page.evaluate: Target crashed")
        self.assertEqual(str(caught.exception),
                         "[monitor] Ohana: browser stopped because it used 410 MB of memory (limit 200 MB).")
        self.assertTrue(ctx.closed)
        self.assertEqual(self.kills, [(103, signal.SIGKILL), (104, signal.SIGKILL)])
        self.assertIn("browser memory peak 410 MB", buf.getvalue())


@unittest.skipUnless(os.path.isdir("/proc/self"), "needs Linux /proc")
class BrowserProcessDiscoveryTest(_MonitorTestBase):
    """_browser_processes / _process_memory_kb / _kill against real processes (no browser)."""

    def setUp(self):
        super().setUp()
        sleeper = "import time; time.sleep(60)"
        # The flags are assembled inside each script so that a parent's own
        # command line (which carries the script text) does not contain them.
        parent = (
            "import subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', {sleeper!r}, '--type' + '=renderer'])\n"
            f"subprocess.Popen([sys.executable, '-c', {sleeper!r}, '--type' + '=gpu-process'])\n"
            "time.sleep(60)\n"
        )
        # Stand-ins: a "driver" with no browser flags, whose child looks like a browser main process.
        driver = (
            "import subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', {parent!r}, '--user-data' + '-dir=/tmp/fake-profile'])\n"
            "time.sleep(60)\n"
        )
        self.driver = subprocess.Popen([sys.executable, "-c", driver])
        self.bystander = subprocess.Popen([sys.executable, "-c", sleeper])
        deadline = time.monotonic() + 10
        while len(monitor._browser_processes()) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)

    def tearDown(self):
        monitor._BrowserGuard._kill(monitor._browser_processes(), renderers_only=False)
        for proc in (self.driver, self.bystander):
            proc.kill()
            proc.wait(timeout=10)
        super().tearDown()

    def test_finds_the_browser_tree_and_nothing_else(self):
        procs = monitor._browser_processes()
        kinds = sorted("main" if "--user-data-dir=" in cmd else cmd.split("--type=")[1].strip() for _pid, cmd in procs)
        self.assertEqual(kinds, ["gpu-process", "main", "renderer"])
        pids = {pid for pid, _cmd in procs}
        self.assertNotIn(self.driver.pid, pids)
        self.assertNotIn(self.bystander.pid, pids)
        self.assertNotIn(os.getpid(), pids)
        for pid in pids:
            self.assertGreater(monitor._process_memory_kb(pid), 0)
        self.assertEqual(monitor._process_memory_kb(2 ** 30), 0)

    def test_renderer_kill_takes_only_the_renderer(self):
        procs = monitor._browser_processes()
        renderer = next(pid for pid, cmd in procs if "--type=renderer" in cmd)
        monitor._BrowserGuard._kill(procs, renderers_only=True)
        deadline = time.monotonic() + 10

        def alive(pid):
            try:
                with open(f"/proc/{pid}/stat") as fh:
                    return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
            except OSError:
                return False

        while alive(renderer) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(renderer))
        left = sorted("main" if "--user-data-dir=" in cmd else cmd.split("--type=")[1].strip()
                      for pid, cmd in monitor._browser_processes() if alive(pid))
        self.assertEqual(left, ["gpu-process", "main"])
        self.assertIsNone(self.driver.poll())
        self.assertIsNone(self.bystander.poll())


class SeederRecoveryTest(unittest.TestCase):
    def setUp(self):
        FakeGuard.clock = None
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        self._env.stop()

    def test_ac10_disney_session_seconds_left_from_cookie_and_failures(self):
        live = FakeContext(cookies=[_token_cookie(3600)])
        left = monitor.disney_session_seconds_left(live)
        self.assertGreaterEqual(left, 3400)
        self.assertLessEqual(left, 3600)

        expired = FakeContext(cookies=[_token_cookie(-60)])
        self.assertEqual(monitor.disney_session_seconds_left(expired), 0)

        missing = FakeContext(cookies=[{"name": "other", "value": "x"}])
        self.assertEqual(monitor.disney_session_seconds_left(missing), 0)

        garbage = FakeContext(cookies=[{
            "name": monitor.TOKEN_COOKIE_NAME,
            "value": "%%%not-a-token%%%",
        }])
        self.assertEqual(monitor.disney_session_seconds_left(garbage), 0)

        boom = FakeContext()
        boom.cookies_error = RuntimeError("cookie store unavailable")
        self.assertEqual(monitor.disney_session_seconds_left(boom), 0)

    def test_ac11_seed_crashed_goto_continues_on_fresh_page(self):
        ctx = FakeContext()
        dead = ctx.pages[0]
        dead.always_fail_goto = "Page.goto: Page crashed"
        with contextlib.redirect_stdout(io.StringIO()):
            returned = seed_disney_session._goto_with_retries(
                dead, "https://disneyworld.disney.go.com/dine-res/restaurant/space-220-lounge/"
            )
        self.assertEqual(ctx.new_page_calls, 1)
        self.assertIs(returned, ctx.created_pages[0])
        self.assertIsNot(returned, dead)
        self.assertEqual(len(dead.goto_calls), 1)
        self.assertEqual(len(returned.goto_calls), 1)
        self.assertEqual(
            returned.goto_calls[0]["url"],
            "https://disneyworld.disney.go.com/dine-res/restaurant/space-220-lounge/",
        )

    def test_ac12_seed_non_crash_retries_same_page_with_wait_until_fallback(self):
        ctx = FakeContext()
        page = ctx.pages[0]
        page.fail_first_n = 2
        page.fail_goto_message = "net::ERR_HTTP2_PROTOCOL_ERROR"
        with contextlib.redirect_stdout(io.StringIO()):
            returned = seed_disney_session._goto_with_retries(
                page, "https://disneyworld.disney.go.com/login"
            )
        self.assertIs(returned, page)
        self.assertEqual(ctx.new_page_calls, 0)
        self.assertEqual(
            [call["wait_until"] for call in page.goto_calls],
            ["domcontentloaded", "load", "commit"],
        )

    def test_ac13_seed_all_attempts_fail_raises_last_after_exactly_attempts_gotos(self):
        ctx = FakeContext()
        page = ctx.pages[0]
        page.always_fail_goto = "net::ERR_HTTP2_PROTOCOL_ERROR"
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(Exception) as caught:
            seed_disney_session._goto_with_retries(
                page, "https://disneyworld.disney.go.com/login", attempts=4
            )
        self.assertIn("ERR_HTTP2_PROTOCOL_ERROR", str(caught.exception))
        self.assertEqual(len(page.goto_calls), 4)
        self.assertEqual(ctx.new_page_calls, 0)

    def _run_seed_main(self, cookies, env=None):
        holder = {}

        def factory():
            ctx = FakeContext(cookies=cookies)
            holder["ctx"] = ctx
            return ctx

        merged = {
            "DISNEY_HEADLESS": "false",
            "DISNEY_LOGIN_EMAIL": "",
            "DISNEY_LOGIN_PASSWORD": "",
        }
        if env:
            merged.update(env)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, merged, clear=False), \
                mock.patch("playwright.sync_api.sync_playwright", return_value=FakePlaywrightCM(factory)), \
                mock.patch("builtins.input", side_effect=EOFError), \
                contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as caught:
                seed_disney_session.main()
        return caught.exception.code, buf.getvalue(), holder["ctx"]

    def test_ac14_seed_main_skips_login_when_session_already_valid(self):
        code, stdout, ctx = self._run_seed_main([_token_cookie(3600)])
        self.assertEqual(code, 0)
        self.assertIn("skipping login", stdout)
        login_gotos = [call["url"] for call in ctx.gotos if "/login" in call["url"]]
        self.assertEqual(login_gotos, [])

    def test_ac14_seed_force_login_bypasses_short_circuit(self):
        code, stdout, ctx = self._run_seed_main(
            [_token_cookie(3600)],
            env={"DISNEY_SEED_FORCE_LOGIN": "1"},
        )
        self.assertNotIn("skipping login", stdout)
        self.assertTrue(any("/login" in call["url"] for call in ctx.gotos))
        self.assertEqual(code, 0)

    def test_ac15_seed_main_expired_token_does_not_short_circuit(self):
        code, stdout, ctx = self._run_seed_main([_token_cookie(-60)])
        self.assertNotIn("skipping login", stdout)
        self.assertTrue(any("/login" in call["url"] for call in ctx.gotos))

    def test_ac15_seed_main_token_below_session_ok_min_does_not_short_circuit(self):
        self.assertGreater(seed_disney_session.SESSION_OK_MIN_SECS, 300)
        code, stdout, ctx = self._run_seed_main([_token_cookie(300)])
        self.assertNotIn("skipping login", stdout)
        self.assertTrue(any("/login" in call["url"] for call in ctx.gotos))


if __name__ == "__main__":
    unittest.main()
