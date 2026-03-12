#!/usr/bin/env python3
"""Walk onboarding funnels and capture screenshots + transcribed text per step."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


OUTPUT_BASE = Path.cwd() / "output" / "funnels"
STOP_AT_DEFAULT = "email_capture"
STEP_MARKER_RE = re.compile(r"\b(\d{1,3})\s+of\s+(\d{1,3})\b", re.IGNORECASE)
STEP_MARKER_SLASH_RE = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{1,3})(?!\d)")
SAFE_FORWARD_RE = re.compile(r"next|continue|get my plan|start|submit|confirm", re.IGNORECASE)
BLOCKED_LABEL_RE = re.compile(r"back|privacy|terms|contact|help|cookie", re.IGNORECASE)
DETOUR_OPTION_RE = re.compile(
    r"add photo|upload|camera|gallery|take photo|choose photo|detect .*photo|identify my dog'?s breed",
    re.IGNORECASE,
)
PROCESSING_RE = re.compile(
    r"connecting to database|analyzing|analysing|recalibrating|cross-checking|estimating optimal|"
    r"generating your action plan|processing your data|creating your personalized|creating personal program|"
    r"just a moment|loading",
    re.IGNORECASE,
)
STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "you",
    "your",
    "are",
    "was",
    "have",
    "from",
    "will",
    "not",
    "but",
    "all",
    "our",
    "can",
    "how",
    "what",
    "when",
    "why",
    "who",
    "where",
    "into",
    "more",
    "than",
    "they",
    "their",
    "them",
    "about",
    "only",
    "after",
    "before",
    "under",
    "over",
    "weight",
    "quiz",
    "step",
}


@dataclass
class StepRecord:
    step_number: int
    url: str
    step_marker: str
    step_index: int | None
    step_total: int | None
    title: str
    screenshot_path: str
    text_path: str
    dom_text_len: int
    ocr_used: bool
    action_taken: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze onboarding funnel screens.")
    parser.add_argument("--url", required=True, help="Funnel entry URL.")
    parser.add_argument("--name", default="", help="Run slug; default from URL + date.")
    parser.add_argument("--max-steps", type=int, default=80, help="Maximum captured steps.")
    parser.add_argument("--headless", default="true", choices=("true", "false"), help="Playwright headless mode.")
    parser.add_argument("--viewport", default="390x844", help="Viewport WIDTHxHEIGHT.")
    parser.add_argument("--stop-at", default=STOP_AT_DEFAULT, help="Current supported: email_capture.")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "run"


def default_run_name(url: str) -> str:
    host = urlparse(url).netloc or "funnel"
    today = datetime.now().strftime("%Y%m%d")
    return f"{slugify(host)}-{today}"


def parse_viewport(raw: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})", raw.strip())
    if not match:
        raise ValueError(f"Invalid --viewport '{raw}'. Expected WIDTHxHEIGHT.")
    return int(match.group(1)), int(match.group(2))


def ensure_dirs(run_name: str) -> tuple[Path, Path]:
    screens_dir = OUTPUT_BASE / "screens" / run_name
    texts_dir = OUTPUT_BASE / "texts" / run_name
    screens_dir.mkdir(parents=True, exist_ok=True)
    texts_dir.mkdir(parents=True, exist_ok=True)
    return screens_dir, texts_dir


def safe_inner_text(locator, timeout: int = 500) -> str:
    try:
        return (locator.inner_text(timeout=timeout) or "").strip()
    except Exception:
        return ""


def detect_step_marker(page: Page) -> tuple[str, int | None, int | None]:
    body_text = safe_inner_text(page.locator("body"))
    candidate_texts = [body_text]
    try:
        candidate_texts.append(extract_dom_text(page))
    except Exception:
        pass
    match = None
    for text in candidate_texts:
        match = STEP_MARKER_RE.search(text)
        if not match:
            match = STEP_MARKER_SLASH_RE.search(text)
        if match:
            break
    if not match:
        return "", None, None
    index = int(match.group(1))
    total = int(match.group(2))
    return f"{index} of {total}", index, total


def detect_title(page: Page) -> str:
    script = """
