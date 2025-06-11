import requests
from bs4 import BeautifulSoup
import time
import os
from config import SITE_CONFIG, logging

logger = logging.getLogger(__name__)

def escape_markdown_v2(text):
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        if char:
            text = text.replace(char, f'\\{char}')
    return text

def get_download_titles_and_links(movie_name=None, site=None, max_pages=5):
    query = f"{movie_name.replace(' ', '+').lower()}" if movie_name else ""
    base_url = f"https://{SITE_CONFIG['hdhub4u']}/?s={query}" if movie_name else f"https://{SITE_CONFIG['hdhub4u']}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    
    page = 1
    movie_count = 0
    all_titles = []
    movie_links = []
    session = requests.Session()
    
    while page <= max_pages:
        url = base_url if page == 1 else f"https://{SITE_CONFIG['hdhub4u']}/page/{page}/{'?s=' + query if movie_name else ''}"
        logger.debug(f"Fetching page {page}: {url}")

        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            logger.debug(f"Status code: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('ul.recent-movies li')
            logger.debug(f"Found {len(movie_elements)} movie elements with 'ul.recent-movies li' selector.")

            if not movie_elements:
                logger.warning("No movie elements found on this page.")
                with open(f"debug_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                if movie_name:
                    break
                page += 1
                continue

            for element in movie_elements:
                title_tag = element.select_one('figcaption p')
                link_tag = element.select_one('figure a[href]')
                if title_tag and link_tag:
                    title = title_tag.text.strip()
                    link = link_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title}")
                        movie_links.append(link)

            if movie_name:
                pagination = soup.find('div', class_='pagination-wrap')
                if not pagination or not pagination.find('a', class_='next page-numbers'):
                    logger.debug("No next page found.")
                    break

            page += 1
            time.sleep(3)

        except requests.RequestException as e:
            logger.error(f"Error fetching page {page}: {e}")
            break

    return all_titles, movie_links

def get_download_links(movie_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    
    try:
        logger.debug(f"Fetching movie page: {movie_url}")
        response = requests.get(movie_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.debug(f"Status code: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        download_links = []
        for idx, tag in enumerate(soup.select('h3 a[href], h4 a[href]'), 1):
            link_text = tag.find('em').text.strip() if tag.find('em') else tag.text.strip()
            link_text = escape_markdown_v2(link_text)
            link_url = tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['trailer', 'watch online', 'player']):
                download_links.append(f"{idx}.) **{link_text}** : {link_url}\n\n")

        if not download_links:
            logger.warning("No download or watch online links found on this page.")
            with open("debug_movie_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)

        return download_links

    except requests.RequestException as e:
        logger.error(f"Error in get_download_links for {movie_url}: {str(e)}")
        return []