#!/usr/bin/env python3

import asyncio
import json
from collections import OrderedDict
from playwright.async_api import async_playwright, Page, ElementHandle
from datetime import datetime, timezone, timedelta

URL = "https://www.publix.com/savings/weekly-ad/bogo"

CARD_SELECTOR = '[data-qa="savings-weekly-card"]'
HEADING_SELECTOR = 'h2[id$="-heading"]'
TITLE_SELECTOR = '[data-qa-automation="prod-title"]'
SAVINGS_SELECTOR = "span.additional-info"
OFFER_SELECTOR = ".p-savings-badge__text span"


async def get_category_for_card(page: Page, card: ElementHandle) -> str | None:
    """
    Get the category heading for a given card element

    Args:
        page (Page): Playwright page object
        card (ElementHandle): The card element to find the category for

    Returns:
        str | None: The category heading text if found, otherwise None
    """

    return await page.evaluate(
        """([card, selector]) => {
            const cardY = card.getBoundingClientRect().top + window.scrollY;

            const headings = Array.from(
                document.querySelectorAll(selector)
            );

            let category = null;

            for (const h of headings) {
                const y = h.getBoundingClientRect().top + window.scrollY;
                if (y <= cardY) {
                    category = h.innerText.trim();
                } else {
                    break;
                }
            }

            return category;
        }""",
        [card, HEADING_SELECTOR],
    )


async def get_card_metrics(page: Page) -> dict:
    """
    Get metrics about the card elements on the page

    Args:
        page (Page): Playwright page object

    Returns:
        dict: Dictionary containing cardHeight and firstCardY
    """
    await page.wait_for_selector(CARD_SELECTOR)

    return await page.evaluate(
        """(selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;

            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            const cardHeight =
                rect.height +
                parseFloat(style.marginTop) +
                parseFloat(style.marginBottom);

            const firstCardY = rect.top + window.scrollY;

            return {
                cardHeight,
                firstCardY
            };
        }""",
        CARD_SELECTOR,
    )


async def is_element_visible(element: ElementHandle) -> bool:
    """
    Check if an element is visible in the viewport

    Args:
        element (ElementHandle): The element to check visibility for

    Returns:
        bool: True if the element is visible, False otherwise
    """
    return await element.evaluate("""(el) => {
            const rect = el.getBoundingClientRect();
            return (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );
        }""")


async def extract_text(card: ElementHandle, selector: str) -> str | None:
    """
    Extract and clean text from a card element based on the provided selector

    Args:
        card (ElementHandle): The card element to extract text from
        selector (str): The CSS selector to locate the text element within the card

    Returns:
        str | None: The cleaned text if found, otherwise None
    """
    extract_text = await card.query_selector(selector)
    if extract_text:
        return (await extract_text.inner_text()).strip()
    return None


def add_new_deals(master_list: list, new_deals: list):
    """
    Add new deals to the master list, avoiding duplicates based on title
    Args:
        master_list (list): Existing list of deals
        new_deals (list): New deals to add
    """

    existing_titles = {deal["title"] for deal in master_list}
    for deal in new_deals:
        if deal["title"] not in existing_titles:
            master_list.append(deal)


def group_deals_by_category(deals: list[dict]) -> list[dict]:
    """
    Group deals by their category

    Args:
        deals (list): List of deal dictionaries

    Returns:
        list: List of categories with their associated deals
    """
    grouped = OrderedDict()

    for deal in deals:
        category = deal.get("category") or "Uncategorized"

        if category not in grouped:
            grouped[category] = []

        item = {
            "title": deal["title"],
            "savings": deal["savings"],
            "offer": deal["offer"],
        }

        grouped[category].append(item)

    deals = [
        {
            "category": category,
            "items": items,
        }
        for category, items in grouped.items()
    ]
    utc_now = datetime.now(timezone.utc).isoformat()
    return {"timestamp": utc_now, "deals": deals}


async def scrape_publix(page: Page, pause: float = 0.0) -> list:
    """
    Scrape all deals from the Publix weekly ad page by scrolling through the content

    Args:
        page (Page): Playwright page object
        pause (float): Pause duration between scrolls

    Returns:
        list: List of deal dictionaries
    """
    last_scroll_y = -1
    deals = []

    metrics = await get_card_metrics(page)

    card_height = metrics["cardHeight"]
    first_card_y = metrics["firstCardY"]

    if not card_height:
        raise RuntimeError("Could not determine card height")

    await page.evaluate("(y) => window.scrollTo(0, y)", first_card_y)
    last_scroll_y = -1

    clean_deals = []

    while True:
        scroll_y = await page.evaluate("() => window.scrollY")

        # Stop if scrolling no longer advances
        if scroll_y == last_scroll_y:
            print("No further scroll possible")
            break

        deals = await scrape_viewport(page)
        add_new_deals(clean_deals, deals)

        # Scroll exactly one card down
        await page.evaluate("(y) => window.scrollTo(0, y)", scroll_y + card_height)

        last_scroll_y = scroll_y
        await asyncio.sleep(pause)

    return clean_deals


async def scrape_viewport(page: Page) -> list:
    """
    Scrape all visible cards in the current viewport

    Args:
        page (Page): Playwright page object

    Returns:
        list: List of deal dictionaries
    """
    cards = await page.query_selector_all(CARD_SELECTOR)
    deals = []

    for card in cards:
        # Only cards currently in viewport
        if not await is_element_visible(card):
            continue

        title = await extract_text(card, TITLE_SELECTOR)
        if not title:
            continue

        category = await get_category_for_card(page, card)
        savings = await extract_text(card, SAVINGS_SELECTOR)
        offer = await extract_text(card, OFFER_SELECTOR)

        deal = {
            "category": category,
            "title": title,
            "savings": savings,
            "offer": offer,
        }

        deals.append(deal)

    print(f"Found {len(deals)} deals in viewport")
    return deals


async def async_main():
    try:
        with open("publix.json", "r") as f:
            data = json.load(f)
            timestamp_str = data.get("timestamp")
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str)
                if datetime.now(timezone.utc) - timestamp < timedelta(days=7):
                    print("Using cached publix.json file")
                else:
                    print("New deals available, refreshing cache")
                    raise ValueError("Cached data is stale")

    except (FileNotFoundError, json.JSONDecodeError, AttributeError, ValueError):
        print("Scraping Publix weekly ad...")
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=False)
            page = await browser.new_page(
                color_scheme="dark", viewport={"width": 1280, "height": 1600}
            )

            await page.goto(URL, wait_until="domcontentloaded")

            # Wait for real deal cards to appear (skeleton replaced by content)
            await page.wait_for_selector(
                '[data-qa="savings-weekly-card"]', timeout=60000
            )
            print("Page loaded")

            flat_deals = await scrape_publix(page)
            await browser.close()

        data = group_deals_by_category(flat_deals)
        print(f"Total deals found: {len(flat_deals)}")

        with open("publix.json", "w") as f:
            json.dump(data, f, indent=2)

    num_items = 0
    for cat in data["deals"]:
        print(cat["category"], "→", len(cat["items"]), "items")
        num_items += len(cat["items"])

    print(f"Total categories found: {len(data["deals"])}")
    print("Total items found ", num_items)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