() => {
  const root = document.querySelector('main') || document.body;
  const isVisible = (node) => {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    return rect.width > 10 && rect.height > 10;
  };
  const nodes = Array.from(root.querySelectorAll('h1, h2, h3, p, div, span, label, button'));
  const cleaned = nodes
    .filter((node) => isVisible(node))
    .map((node) => (node.innerText || '').trim())
    .map((text) => text.replace(/\\s+/g, ' '))
    .filter((text) => text.length > 5)
    .filter((text) => !/^back$/i.test(text))
    .filter((text) => !/^\\d+\\s+of\\s+\\d+$/i.test(text))
    .filter((text) => !/^\\d+\\s*\\/\\s*\\d+$/i.test(text))
    .filter((text) => !/^©/i.test(text))
    .filter((text) => !/disclaimer/i.test(text))
    .filter((text) => !/all rights reserved/i.test(text));
  const ignored = /terms of use|privacy policy|need help|skip/i;
  const informative = cleaned.filter((text) => !/^luvly$/i.test(text));
  const relevant = informative.filter((text) => !ignored.test(text));
  const question = relevant.find((text) => /\\?$/.test(text));
  if (question) return question;
  const longLine = relevant.find((text) => text.length >= 20 && text.length <= 180);
  if (longLine) return longLine;
  const shortPrompt = relevant.find((text) => text.length >= 8);
  if (shortPrompt) return shortPrompt;
  return '';
}
"""
    try:
        detected = (page.evaluate(script) or "").strip()
        if detected:
            return detected
    except Exception:
        pass
    return page.title()


def extract_dom_text(page: Page) -> str:
    script = """
() => {
  const root = document.querySelector('main') || document.body;
  const nodes = root.querySelectorAll('h1,h2,h3,p,button,label,li,span,div');
  const lines = [];
  for (const node of nodes) {
    const style = window.getComputedStyle(node);
    if (style && (style.display === 'none' || style.visibility === 'hidden')) continue;
    const text = (node.innerText || '').trim();
    if (!text) continue;
    if (text.length > 500) continue;
    lines.push(text.replace(/\\s+/g, ' '));
  }
  const dedup = [];
  const seen = new Set();
  for (const line of lines) {
    if (!seen.has(line)) {
      seen.add(line);
      dedup.push(line);
    }
  }
  return dedup.join('\\n');
}
"""
    try:
        text = page.evaluate(script) or ""
    except Exception:
        text = safe_inner_text(page.locator("body"))
    return text.strip()


def wait_for_meaningful_screen(page: Page, timeout_ms: int = 6000) -> bool:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        try:
            ready = page.evaluate(
                """
