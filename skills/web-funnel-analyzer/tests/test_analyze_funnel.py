import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "analyze_funnel.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_funnel", MODULE_PATH)
analyze_funnel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = analyze_funnel
SPEC.loader.exec_module(analyze_funnel)


class FakeLocator:
    def __init__(self, text="", count=1):
        self._text = text
        self._count = count

    def inner_text(self, timeout=500):
        return self._text

    def count(self):
        return self._count


class FakePage:
    def __init__(
        self,
        body_text="",
        eval_results=None,
        url="https://example.test",
        page_title="Example",
        locators=None,
    ):
        self.body_text = body_text
        self.eval_results = list(eval_results or [])
        self.url = url
        self.waits = []
        self.page_title = page_title
        self.locators = locators or {}

    def locator(self, selector):
        if selector in self.locators:
            return self.locators[selector]
        if selector == "body":
            return FakeLocator(self.body_text)
        raise AssertionError(f"Unexpected selector: {selector}")

    def evaluate(self, script):
        if not self.eval_results:
            raise AssertionError("No evaluate result queued")
        return self.eval_results.pop(0)

    def title(self):
        return self.page_title

    def wait_for_timeout(self, value):
        self.waits.append(value)


class AnalyzeFunnelTests(unittest.TestCase):
    def test_detect_step_marker_supports_of_format(self):
        page = FakePage(body_text="Question text 3 of 40 more text")
        marker, index, total = analyze_funnel.detect_step_marker(page)
        self.assertEqual(("3 of 40", 3, 40), (marker, index, total))

    def test_detect_step_marker_supports_slash_format(self):
        page = FakePage(body_text="Question text 3 /40 more text")
        marker, index, total = analyze_funnel.detect_step_marker(page)
        self.assertEqual(("3 of 40", 3, 40), (marker, index, total))

    def test_detect_title_filters_brand_only_title(self):
        page = FakePage(
            eval_results=[""],
            page_title="How many glasses of water do you drink per day?",
        )
        title = analyze_funnel.detect_title(page)
        self.assertEqual("How many glasses of water do you drink per day?", title)

    def test_looks_like_processing_screen_detects_loader_copy(self):
        text = "Connecting to database 83% Generating Your Action Plan"
        self.assertTrue(analyze_funnel.looks_like_processing_screen(text, "", "Luvly"))

    def test_looks_like_processing_screen_yields_to_question_title(self):
        text = "Recalibrating your skin care program... Do you wear make-up on a daily basis? Yes No"
        self.assertFalse(
            analyze_funnel.looks_like_processing_screen(
                text,
                "12 of 27",
                "Do you wear make-up on a daily basis?",
            )
        )

    def test_wait_for_screen_change_returns_true_on_signature_change(self):
        page = FakePage(
            body_text="same",
            eval_results=[
                "First title",
                "First title",
                "Second title",
            ],
        )
        original_extract_dom_text = analyze_funnel.extract_dom_text
        original_detect_step_marker = analyze_funnel.detect_step_marker
        states = iter(["same body", "same body", "next body"])
        analyze_funnel.extract_dom_text = lambda _: next(states)
        analyze_funnel.detect_step_marker = lambda _: ("", None, None)
        try:
            changed = analyze_funnel.wait_for_screen_change(
                page,
                "https://example.test||First title|same body",
                timeout_ms=1200,
                poll_ms=10,
            )
        finally:
            analyze_funnel.extract_dom_text = original_extract_dom_text
            analyze_funnel.detect_step_marker = original_detect_step_marker
        self.assertTrue(changed)

    def test_click_image_option_uses_ranked_image_candidate(self):
        class ClickLocator:
            def __init__(self):
                self.clicked = False

            def is_visible(self):
                return True

            def click(self, timeout=1200):
                self.clicked = True

        class ImageLocatorGroup:
            def __init__(self):
                self.target = ClickLocator()

            def nth(self, index):
                self.last_index = index
                return self.target

        group = ImageLocatorGroup()

        class ImagePage(FakePage):
            def locator(self, selector):
                if selector == "main img, img":
                    return group
                return super().locator(selector)

        page = ImagePage(eval_results=[2])
        clicked = analyze_funnel.click_image_option(page)
        self.assertTrue(clicked)
        self.assertEqual(2, group.last_index)
        self.assertTrue(group.target.clicked)

    def test_looks_like_email_capture_accepts_text_input_with_email_copy(self):
        page = FakePage(
            body_text="Enter your email to get started Get my Plan",
            locators={
                "input[type='email']": FakeLocator(count=0),
                "input[type='text']": FakeLocator(count=1),
                "input[name*='email' i]": FakeLocator(count=0),
                "input[placeholder*='email' i]": FakeLocator(count=0),
                "input[aria-label*='email' i]": FakeLocator(count=0),
            },
        )
        self.assertTrue(analyze_funnel.looks_like_email_capture(page))

    def test_looks_like_email_capture_accepts_email_url(self):
        page = FakePage(url="https://example.test/email-aref")
        self.assertTrue(analyze_funnel.looks_like_email_capture(page))


if __name__ == "__main__":
    unittest.main()
