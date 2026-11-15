import aiohttp
import asyncio
import requests
from bs4 import BeautifulSoup, Tag
from typing import TypedDict
from urllib.parse import *

class PageData(TypedDict):
    url: str
    heading: str
    first_paragraph: str
    outgoing_links: list[str]
    image_urls: list[str]


class AsyncCrawler:
    def __init__(self, base_url, max_concurrency, max_pages):
        self.base_url = base_url
        self.base_domain = urlsplit(base_url).netloc
        self.page_data: dict[str, PageData] = {}
        self.visited: set[str] = set()
        self.lock = asyncio.Lock()
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.session: aiohttp.ClientSession | None = None
        self.max_pages = max_pages
        self.should_stop = False
        self.all_tasks = set()
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session is not None:
            await self.session.close()
    
    async def add_page_visit(self, normalized_url: str) -> bool:
        async with self.lock:
            if self.should_stop:
                return False
            if len(self.visited) >= self.max_pages:
                self.should_stop = True
                return False
            if normalized_url in self.visited:
                return False
            self.visited.add(normalized_url)
            return True
    
    async def get_html(self, url: str) -> str | None:
        if self.session is None:
            return None
        try:
            async with self.session.get(url, headers={"user-agent": "BootCrawler/1.0"}) as r:
                if r.status > 399:
                    print(f"Error: HTTP {r.status} for {url}")
                    return None
                # Exception if content isnt text/html
                if "text/html" not in r.headers.get("content-type"):
                    print(f"Expected text/html, but received unexpected Content-Type: '{r.headers.get("content-type")}'")
                    return None
                return await r.text()
        except Exception as e:
            raise Exception(f"network error while fetching {url}: {e}")

    async def crawl_page(self, current_url: str) -> None:
        if self.should_stop:
            return
        current_url_obj = urlsplit(current_url)
        if current_url_obj.netloc != self.base_domain:
            return
        
        normalized_url = normalize_url(current_url)
        is_new_page = await self.add_page_visit(normalized_url)
        if not is_new_page:
            return

        async with self.semaphore:
            html = await self.get_html(current_url)
        if html is None:
            return

        page_info = extract_page_data(html, current_url)
        async with self.lock:
            self.page_data[normalized_url] = page_info

        next_urls = page_info["outgoing_links"]
        
        tasks: list[asyncio.Task[None]] = []
        for next_url in next_urls:
            task = asyncio.create_task(self.crawl_page(next_url))
            tasks.append(task)
            self.all_tasks.add(task)

        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                for task in tasks:
                    self.all_tasks.discard(task)

    async def crawl(self):
        await self.crawl_page(self.base_url)
        return self.page_data

async def crawl_site_async(base_url: str, max_concurrency: int, max_pages: int) -> dict[str, PageData]:
    async with AsyncCrawler(base_url, max_concurrency, max_pages) as crawler:
        return await crawler.crawl()




def normalize_url(url: str) -> str:
    splitted_url = urlsplit(url)
    return f"{splitted_url.netloc}{splitted_url.path.rstrip("/")}"

def get_heading_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h_tag = soup.find("h1") or soup.find("h2")
    if isinstance(h_tag, Tag):
        return h_tag.get_text(strip=True)
    return ""

def get_first_paragraph_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    main_tag = soup.find("main")
    if isinstance(main_tag, Tag):
        p_tag = main_tag.find("p") or soup.find("p")
    else:
        p_tag = soup.find("p")
    if isinstance(p_tag, Tag):
        return p_tag.get_text(strip=True)
    return ""

def get_urls_from_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    a_list = []
    for a in soup.find_all("a"):
        a_list.append(urljoin(base_url, a.get("href")))
    return a_list

def get_images_from_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    img_list = []
    for img in soup.find_all("img"):
        img_list.append(urljoin(base_url, img.get("src")))
    return img_list

def extract_page_data(html: str, page_url: str) -> PageData:
    data: PageData = {
        "url": page_url,
        "heading": get_heading_from_html(html),
        "first_paragraph": get_first_paragraph_from_html(html),
        "outgoing_links": get_urls_from_html(html, page_url),
        "image_urls": get_images_from_html(html, page_url)
    }
    return data

def get_html(url: str) -> str:
    try:
        h = {"user-agent": "BootCrawler/1.0"}
        r = requests.get(url, headers=h)
    except Exception as e:
        raise Exception(f"network error while fetching {url}: {e}")
    
    # Exception for bad HTTP status
    r.raise_for_status()

    # Exception if content isnt text/html
    if "text/html" not in r.headers.get("content-type"):
        raise ValueError(f"Expected text/html, but received unexpected Content-Type: '{r.headers.get("content-type")}'")
    
    return r.content

def crawl_page(
    base_url: str, 
    current_url: str | None = None,
    page_data: dict[str, PageData] | None = None
) -> dict[str, PageData]:
    if current_url is None:
        current_url = base_url
    if page_data is None:
        page_data = {}

    base_domain = urlsplit(base_url).netloc
    current_domain = urlsplit(current_url).netloc
    if base_domain != current_domain:
        return page_data

    current_normalized = normalize_url(current_url)

    # Check if we have crawled to current_normalized
    if current_normalized in page_data:
        return page_data
    
    # Get the html data of the current_url
    current_html = get_html(current_url)
    if current_html is None:
        return page_data

    # Add the HTML into page_data
    current_page_data = extract_page_data(current_html, current_url)
    page_data[current_normalized] = current_page_data

    # Crawl to the next links recursively
    next_urls = current_page_data["outgoing_links"]
    for next_url in next_urls:
        crawl_page(base_url, next_url, page_data)
    
    # Final return result
    return page_data