() => {
  const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
  if (bodyText.length >= 40) return true;

  const candidates = Array.from(
    document.querySelectorAll("button, label, a, [role='button'], [role='radio'], [role='option'], input")
  );
  const visibleCount = candidates.filter((el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    return rect.width > 30 && rect.height > 18;
  }).length;
  return visibleCount > 0;
}
"""
            )
            if ready:
                return True
        except Exception:
            pass
        page.wait_for_timeout(250)
    return False


def read_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read()


def ocr_image_with_openai(image_path: Path, client: Any) -> str:
    image_bytes = read_bytes(image_path)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{encoded}"
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Transcribe all visible text from this screen exactly. Return plain text only.",
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                    },
                ],
            }
        ],
    )
    text = getattr(response, "output_text", "") or ""
    return text.strip()


def merge_text(dom_text: str, ocr_text: str) -> str:
    if not dom_text and not ocr_text:
        return ""
    if not dom_text:
        return ocr_text
    if not ocr_text:
        return dom_text
    merged = [dom_text]
    for line in ocr_text.splitlines():
        stripped = line.strip()
        if stripped and stripped.lower() not in dom_text.lower():
            merged.append(stripped)
    return "\n".join(merged).strip()


def looks_like_processing_screen(text: str, marker: str, title: str = "") -> bool:
    lowered = text.lower()
    title_lower = title.lower().strip()

    # Prefer explicit loader titles to avoid false positives from hidden/stale DOM text.
    title_keywords = (
        "all set! just a moment",
        "creating your communication plan",
        "creating your personalized",
        "creating personal program",
        "processing your data",
    )
    if any(keyword in title_lower for keyword in title_keywords):
        return True
    if "?" in title_lower:
        return False
    if PROCESSING_RE.search(lowered):
        return True
    if marker:
        return False

    return False


def wait_for_screen_change(
    page: Page,
    initial_signature: str,
    timeout_ms: int = 12000,
    poll_ms: int = 400,
) -> bool:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        page.wait_for_timeout(poll_ms)
        current_signature = f"{page.url}|{detect_step_marker(page)[0]}|{detect_title(page)}|{extract_dom_text(page)[:180]}"
        if current_signature != initial_signature:
            return True
    return False


def looks_like_email_capture(page: Page) -> bool:
    try:
        if "email" in (urlparse(page.url).path or "").lower():
            return True
    except Exception:
        pass
    selectors = [
        "input[type='email']",
        "input[type='text']",
        "input[name*='email' i]",
        "input[placeholder*='email' i]",
        "input[aria-label*='email' i]",
    ]
    has_input = False
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                has_input = True
                if selector != "input[type='text']":
                    return True
        except Exception:
            continue
    if not has_input:
        return False
    body_text = safe_inner_text(page.locator("body")).lower()
    email_keywords = (
        "enter your email",
        "your email",
        "get my plan",
        "email",
    )
    return any(keyword in body_text for keyword in email_keywords)


def click_if_visible(page: Page, selector: str) -> bool:
    try:
        locator = page.locator(selector).first
        if locator.count() == 0:
            return False
        locator.click(timeout=1200)
        return True
    except Exception:
        return False


def dismiss_consent_overlays(page: Page) -> bool:
    clicked = False

    # Common cookie/consent manager selectors (OneTrust and generic CMPs).
    selector_candidates = [
        "#accept-recommended-btn-handler",
        "#onetrust-accept-btn-handler",
        "#onetrust-reject-all-handler",
        ".ot-pc-refuse-all-handler",
        ".save-preference-btn-handler",
        "[aria-label*='cookie' i] button",
        "[id*='cookie' i] button",
        "[class*='cookie' i] button",
        "[id*='consent' i] button",
        "[class*='consent' i] button",
        ".onetrust-close-btn-handler",
        "#close-pc-btn-handler",
    ]
    for _ in range(3):
        for selector in selector_candidates:
            try:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                if locator.is_visible():
                    locator.click(timeout=1000, force=True)
                    clicked = True
                    page.wait_for_timeout(250)
            except Exception:
                continue

        # Text-based fallback for CMP buttons.
        text_patterns = [
            "allow all",
            "accept all",
            "accept",
            "agree",
            "i agree",
            "confirm my choices",
            "save preferences",
            "reject all",
            "got it",
            "close",
        ]
        buttons = page.locator("button, a")
        try:
            count = buttons.count()
        except Exception:
            count = 0
        for idx in range(min(count, 50)):
            control = buttons.nth(idx)
            text = safe_inner_text(control).lower()
            if not text:
                continue
            if not any(pattern in text for pattern in text_patterns):
                continue
            try:
                if control.is_visible() and control.is_enabled():
                    control.click(timeout=900, force=True)
                    clicked = True
                    page.wait_for_timeout(200)
            except Exception:
                continue

        # JS fallback for stubborn OneTrust overlays.
        try:
            did_click = page.evaluate(
                """
