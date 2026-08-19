from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

from openpyxl import Workbook
from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from contact_utils import (
    clean, emails_from_text, is_company_social_url, normalize_company,
    phones_from_text, platform_for_social, root_host, unique, unwrap_redirect,
)

COORD_RE = re.compile(r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
CONTACT_WORDS = ("contact", "about", "location", "locations", "reach", "support", "company", "office")
ADDRESS_LABELS = ("address", "location", "headquarters", "registered office", "corporate office", "office address")
IGNORED_HOSTS = {
    "google.com", "googleusercontent.com", "gstatic.com", "bing.com", "fbcdn.net",
    "cdninstagram.com", "licdn.com", "doubleclick.net", "youtube.com", "youtu.be",
}


@dataclass
class ConnectedBusiness:
    business_name: str = ""
    category: str = ""
    google_address: str = ""
    consolidated_addresses: str = ""
    google_phone: str = ""
    consolidated_phones: str = ""
    public_emails: str = ""
    official_website: str = ""
    facebook_url: str = ""
    instagram_url: str = ""
    linkedin_url: str = ""
    rating: str = ""
    review_count: str = ""
    business_status: str = ""
    hours: str = ""
    latitude: str = ""
    longitude: str = ""
    google_maps_url: str = ""
    google_query: str = ""
    google_status: str = ""
    website_status: str = ""
    social_status: str = ""
    pages_scanned: str = ""
    connection_method: str = ""
    record_status: str = ""
    error_message: str = ""
    collected_at: str = ""


def log(message: str):
    """Print immediately so long browser operations never look frozen."""
    print(message, flush=True)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def text(page: Page, selectors: list[str]) -> str:
    for selector in selectors:
        try:
            item = page.locator(selector).first
            if item.count() and item.is_visible(timeout=500):
                value = clean(item.inner_text(timeout=1200))
                if value:
                    return value
        except Exception:
            continue
    return ""


def attr(page: Page, selectors: list[str], name: str) -> str:
    for selector in selectors:
        try:
            item = page.locator(selector).first
            if item.count():
                value = clean(item.get_attribute(name, timeout=1200))
                if value:
                    return value
        except Exception:
            continue
    return ""


def strip_label(value: str, labels: tuple[str, ...]) -> str:
    result = clean(value)
    for label in labels:
        result = re.sub(rf"^{re.escape(label)}\s*:?\s*", "", result, flags=re.I)
    return clean(result)


def review_number(value: str) -> str:
    match = re.search(r"([\d,.]+)", value or "")
    return match.group(1).replace(",", "") if match else ""


def accept_consent(page: Page):
    for label in ("Accept all", "Reject all", "I agree"):
        try:
            button = page.get_by_role("button", name=label, exact=True).first
            if button.count() and button.is_visible(timeout=500):
                button.click(); page.wait_for_timeout(500); return
        except Exception:
            continue


def body_text(page: Page, limit: int = 20000) -> str:
    try:
        return clean(page.locator("body").inner_text(timeout=5000))[:limit]
    except Exception:
        return ""


def google_page_problem(page: Page) -> str:
    body = body_text(page).casefold()
    if any(term in body for term in ("unusual traffic", "captcha", "automated queries")):
        return "Google displayed CAPTCHA or unusual-traffic protection. Stop and try again later."
    if any(term in body for term in ("can't connect", "can’t connect", "this site can’t be reached", "no internet")):
        return "Google Maps did not load because of a network problem."
    return ""


def discover_google_urls(page: Page, query: str, limit: int) -> list[str]:
    url = f"https://www.google.com/maps/search/{quote(query, safe='')}?hl=en"
    log("  Opening Google Maps...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    accept_consent(page)
    page.wait_for_timeout(2500)
    problem = google_page_problem(page)
    if problem:
        page.screenshot(path="google_maps_error.png", full_page=True)
        raise RuntimeError(problem + " Screenshot: google_maps_error.png")
    feed = page.locator("div[role='feed']")
    if "/maps/place/" in page.url and not feed.count():
        log("  Google opened one direct listing.")
        return [page.url]
    log("  Waiting for the Google Maps results panel...")
    try:
        feed.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        try:
            hrefs = page.locator("a[href*='/maps/place/']").evaluate_all("els => els.map(e => e.href || '')")
        except Exception:
            hrefs = []
        fallback = unique(href.split("?", 1)[0] for href in hrefs if href)
        if fallback:
            log(f"  Results panel changed; using {len(fallback[:limit])} visible listing link(s).")
            return fallback[:limit]
        page.screenshot(path="google_maps_error.png", full_page=True)
        raise RuntimeError("Google Maps results panel was not found. Check google_maps_error.png for consent, CAPTCHA, or a connection error.")
    found, seen, stagnant = [], set(), 0
    previous_count = 0
    rounds = 0
    # Large jobs need more scroll rounds, while the stagnant guard still stops
    # cleanly when Google has no additional public listings to show.
    while len(found) < limit and stagnant < 12 and rounds < 400:
        rounds += 1
        try:
            hrefs = feed.locator("a[href*='/maps/place/']").evaluate_all("els => els.map(e => e.href || '')")
        except Exception:
            hrefs = []
        for href in hrefs:
            key = href.split("?", 1)[0]
            if key and key not in seen:
                seen.add(key); found.append(href)
                if len(found) >= limit:
                    break
        log(f"  Discovery progress: {len(found)}/{limit} listing URL(s)")
        end_text = body_text(page, 60000).casefold()
        if any(term in end_text for term in ("you've reached the end of the list", "you’ve reached the end of the list")):
            break
        feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
        page.wait_for_timeout(1200)
        current = len(found)
        stagnant = stagnant + 1 if current <= previous_count else 0
        previous_count = current
    if not found:
        page.screenshot(path="google_maps_error.png", full_page=True)
        raise RuntimeError("Google Maps loaded but no listing URLs were found. Check google_maps_error.png.")
    return found[:limit]


def extract_google_business(page: Page, listing_url: str, query: str) -> dict:
    page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.locator("h1").first.wait_for(state="visible", timeout=12000)
    except PlaywrightTimeoutError:
        problem = google_page_problem(page)
        if problem:
            raise RuntimeError(problem)
    page.wait_for_timeout(700)
    name = text(page, ["h1.DUwDvf", "h1"])
    category = text(page, ["button[jsaction*='category']", "button.DkEaL"])
    address = strip_label(
        attr(page, ["button[data-item-id='address']"], "aria-label") or text(page, ["button[data-item-id='address']"]),
        ("Address",),
    )
    phone = strip_label(attr(page, ["button[data-item-id^='phone:tel:']"], "aria-label"), ("Phone",))
    website = unwrap_redirect(attr(page, ["a[data-item-id='authority']"], "href"))
    rating = attr(page, ["div.F7nice span[aria-hidden='true']", "span.MW4etd"], "aria-label") or text(
        page, ["div.F7nice span[aria-hidden='true']", "span.MW4etd"]
    )
    reviews = review_number(
        attr(page, ["button[jsaction*='pane.reviewChart.moreReviews']"], "aria-label") or text(page, ["span.UY7F9"])
    )
    status = text(page, ["span.ZDu9vd span", "div.o0Svhf span"])
    hours = strip_label(attr(page, ["button[data-item-id='oh']", "div[data-item-id='oh']"], "aria-label"), ("Hours",))
    current_url = page.url
    coordinates = COORD_RE.search(current_url)
    latitude, longitude = (coordinates.group(1), coordinates.group(2)) if coordinates else ("", "")
    return {
        "name": name, "category": category, "address": address, "phone": phone,
        "website": website, "rating": clean(rating), "reviews": reviews, "status": status,
        "hours": hours, "latitude": latitude, "longitude": longitude,
        "maps_url": current_url, "query": query,
    }


def jsonld_contacts(page: Page) -> tuple[list[str], list[str], list[str]]:
    emails, phones, addresses = [], [], []
    try:
        scripts = page.locator("script[type='application/ld+json']").all_text_contents()
    except Exception:
        return emails, phones, addresses

    def address_value(value) -> str:
        if isinstance(value, str):
            return clean(value)
        if not isinstance(value, dict):
            return ""
        parts = []
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
            item = value.get(key)
            if isinstance(item, dict):
                item = item.get("name")
            if item:
                parts.append(clean(str(item)))
        return ", ".join(parts)

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                lower = key.casefold()
                if lower == "email" and isinstance(item, str):
                    emails.extend(emails_from_text(item))
                elif lower in {"telephone", "phone", "faxnumber"} and isinstance(item, str):
                    phones.append(item)
                elif lower in {"address", "postaladdress"}:
                    candidate = address_value(item)
                    if candidate:
                        addresses.append(candidate)
                walk(item)

    for raw in scripts:
        try:
            walk(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return unique(emails), unique(phones), unique(addresses)


def labelled_addresses(raw: str) -> list[str]:
    lines = [clean(line) for line in raw.splitlines() if clean(line)]
    output = []
    for index, line in enumerate(lines):
        lower = line.casefold().rstrip(":")
        if lower in ADDRESS_LABELS and index + 1 < len(lines):
            candidate = lines[index + 1]
            if 5 <= len(candidate) <= 240:
                output.append(candidate)
        for label in ADDRESS_LABELS:
            match = re.match(rf"^{re.escape(label)}\s*:\s*(.+)$", line, re.I)
            if match and 5 <= len(match.group(1)) <= 240:
                output.append(match.group(1)); break
    return unique(output)


def public_page_snapshot(page: Page) -> dict:
    page.wait_for_timeout(1100)
    try:
        raw = page.locator("body").inner_text(timeout=6000)[:100000]
    except Exception:
        raw = ""
    link_emails, link_phones, social_urls = [], [], []
    try:
        links = page.locator("a[href]").evaluate_all("els => els.map(e => e.href || '')")
    except Exception:
        links = []
    for href in links:
        href = unwrap_redirect(href)
        if href.lower().startswith("mailto:"):
            link_emails.append(href.split(":", 1)[1].split("?", 1)[0])
        elif href.lower().startswith("tel:"):
            link_phones.append(href.split(":", 1)[1].split("?", 1)[0])
        elif is_company_social_url(href):
            social_urls.append(href.split("?", 1)[0].rstrip("/") + "/")
    ld_emails, ld_phones, ld_addresses = jsonld_contacts(page)
    return {
        "emails": unique(emails_from_text(raw) + link_emails + ld_emails),
        "phones": unique(phones_from_text(raw) + link_phones + ld_phones),
        "addresses": unique(labelled_addresses(raw) + ld_addresses),
        "social_urls": unique(social_urls), "raw": clean(raw), "url": page.url,
    }


def robots_allowed(page: Page, url: str) -> bool:
    parsed = urlparse(url); robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = page.context.request.get(robots_url, timeout=6000)
        if response.ok:
            parser = RobotFileParser(); parser.set_url(robots_url); parser.parse(response.text().splitlines())
            return parser.can_fetch("ITCYBER-Connected-Business-Scraper", url)
    except Exception:
        pass
    return True


def contact_page_links(page: Page, host: str) -> list[str]:
    try:
        hrefs = page.locator("a[href]").evaluate_all("els => els.map(e => e.href || '')")
    except Exception:
        return []
    output = []
    for href in hrefs:
        url = urljoin(page.url, href).split("#", 1)[0]
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and root_host(url) == host:
            searchable = (parsed.path + " " + parsed.query).casefold()
            if any(word in searchable for word in CONTACT_WORDS):
                output.append(url)
    return unique(output)


def scan_website(context: BrowserContext, website: str, max_pages: int, delay: float) -> dict:
    result = {"emails": [], "phones": [], "addresses": [], "social_urls": [], "pages": [], "status": "website_not_found"}
    if not website or urlparse(website).scheme not in {"http", "https"}:
        return result
    page = context.new_page(); queue = [website]; seen = set(); expected_host = root_host(website)
    try:
        log(f"    Website: {website}")
        while queue and len(seen) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            if seen and root_host(url) != expected_host:
                continue
            seen.add(url)
            if not robots_allowed(page, url):
                result["status"] = "robots_disallowed"; continue
            try:
                log(f"      Scanning page {len(seen)}/{max_pages}: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                if len(seen) == 1:
                    expected_host = root_host(page.url)
                snapshot = public_page_snapshot(page)
                for key in ("emails", "phones", "addresses", "social_urls"):
                    result[key] = unique(result[key] + snapshot[key])
                result["pages"].append(page.url); result["status"] = "ok"
                if len(seen) == 1:
                    queue.extend(contact_page_links(page, expected_host))
                page.wait_for_timeout(int(delay * 1000))
            except PlaywrightTimeoutError:
                result["status"] = "partial_timeout"
            except Exception:
                result["status"] = "partial_error"
    finally:
        page.close()
    return result


def social_about_urls(url: str) -> list[str]:
    parts = [part for part in urlparse(url).path.split("/") if part]
    platform = platform_for_social(url)
    if platform == "LinkedIn" and len(parts) >= 2:
        return [f"https://www.linkedin.com/{parts[0]}/{parts[1]}/about/"]
    if platform == "Facebook" and parts:
        base = f"https://www.facebook.com/{parts[0]}"
        return [base + "/about", base + "/about_contact_and_basic_info"]
    return []


def scan_social(context: BrowserContext, urls: list[str], delay: float) -> dict:
    result = {"emails": [], "phones": [], "addresses": [], "pages": [], "statuses": []}
    page = context.new_page()
    try:
        for url in unique(urls):
            if not is_company_social_url(url):
                continue
            targets = [url] + social_about_urls(url)
            for target in targets:
                try:
                    log(f"    Public social page: {target}")
                    page.goto(target, wait_until="domcontentloaded", timeout=25000)
                    snapshot = public_page_snapshot(page)
                    for key in ("emails", "phones", "addresses"):
                        result[key] = unique(result[key] + snapshot[key])
                    result["pages"].append(page.url)
                    lower = snapshot["raw"].casefold()
                    if any(term in lower for term in ("captcha", "temporarily blocked", "unusual activity")):
                        result["statuses"].append("blocked_or_captcha")
                    elif any(term in lower for term in ("log in to continue", "sign in to view", "join linkedin")):
                        result["statuses"].append("login_required_or_limited")
                    else:
                        result["statuses"].append("ok")
                    page.wait_for_timeout(int(delay * 1000))
                except PlaywrightTimeoutError:
                    result["statuses"].append("timeout")
                except Exception:
                    result["statuses"].append("error")
    finally:
        page.close()
    return result


def load_queries(path: Path) -> list[str]:
    if not path.exists():
        return []
    return unique(line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.strip().startswith("#"))


def load_manual_social(path: Path) -> dict[str, list[str]]:
    mapping = {}
    if not path.exists():
        return mapping
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            name = clean(row.get("company_name"))
            if not name or name.startswith("#"):
                continue
            urls = [row.get("facebook_url", ""), row.get("instagram_url", ""), row.get("linkedin_url", "")]
            mapping[normalize_company(name)] = [url for url in urls if is_company_social_url(clean(url))]
    return mapping


def social_columns(urls: list[str]) -> dict[str, str]:
    output = {"Facebook": "", "Instagram": "", "LinkedIn": ""}
    for url in urls:
        platform = platform_for_social(url)
        if platform and not output[platform]:
            output[platform] = url
    return output


def build_record(
    context: BrowserContext,
    google: dict,
    manual_social: dict[str, list[str]],
    max_website_pages: int,
    delay: float,
    enrichment: str,
) -> ConnectedBusiness:
    errors = []
    website_data = {
        "emails": [], "phones": [], "addresses": [], "social_urls": [],
        "pages": [], "status": "website_scan_disabled",
    }
    if enrichment != "none":
        try:
            website_data = scan_website(context, google["website"], max_website_pages, delay)
        except Exception as exc:
            errors.append(f"website: {clean(str(exc))[:200]}")
            website_data["status"] = "website_scan_error"
    auto_social = website_data["social_urls"]
    manual_urls = manual_social.get(normalize_company(google["name"]), [])
    social_urls = unique(auto_social + manual_urls)
    social_data = {"emails": [], "phones": [], "addresses": [], "pages": [], "statuses": []}
    if enrichment == "full" and social_urls:
        try:
            social_data = scan_social(context, social_urls, delay)
        except Exception as exc:
            errors.append(f"social: {clean(str(exc))[:200]}")
            social_data["statuses"] = ["social_scan_error"]
    elif enrichment == "full":
        social_data["statuses"] = ["social_profiles_not_found"]
    else:
        social_data["statuses"] = ["social_scan_disabled"]
    columns = social_columns(social_urls)
    addresses = unique([google["address"]] + website_data["addresses"] + social_data["addresses"])
    phones = unique([google["phone"]] + website_data["phones"] + social_data["phones"])
    emails = unique(website_data["emails"] + social_data["emails"])
    pages = unique([google["maps_url"]] + website_data["pages"] + social_data["pages"])
    if enrichment == "none":
        connection = "google_only"
    elif auto_social:
        connection = "official_website_social_links"
    elif manual_urls:
        connection = "manual_company_name_mapping"
    else:
        connection = "google_and_website_only"
    return ConnectedBusiness(
        business_name=google["name"], category=google["category"], google_address=google["address"],
        consolidated_addresses="; ".join(addresses), google_phone=google["phone"],
        consolidated_phones="; ".join(phones), public_emails="; ".join(emails),
        official_website=google["website"], facebook_url=columns["Facebook"],
        instagram_url=columns["Instagram"], linkedin_url=columns["LinkedIn"],
        rating=google["rating"], review_count=google["reviews"], business_status=google["status"],
        hours=google["hours"], latitude=google["latitude"], longitude=google["longitude"],
        google_maps_url=google["maps_url"], google_query=google["query"], google_status="ok",
        website_status=website_data["status"], social_status="; ".join(unique(social_data["statuses"])),
        pages_scanned="; ".join(pages), connection_method=connection,
        record_status="completed_with_warnings" if errors else "completed",
        error_message="; ".join(errors),
        collected_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def partial_record(query: str, maps_url: str, stage: str, error: Exception | str, google: dict | None = None) -> ConnectedBusiness:
    """Preserve every field already collected when a later stage fails."""
    google = google or {}
    address = google.get("address", "")
    phone = google.get("phone", "")
    return ConnectedBusiness(
        business_name=google.get("name", ""), category=google.get("category", ""),
        google_address=address, consolidated_addresses=address,
        google_phone=phone, consolidated_phones=phone,
        official_website=google.get("website", ""), rating=google.get("rating", ""),
        review_count=google.get("reviews", ""), business_status=google.get("status", ""),
        hours=google.get("hours", ""), latitude=google.get("latitude", ""),
        longitude=google.get("longitude", ""), google_maps_url=google.get("maps_url") or maps_url,
        google_query=google.get("query", query), google_status=f"failed_at_{stage}",
        pages_scanned=google.get("maps_url") or maps_url, connection_method="partial_record",
        record_status="partial_error", error_message=clean(str(error))[:500],
        collected_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def save(records: list[ConnectedBusiness], path: Path, fmt: str):
    names = [field.name for field in fields(ConnectedBusiness)]
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=names); writer.writeheader(); writer.writerows(asdict(record) for record in records)
    else:
        workbook = Workbook(); sheet = workbook.active; sheet.title = "Connected Businesses"; sheet.append(names)
        for record in records:
            sheet.append([getattr(record, name) for name in names])
        sheet.freeze_panes = "A2"; sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(60, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
        workbook.save(path)


def save_checkpoint(records: list[ConnectedBusiness], path: Path, fmt: str) -> bool:
    try:
        save(records, path, fmt)
        return True
    except PermissionError:
        log(f"    WARNING: Cannot update {path}. Close the file in Excel; collection will continue.")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect public Google Business and company social profiles locally without API keys.")
    parser.add_argument("--query", action="append", help="Google Maps query. Repeat for multiple queries.")
    parser.add_argument("--queries-file", default="queries.txt")
    parser.add_argument("--manual-social-file", default="manual_social_profiles.csv")
    parser.add_argument("--max-results", type=int, default=100, help="Maximum Google results per query (1-2000).")
    parser.add_argument("--max-website-pages", type=int, default=2, help="Official website pages per business (1-8).")
    parser.add_argument("--delay", type=float, default=2.5)
    parser.add_argument(
        "--enrichment", choices=["full", "website", "none"], default="full",
        help="full=Google+website+social; website=Google+website; none=Google only",
    )
    parser.add_argument("--format", choices=["xlsx", "csv", "json"], default="xlsx")
    parser.add_argument("--output", default="output/connected_business_profiles.xlsx")
    parser.add_argument("--login", action="store_true", help="Open persistent browser for manual social login.")
    args = parser.parse_args()
    if not 1 <= args.max_results <= 2000:
        parser.error("--max-results must be between 1 and 2000")
    if not 1 <= args.max_website_pages <= 8:
        parser.error("--max-website-pages must be between 1 and 8")
    if args.delay < 2:
        parser.error("--delay must be at least 2 seconds")
    profile = Path(os.environ.get("ITCYBER_BROWSER_PROFILE_DIR", "browser_profile")).resolve()
    profile.parent.mkdir(parents=True, exist_ok=True)
    headless = env_bool("ITCYBER_HEADLESS", default=False)
    output = Path(args.output).with_suffix("." + args.format)
    records: list[ConnectedBusiness] = []
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                headless=headless,
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                args=["--disable-dev-shm-usage"],
            )
            try:
                main_page = context.pages[0] if context.pages else context.new_page()
                if args.login:
                    main_page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
                    input("Login manually in browser tabs, then press Enter here...")
                    log(f"Login session saved in browser profile: {profile}")
                    return 0
                queries = unique(args.query or load_queries(Path(args.queries_file)))
                if not queries:
                    raise RuntimeError("No query provided. Use --query or add queries to queries.txt")
                manual_social = load_manual_social(Path(args.manual_social_file))
                seen_businesses = set()
                detail_page = context.new_page()
                for query in queries:
                    log(f"\nGoogle Maps query: {query}")
                    try:
                        listing_urls = discover_google_urls(main_page, query, args.max_results)
                        log(f"  Discovered {len(listing_urls)} listing(s). Starting detail extraction...")
                    except Exception as exc:
                        records.append(partial_record(query, "", "google_discovery", exc))
                        save_checkpoint(records, output, args.format)
                        log(f"  Query failed; diagnostic row saved: {exc}")
                        continue
                    for index, listing_url in enumerate(listing_urls, 1):
                        google = None
                        try:
                            log(f"  [{index}/{len(listing_urls)}] Reading Google listing...")
                            google = extract_google_business(detail_page, listing_url, query)
                            if not google["name"]:
                                raise RuntimeError("Google listing opened, but its business name was not visible.")
                            business_key = (
                                google["maps_url"].split("?", 1)[0]
                                or f"{normalize_company(google['name'])}|{clean(google['address']).casefold()}"
                            )
                            if business_key in seen_businesses:
                                log(f"    Duplicate skipped: {google['name']}")
                                continue
                            seen_businesses.add(business_key)
                            log(f"    Business: {google['name']}")
                            records.append(build_record(
                                context, google, manual_social, args.max_website_pages, args.delay, args.enrichment
                            ))
                            save_checkpoint(records, output, args.format)
                            log(f"    Checkpoint saved ({len(records)} record(s)): {output}")
                        except Exception as exc:
                            records.append(partial_record(query, listing_url, "listing", exc, google))
                            save_checkpoint(records, output, args.format)
                            log(f"    Listing error saved as a partial row: {exc}")
                        detail_page.wait_for_timeout(int(args.delay * 1000))
            finally:
                context.close()
        if not save_checkpoint(records, output, args.format):
            raise RuntimeError(f"Could not write final output because {output} is open in another program.")
        log(f"\nFinished. Saved {len(records)} record(s) to {output.resolve()}")
        return 0
    except KeyboardInterrupt:
        if records:
            if save_checkpoint(records, output, args.format):
                print(f"\nStopped by user. Partial data saved to {output.resolve()}", file=sys.stderr, flush=True)
            else:
                print("\nStopped by user. Close Excel before the next run so checkpoints can be written.", file=sys.stderr, flush=True)
        else:
            print("\nStopped by user before any records were collected.", file=sys.stderr, flush=True)
        return 130
    except Exception as exc:
        if records:
            saved = save_checkpoint(records, output, args.format)
            suffix = f"\nPartial data saved to {output.resolve()}" if saved else "\nOutput could not be updated because it is open."
            print(f"\nERROR: {exc}{suffix}", file=sys.stderr, flush=True)
        else:
            print(f"\nERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
