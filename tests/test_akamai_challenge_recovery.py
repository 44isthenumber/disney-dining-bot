import base64
import contextlib
import io
import json
import os
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

    def on(self, event, handler):
        if event == "crash":
            self.crash_handlers.append(handler)

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

    def goto(self, url, wait_until="domcontentloaded", timeout=None):
        self._goto_n += 1
        call = {"url": url, "wait_until": wait_until, "timeout": timeout, "page": self}
        self.goto_calls.append(call)
        self.context.events.append(("goto", url, wait_until, self))
        self.context.gotos.append(call)
        self.url = url
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


class FakeContext:
    def __init__(self, cookies=None, evaluate_results=None):
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


class AkamaiChallengeRecoveryTest(unittest.TestCase):
    def setUp(self):
        monitor._akamai_retry_blocked_until = 0.0
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for key in (
            "DISNEY_AKAMAI_CHALLENGE_RETRIES",
            "DISNEY_AKAMAI_CHALLENGE_WAIT_MS",
            "DISNEY_AKAMAI_WARMUP_MS",
            "DISNEY_SEED_FORCE_LOGIN",
            "DISNEY_LOGIN_EMAIL",
            "DISNEY_LOGIN_PASSWORD",
        ):
            os.environ.pop(key, None)
        self._token = mock.patch.object(
            monitor, "_token_from_playwright_context", return_value="BEARER t"
        )
        self.mock_token = self._token.start()

    def tearDown(self):
        self._token.stop()
        self._env.stop()
        monitor._akamai_retry_blocked_until = 0.0

    def _run_check(self, context_factory, env=None):
        cm = FakePlaywrightCM(context_factory)
        buf = io.StringIO()
        env = env or {}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch("playwright.sync_api.sync_playwright", return_value=cm), \
                contextlib.redirect_stdout(buf):
            slots = monitor.check_slots_via_playwright(_restaurant())
        return slots, buf.getvalue(), cm

    def _run_check_expect_error(self, context_factory, env=None, error_type=RuntimeError):
        cm = FakePlaywrightCM(context_factory)
        buf = io.StringIO()
        env = env or {}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch("playwright.sync_api.sync_playwright", return_value=cm), \
                contextlib.redirect_stdout(buf):
            with self.assertRaises(error_type) as caught:
                monitor.check_slots_via_playwright(_restaurant())
        return caught.exception, buf.getvalue(), cm

    def test_ac1_428_then_200_retries_once_waiting_25s_between_gotos(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_challenge_428(15), _ok_200(day)])

        slots, stdout, cm = self._run_check(factory)
        ctx = cm.contexts[0]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].time, "19:50")
        gotos = [event for event in ctx.events if event[0] == "goto"]
        self.assertEqual(len(gotos), 2)
        self.assertEqual([event[1] for event in gotos], [_restaurant_url(), _restaurant_url()])
        wait_idxs = [
            i for i, event in enumerate(ctx.events)
            if event[0] == "wait_for_timeout" and event[1] == 25000
        ]
        goto_idxs = [i for i, event in enumerate(ctx.events) if event[0] == "goto"]
        self.assertEqual(len(wait_idxs), 1)
        self.assertTrue(goto_idxs[0] < wait_idxs[0] < goto_idxs[1])
        self.assertIn("keeping the page open 25s", stdout)

    def test_ac2_retries_disabled_raises_on_428_with_single_goto(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = _challenge_428(15)
            return ctx

        exc, stdout, cm = self._run_check_expect_error(
            factory, env={"DISNEY_AKAMAI_CHALLENGE_RETRIES": "0"}
        )
        ctx = cm.contexts[0]
        self.assertIsInstance(exc, RuntimeError)
        self.assertIn("HTTP 428 from availability API", str(exc))
        self.assertEqual(len([event for event in ctx.events if event[0] == "goto"]), 1)
        waits = [event[1] for event in ctx.events if event[0] == "wait_for_timeout"]
        self.assertNotIn(25000, waits)
        self.assertNotIn("keeping the page open", stdout)

    def test_ac3_persistent_428_retries_once_then_cooldown_skips_later_restaurant(self):
        def factory():
            ctx = FakeContext()
            ctx._evaluate_always = lambda script, arg: _challenge_428(15)
            return ctx

        cm = FakePlaywrightCM(factory)
        buf1 = io.StringIO()
        with mock.patch("playwright.sync_api.sync_playwright", return_value=cm), \
                contextlib.redirect_stdout(buf1):
            with self.assertRaises(RuntimeError) as first:
                monitor.check_slots_via_playwright(_restaurant())
        self.assertIn("HTTP 428 from availability API", str(first.exception))
        self.assertEqual(disney_bot._error_category(first.exception), "akamai")
        self.assertEqual(len(cm.contexts[0].gotos), 2)

        buf2 = io.StringIO()
        with mock.patch("playwright.sync_api.sync_playwright", return_value=cm), \
                contextlib.redirect_stdout(buf2):
            with self.assertRaises(RuntimeError) as second:
                monitor.check_slots_via_playwright(_restaurant(name="Space 220"))
        self.assertEqual(len(cm.contexts[1].gotos), 1)
        self.assertIn("skipping the retry", buf2.getvalue())
        self.assertIn("HTTP 428 from availability API", str(second.exception))

    def test_ac4_crashed_retry_goto_opens_fresh_tab_and_returns_slots(self):
        day = _tomorrow()

        def factory():
            ctx = FakeContext(evaluate_results=[_challenge_428(15), _ok_200(day)])
            ctx.pages[0].crash_on_goto_index = 2
            return ctx

        slots, stdout, cm = self._run_check(factory)
        ctx = cm.contexts[0]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].time, "19:50")
        self.assertEqual(ctx.new_page_calls, 1)
        original = ctx.pages[0]
        fresh = ctx.created_pages[0]
        self.assertEqual(len(original.goto_calls), 2)
        self.assertEqual(len(fresh.goto_calls), 1)
        self.assertEqual(fresh.goto_calls[0]["url"], _restaurant_url())
        self.assertIn("retrying in a fresh tab", stdout)
        goto_pages = [event[3] for event in ctx.events if event[0] == "goto"]
        self.assertIs(goto_pages[0], original)
        self.assertIs(goto_pages[1], original)
        self.assertIs(goto_pages[2], fresh)

    def test_ac5a_auth_required_on_first_load_propagates_without_akamai_retry(self):
        self.mock_token.side_effect = monitor.DisneyAuthRequired("Disney auth required: missing")

        def factory():
            return FakeContext()

        exc, stdout, cm = self._run_check_expect_error(
            factory, error_type=monitor.DisneyAuthRequired
        )
        ctx = cm.contexts[0]
        self.assertIsInstance(exc, monitor.DisneyAuthRequired)
        self.assertTrue(ctx.closed)
        self.assertEqual(len([event for event in ctx.events if event[0] == "goto"]), 1)
        self.assertEqual(len(ctx.evaluates), 0)
        self.assertNotIn("Akamai", stdout)

    def test_ac5b_token_is_read_once_and_reused_on_challenge_retry(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_challenge_428(15), _ok_200(day)])

        slots, stdout, cm = self._run_check(factory)
        self.assertEqual(len(slots), 1)
        self.assertEqual(self.mock_token.call_count, 1)
        tokens = [args["token"] for args in cm.contexts[0].evaluates]
        self.assertEqual(tokens, ["BEARER t", "BEARER t"])
        self.assertIn("keeping the page open 25s", stdout)

    def test_ac6_first_fetch_200_does_one_goto_and_only_warmup_wait(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_ok_200(day)])

        slots, stdout, cm = self._run_check(factory)
        ctx = cm.contexts[0]
        self.assertEqual(len(slots), 1)
        self.assertEqual(len([event for event in ctx.events if event[0] == "goto"]), 1)
        waits = [event[1] for event in ctx.events if event[0] == "wait_for_timeout"]
        self.assertEqual(waits, [8000])
        self.assertNotIn(25000, waits)
        self.assertNotIn("Akamai", stdout)

    def test_ac6_first_fetch_404_returns_empty_after_one_goto(self):
        def factory():
            return FakeContext(evaluate_results=[{"status": 404, "data": None, "body": ""}])

        slots, stdout, cm = self._run_check(factory)
        ctx = cm.contexts[0]
        self.assertEqual(slots, [])
        self.assertEqual(len([event for event in ctx.events if event[0] == "goto"]), 1)
        self.assertIn("no availability returned by Disney", stdout)

    def test_ac7_akamai_challenge_wait_ms_env_and_body_parsing(self):
        self.assertEqual(
            monitor._akamai_challenge_wait_ms({"body": '{"chlg_duration":15}'}),
            25000,
        )
        self.assertEqual(monitor._akamai_challenge_wait_ms({}), 25000)
        self.assertEqual(monitor._akamai_challenge_wait_ms({"body": "not-json"}), 25000)
        self.assertEqual(monitor._akamai_challenge_wait_ms({"body": "[1,2]"}), 25000)
        self.assertEqual(
            monitor._akamai_challenge_wait_ms({"body": '{"chlg_duration":500}'}),
            70000,
        )
        self.assertEqual(
            monitor._akamai_challenge_wait_ms({"body": '{"chlg_duration":1}'}),
            15000,
        )
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_WAIT_MS": "1000"}):
            self.assertEqual(
                monitor._akamai_challenge_wait_ms({"body": '{"chlg_duration":15}'}),
                1000,
            )
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_WAIT_MS": "abc"}):
            self.assertEqual(
                monitor._akamai_challenge_wait_ms({"body": '{"chlg_duration":15}'}),
                25000,
            )

    def test_ac8_akamai_challenge_retries_default_clamp_and_invalid(self):
        self.assertEqual(monitor._akamai_challenge_retries(), 1)
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_RETRIES": "0"}):
            self.assertEqual(monitor._akamai_challenge_retries(), 0)
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_RETRIES": "2"}):
            self.assertEqual(monitor._akamai_challenge_retries(), 2)
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_RETRIES": "9"}):
            self.assertEqual(monitor._akamai_challenge_retries(), 2)
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_RETRIES": "-3"}):
            self.assertEqual(monitor._akamai_challenge_retries(), 0)
        with mock.patch.dict(os.environ, {"DISNEY_AKAMAI_CHALLENGE_RETRIES": "abc"}):
            self.assertEqual(monitor._akamai_challenge_retries(), 1)

    def test_ac9_launch_still_passes_no_sandbox_and_headless_helper(self):
        day = _tomorrow()

        def factory():
            return FakeContext(evaluate_results=[_ok_200(day)])

        slots, stdout, cm = self._run_check(factory)
        self.assertEqual(len(slots), 1)
        kwargs = cm.contexts[0].launch_kwargs
        self.assertEqual(kwargs.get("args"), ["--no-sandbox"])
        self.assertEqual(kwargs.get("headless"), monitor._playwright_headless())

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