() => {
  const candidates = [
    '#accept-recommended-btn-handler',
    '#onetrust-accept-btn-handler',
    '.ot-pc-refuse-all-handler',
    '.save-preference-btn-handler',
    '.onetrust-close-btn-handler',
    '#close-pc-btn-handler'
  ];
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el && el instanceof HTMLElement) {
      const style = window.getComputedStyle(el);
      if (style.display !== 'none' && style.visibility !== 'hidden') {
        el.click();
        return true;
      }
    }
  }
  return false;
}
"""
            )
            if did_click:
                clicked = True
                page.wait_for_timeout(250)
        except Exception:
            pass

        try:
            banner_visible = (
                page.locator("#onetrust-banner-sdk:visible, .onetrust-pc-dark-filter:visible").count() > 0
            )
        except Exception:
            banner_visible = False
        if not banner_visible:
            break

    return clicked


def maybe_click_start_cta(page: Page) -> bool:
    start_words = [
        "female",
        "male",
        "start",
        "begin",
        "get started",
    ]
    buttons = page.locator("button")
    try:
        count = buttons.count()
    except Exception:
        count = 0
    for idx in range(min(count, 12)):
        text = safe_inner_text(buttons.nth(idx)).lower()
        if not text:
            continue
        if any(word in text for word in start_words):
            try:
                buttons.nth(idx).click(timeout=1500)
                return True
            except Exception:
                continue
    return False


def fill_numeric_fields(page: Page, warnings: list[str]) -> bool:
    action_taken = False
    current_weight = 180

    def fill_spinbutton(name_re: str, value: str) -> bool:
        locator = page.locator(f"input[aria-label*='{name_re}' i], input[name*='{name_re}' i]")
        try:
            if locator.count() > 0:
                locator.first.fill(value)
                return True
        except Exception:
            return False
        return False

    feet = fill_spinbutton("feet", "5")
    inches = fill_spinbutton("inch", "6")
    if feet or inches:
        action_taken = True

    if fill_spinbutton("current weight", str(current_weight)):
        action_taken = True

    if fill_spinbutton("goal weight", "150") or fill_spinbutton("target weight", "150"):
        action_taken = True

    numeric_inputs = page.locator("input[type='number'], input[inputmode='numeric']")
    try:
        count = numeric_inputs.count()
    except Exception:
        count = 0
    for idx in range(count):
        field = numeric_inputs.nth(idx)
        attrs = " ".join(
            [
                field.get_attribute("aria-label") or "",
                field.get_attribute("name") or "",
                field.get_attribute("id") or "",
                field.get_attribute("placeholder") or "",
            ]
        ).lower()
        value = "30"
        if "feet" in attrs:
            value = "5"
        elif "inch" in attrs:
            value = "6"
        elif "current" in attrs and "weight" in attrs:
            value = str(current_weight)
        elif "weight" in attrs and "goal" not in attrs and "target" not in attrs:
            value = str(current_weight)
        elif "goal" in attrs or "target" in attrs:
            value = "150"
        try:
            field.fill(value)
            action_taken = True
        except Exception as exc:
            warnings.append(f"Failed numeric fill: {exc}")

    if action_taken:
        page.wait_for_timeout(250)
    return action_taken


def fill_searchable_choice_fields(page: Page, warnings: list[str]) -> bool:
    text_inputs = page.locator(
        "input[type='text']:not([type='email']), input:not([type])[name], input[placeholder]"
    )
    try:
        count = text_inputs.count()
    except Exception:
        count = 0

    for idx in range(count):
        field = text_inputs.nth(idx)
        try:
            attrs = " ".join(
                [
                    field.get_attribute("name") or "",
                    field.get_attribute("placeholder") or "",
                    field.get_attribute("aria-label") or "",
                ]
            ).lower()
        except Exception:
            attrs = ""
        if not any(token in attrs for token in ("breed", "choose", "search", "select")):
            continue

        radio_options = page.locator("input[type='radio'][value]")
        try:
            radio_count = radio_options.count()
        except Exception:
            radio_count = 0
        if radio_count == 0:
            continue

        selected_value = ""
        for radio_idx in range(radio_count):
            candidate = radio_options.nth(radio_idx)
            try:
                candidate_value = (candidate.get_attribute("value") or "").strip()
            except Exception:
                candidate_value = ""
            if not candidate_value or DETOUR_OPTION_RE.search(candidate_value.lower()):
                continue
            selected_value = candidate_value
            break
        if not selected_value:
            continue

        try:
            field.fill(selected_value)
            page.wait_for_timeout(300)
        except Exception as exc:
            warnings.append(f"Failed searchable fill: {exc}")
            continue

        suggestion_clicked = False
        option_button = page.get_by_role("button", name=selected_value)
        try:
            if option_button.count() > 0 and option_button.first.is_visible():
                option_button.first.click(timeout=1200)
                suggestion_clicked = True
        except Exception:
            suggestion_clicked = False

        if not suggestion_clicked:
            try:
                field.press("ArrowDown")
                field.press("Enter")
                suggestion_clicked = True
            except Exception:
                pass

        page.wait_for_timeout(250)
        return True

    return False


def click_first_option(page: Page) -> bool:
    def collect_clickable(locator) -> list[tuple[int, Any]]:
        primary: list[tuple[int, Any]] = []
        detours: list[tuple[int, Any]] = []
        try:
            count = locator.count()
        except Exception:
            count = 0
        for idx in range(count):
            option = locator.nth(idx)
            text = safe_inner_text(option).strip()
            lowered = text.lower()
            if not lowered or BLOCKED_LABEL_RE.search(lowered):
                continue
            if DETOUR_OPTION_RE.search(lowered):
                detours.append((idx, option))
            else:
                primary.append((idx, option))
        return primary + detours

    data_test_options = page.locator("[data-testid='option']")
    for _, option in collect_clickable(data_test_options):
        try:
            if option.is_visible():
                option.click(timeout=1200)
                return True
        except Exception:
            continue

    labels = page.locator("label")
    for _, label in collect_clickable(labels):
        try:
            label.click(timeout=1200)
            return True
        except Exception:
            continue

    role_options = page.locator("[role='radio'], [role='option']")
    for _, option in collect_clickable(role_options):
        try:
            option.click(timeout=1200)
            return True
        except Exception:
            continue

    radios = page.locator("input[type='radio'], input[type='checkbox']")
    try:
        count = radios.count()
    except Exception:
        count = 0
    for idx in range(count):
        field = radios.nth(idx)
        try:
            label = " ".join(
                filter(
                    None,
                    [
                        field.get_attribute("value") or "",
                        field.get_attribute("aria-label") or "",
                        field.get_attribute("name") or "",
                    ],
                )
            ).strip()
        except Exception:
            label = ""
        if label and DETOUR_OPTION_RE.search(label.lower()):
            continue
        try:
            field.check(timeout=1200, force=True)
            return True
        except Exception:
            try:
                field.click(timeout=1200, force=True)
                return True
            except Exception:
                continue

    # Many funnels (e.g. Speechify) render answer cards as regular <button> elements.
    # Treat non-forward, non-navigation buttons as answer options.
    buttons = page.locator("button")
    for _, button in collect_clickable(buttons):
        text = safe_inner_text(button).strip()
        lowered = text.lower()
        if SAFE_FORWARD_RE.search(lowered):
            continue
        try:
            testid = (button.get_attribute("data-testid") or "").lower()
        except Exception:
            testid = ""
        # Skip obvious non-answer utility buttons.
        if any(token in testid for token in ("close", "dismiss", "cookie", "help", "support")):
            continue
        try:
            if button.is_enabled():
                button.click(timeout=1200)
                return True
        except Exception:
            continue
    return False


def click_image_option(page: Page) -> bool:
    script = """
() => {
  const isVisible = (node) => {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    return rect.width >= 20 && rect.height >= 20;
  };
  const images = Array.from(document.querySelectorAll('main img, img'));
  const scored = images
    .map((img, index) => {
      const rect = img.getBoundingClientRect();
      const style = window.getComputedStyle(img);
      const src = (img.getAttribute('src') || '').toLowerCase();
      const alt = (img.getAttribute('alt') || '').trim().toLowerCase();
      const score =
        (style.cursor === 'pointer' ? 4 : 0) +
        (rect.y > 140 && rect.y < window.innerHeight - 120 ? 3 : 0) +
        (rect.width <= 120 && rect.height <= 140 ? 2 : 0) +
        (alt ? 1 : 0);
      return {
        index,
        src,
        alt,
        score,
        x: rect.x,
        y: rect.y,
        visible: isVisible(img),
      };
    })
    .filter((item) => item.visible)
    .filter((item) => !item.src.includes('bat.bing.com'))
    .filter((item) => !item.src.includes('site-assets.plasmic.app'))
    .filter((item) => !item.src.startsWith('data:image/svg+xml'))
    .filter((item) => item.y > 120 && item.y < window.innerHeight - 120)
    .sort((a, b) => b.score - a.score || a.y - b.y || a.x - b.x);
  return scored.length ? scored[0].index : -1;
}
"""
    try:
        target_index = page.evaluate(script)
    except Exception:
        return False
    if target_index is None or target_index < 0:
        return False
    locator = page.locator("main img, img").nth(target_index)
    try:
        if locator.is_visible():
            locator.click(timeout=1200)
            return True
    except Exception:
        return False
    return False


def click_safe_forward_button(page: Page) -> bool:
    buttons = page.locator("button")
    try:
        count = buttons.count()
    except Exception:
        count = 0
    for idx in range(count):
        button = buttons.nth(idx)
        text = safe_inner_text(button)
        if not text:
            continue
        lowered = text.lower()
        if BLOCKED_LABEL_RE.search(lowered):
            continue
        if SAFE_FORWARD_RE.search(lowered):
            try:
                if button.is_enabled():
                    button.click(timeout=1500)
                    return True
            except Exception:
                continue
    return False


def write_step_markdown(
    step_path: Path,
    url: str,
    step_number: int,
    step_marker: str,
    title: str,
    dom_text: str,
    ocr_text: str,
    merged_text: str,
) -> None:
    content = [
        f"# Step {step_number:03d}",
        "",
        f"- URL: {url}",
        f"- Step marker: {step_marker or 'N/A'}",
        f"- Title: {title or 'N/A'}",
        "",
        "## DOM text",
        dom_text or "(empty)",
        "",
        "## OCR text",
        ocr_text or "(not used or empty)",
        "",
        "## Merged text",
        merged_text or "(empty)",
        "",
    ]
    step_path.write_text("\n".join(content), encoding="utf-8")


def extract_top_themes(texts: list[str], limit: int = 8) -> list[str]:
    words: Counter[str] = Counter()
    for text in texts:
        for token in re.findall(r"[A-Za-z]{4,}", text.lower()):
            if token in STOPWORDS:
                continue
            words[token] += 1
    return [word for word, _ in words.most_common(limit)]


def extract_cta_progression(texts: list[str]) -> list[str]:
    ctas = []
    patterns = [r"\bnext\b", r"\bcontinue\b", r"\bget my plan\b", r"\bstart\b", r"\bconfirm\b"]
    for idx, text in enumerate(texts, start=1):
        lowered = text.lower()
        found = [pat.strip("\\b") for pat in patterns if re.search(pat, lowered)]
        if found:
            ctas.append(f"Step {idx:03d}: {', '.join(found)}")
    return ctas


def write_summary(
    path: Path,
    url: str,
    steps: list[StepRecord],
    stop_reason: str,
) -> None:
    merged_texts = []
    for step in steps:
        text_file = Path(step.text_path)
        try:
            merged_texts.append(text_file.read_text(encoding="utf-8"))
        except Exception:
            continue
    themes = extract_top_themes(merged_texts)
    ctas = extract_cta_progression(merged_texts)
    lines = [
        "# Funnel Summary",
        "",
        "## Overview",
        f"- Entry URL: {url}",
        f"- Captured screens: {len(steps)}",
        f"- Stop reason: {stop_reason}",
        "",
        "## Step-by-step flow",
        "| Step | Marker | Title | URL |",
        "|---|---|---|---|",
    ]
    for step in steps:
        lines.append(
            f"| {step.step_number:03d} | {step.step_marker or 'N/A'} | {step.title.replace('|', '/')} | {step.url} |"
        )
    lines.extend(
        [
            "",
            "## Key messaging themes and psychological hooks",
            f"- Frequent themes: {', '.join(themes) if themes else 'N/A'}",
            "- Typical hooks: identity change, ease/simplicity, confidence, and personalized outcomes.",
            "",
            "## CTA progression notes",
        ]
    )
    if ctas:
        lines.extend([f"- {item}" for item in ctas])
    else:
        lines.append("- CTA text not clearly detected in captured text.")
    lines.extend(
        [
            "",
            "## Email-writing implications",
            "- Subject angles: quick transformation, confidence gains, reduced effort, and personalized plan.",
            "- Body themes: pain points first, social proof, simple next step, and non-judgmental tone.",
            "- Objections to handle: skepticism, effort/time concerns, and fear of unsustainable results.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.stop_at != STOP_AT_DEFAULT:
        print(f"[WARN] Unsupported --stop-at '{args.stop_at}', using '{STOP_AT_DEFAULT}'.")
    run_name = slugify(args.name) if args.name else default_run_name(args.url)
    width, height = parse_viewport(args.viewport)
    screens_dir, texts_dir = ensure_dirs(run_name)
    manifest_path = texts_dir / "manifest.json"
    summary_path = texts_dir / "summary.md"
    warnings: list[str] = []
    steps: list[StepRecord] = []
    stop_reason = "max_steps_reached"
    started_at = utc_now()

    ocr_client = None
    if OpenAI is not None and os.getenv("OPENAI_API_KEY"):
        try:
            ocr_client = OpenAI()
        except Exception as exc:
            warnings.append(f"OCR disabled: OpenAI client init failed: {exc}")
    else:
        warnings.append("OCR disabled: OPENAI_API_KEY missing or openai package unavailable.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=(args.headless == "true"))
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
        dismiss_consent_overlays(page)
        maybe_click_start_cta(page)
        wait_for_meaningful_screen(page, timeout_ms=8000)
        page.wait_for_timeout(1200)

        stalled = 0
        previous_signature = ""
        for step_number in range(1, args.max_steps + 1):
            wait_for_meaningful_screen(page, timeout_ms=4000)
            page.wait_for_timeout(600)
            dismiss_consent_overlays(page)
            marker, marker_idx, marker_total = detect_step_marker(page)
            title = detect_title(page)
            signature = f"{page.url}|{marker}|{title}"
            if signature == previous_signature:
                stalled += 1
            else:
                stalled = 0

            # Recovery path: if the screen signature is unchanged, try a forward action
            # before creating another duplicate capture entry for the same screen.
            if signature == previous_signature and stalled > 0:
                if click_safe_forward_button(page) or click_if_visible(page, "[type='submit']"):
                    page.wait_for_timeout(800)
                    continue
                processing_signature = (
                    f"{page.url}|{detect_step_marker(page)[0]}|{detect_title(page)}|{extract_dom_text(page)[:180]}"
                )
                if looks_like_processing_screen(extract_dom_text(page), marker, detect_title(page)):
                    if wait_for_screen_change(page, processing_signature, timeout_ms=12000):
                        continue
                    page.wait_for_timeout(1500)
                    continue

            previous_signature = signature
            if stalled >= 3:
                stop_reason = "stalled_same_screen"
                break

            screenshot_path = screens_dir / f"step-{step_number:03d}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)

            dom_text = extract_dom_text(page)
            ocr_text = ""
            ocr_used = False
            if len(dom_text) < 80 and ocr_client is not None:
                try:
                    ocr_text = ocr_image_with_openai(screenshot_path, ocr_client)
                    ocr_used = True
                except Exception as exc:
                    warnings.append(f"OCR failed on step {step_number:03d}: {exc}")
            merged_text = merge_text(dom_text, ocr_text)
            text_path = texts_dir / f"step-{step_number:03d}.md"
            write_step_markdown(
                step_path=text_path,
                url=page.url,
                step_number=step_number,
                step_marker=marker,
                title=title,
                dom_text=dom_text,
                ocr_text=ocr_text,
                merged_text=merged_text,
            )

            record = StepRecord(
                step_number=step_number,
                url=page.url,
                step_marker=marker,
                step_index=marker_idx,
                step_total=marker_total,
                title=title,
                screenshot_path=str(screenshot_path),
                text_path=str(text_path),
                dom_text_len=len(dom_text),
                ocr_used=ocr_used,
                action_taken="none",
            )

            if looks_like_email_capture(page):
                record.action_taken = "stop_email_capture"
                steps.append(record)
                stop_reason = "email_capture_reached"
                break

            if looks_like_processing_screen(merged_text, marker, title):
                record.action_taken = "wait_processing"
                steps.append(record)
                processing_signature = f"{page.url}|{marker}|{title}|{merged_text[:180]}"
                wait_for_screen_change(page, processing_signature, timeout_ms=20000)
                continue

            action = "none"
            before_action_signature = f"{page.url}|{marker}|{title}"
            handled_searchable = fill_searchable_choice_fields(page, warnings)
            if handled_searchable:
                if click_safe_forward_button(page):
                    action = "fill_searchable_then_forward"
                else:
                    action = "fill_searchable_only"
            elif click_first_option(page):
                page.wait_for_timeout(350)
                after_marker, _, _ = detect_step_marker(page)
                after_title = detect_title(page)
                after_select_signature = f"{page.url}|{after_marker}|{after_title}"
                if after_select_signature != before_action_signature:
                    action = "click_first_option"
                elif click_safe_forward_button(page):
                    action = "click_first_option_then_forward"
                else:
                    action = "click_first_option"
            elif click_image_option(page):
                page.wait_for_timeout(350)
                if click_safe_forward_button(page):
                    action = "click_image_option_then_forward"
                else:
                    action = "click_image_option"
            else:
                had_numeric = fill_numeric_fields(page, warnings)
                clicked_forward = click_safe_forward_button(page)
                if had_numeric and clicked_forward:
                    action = "fill_numeric_then_forward"
                elif clicked_forward:
                    action = "click_forward_button"
                elif had_numeric:
                    action = "filled_numeric_only"
                elif click_if_visible(page, "[type='submit']"):
                    action = "click_submit_fallback"

            record.action_taken = action
            steps.append(record)

            if action == "none":
                stop_reason = "no_actionable_control"
                break

            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except PlaywrightTimeoutError:
                warnings.append(f"Step {step_number:03d}: domcontentloaded timeout after action '{action}'.")

        context.close()
        browser.close()

    ended_at = utc_now()
    manifest = {
        "run_name": run_name,
        "url": args.url,
        "started_at": started_at,
        "ended_at": ended_at,
        "stop_reason": stop_reason,
        "total_steps": len(steps),
        "settings": {
            "max_steps": args.max_steps,
            "headless": args.headless == "true",
            "viewport": {"width": width, "height": height},
            "stop_at": STOP_AT_DEFAULT,
        },
        "steps": [asdict(step) for step in steps],
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_summary(summary_path, args.url, steps, stop_reason)
    print(f"[OK] Run complete: {run_name}")
    print(f"[OK] Screens: {screens_dir}")
    print(f"[OK] Texts: {texts_dir}")
    print(f"[OK] Manifest: {manifest_path}")
    print(f"[OK] Summary: {summary_path}")
    print(f"[OK] Stop reason: {stop_reason}")
    if warnings:
        print(f"[WARN] {len(warnings)} warning(s) recorded.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("[ERROR] Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        traceback.print_exc()
        time.sleep(0.1)
        sys.exit(1)
