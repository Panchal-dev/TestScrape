import cloudscraper
from bs4 import BeautifulSoup
import time
import os
from config import SITE_CONFIG, logger

def get_movie_titles_and_links(movie_name=None, max_pages=5):
    all_titles = []
    movie_links = []
    movie_count = 0
    scraper = cloudscraper.create_scraper()

    if not movie_name:
        featured_titles = []
        featured_links = []
        recently_added_titles = []
        recently_added_links = []

        url = f"https://{SITE_CONFIG['hdmovie2']}/movies/"
        logger.debug(f"Fetching featured movies: {url}")
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            logger.debug(f"Status code: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            featured_elements = soup.select('div.items.featured article.item.movies')
            logger.debug(f"Found {len(featured_elements)} featured movie elements with 'div.data.dfeatur h3 a' selector.")

            for element in featured_elements:
                title_tag = element.select_one('div.data.dfeatur h3 a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        featured_titles.append(f"{movie_count}. {title}")
                        featured_links.append(link)

            if not featured_elements:
                logger.warning("No featured movies found.")
                with open("debug_featured.html", "w", encoding="utf-8") as f:
                    f.write(response.text)

        except Exception as e:
            logger.error(f"Error fetching featured movies: {e}")

        for page in range(1, max_pages + 1):
            url = f"https://{SITE_CONFIG['hdmovie2']}/movies/page/{page}/" if page > 1 else f"https://{SITE_CONFIG['hdmovie2']}/movies/"
            logger.debug(f"Fetching recently added movies page {page}: {url}")
            try:
                response = scraper.get(url, timeout=10)
                response.raise_for_status()
                logger.debug(f"Status code: {response.status_code}")

                soup = BeautifulSoup(response.text, 'html.parser')
                recent_elements = soup.select('div#archive-content article.item.movies')
                logger.debug(f"Found {len(recent_elements)} recently added movie elements with 'div.data h3 a' selector.")

                for element in recent_elements:
                    title_tag = element.select_one('div.data h3 a')
                    if title_tag:
                        title = title_tag.text.strip()
                        link = title_tag['href']
                        if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                            movie_count += 1
                            recently_added_titles.append(f"{movie_count}. {title}")
                            recently_added_links.append(link)

                if not recent_elements:
                    logger.warning("No recently added movies found on this page.")
                    with open(f"debug_page_{page}.html", "w", encoding="utf-8") as f:
                        f.write(response.text)

                time.sleep(3)

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        all_titles = featured_titles[:15] + recently_added_titles
        movie_links = featured_links[:15] + recently_added_links

    else:
        search_query = f"{movie_name.replace(' ', '+').lower()}"
        base_url = f"https://{SITE_CONFIG['hdmovie2']}/?s={search_query}"
        page = 1

        while True:
            url = base_url if page == 1 else f"https://{SITE_CONFIG['hdmovie2']}/page/{page}/?s={search_query}"
            logger.debug(f"Fetching search page {page}: {url}")
            try:
                response = scraper.get(url, timeout=10)
                response.raise_for_status()
                logger.debug(f"Status code: {response.status_code}")

                soup = BeautifulSoup(response.text, 'html.parser')
                movie_elements = soup.select('div.result-item')
                logger.debug(f"Found {len(movie_elements)} movie elements with 'div.details div.title a' selector.")

                if not movie_elements:
                    logger.warning("No movie elements found on this page.")
                    with open(f"debug_page_{page}.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    break

                for element in movie_elements:
                    title_tag = element.select_one('div.details div.title a')
                    if title_tag:
                        title = title_tag.text.strip()
                        link = title_tag['href']
                        if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                            movie_count += 1
                            all_titles.append(f"{movie_count}. {title}")
                            movie_links.append(link)

                pagination = soup.find('div', class_='pagination')
                next_page = pagination.find('a', class_='inactive') if pagination else None
                if not next_page:
                    logger.debug("No next page found.")
                    break

                page += 1
                time.sleep(3)

            except Exception as e:
                logger.error(f"Error fetching search page {page}: {e}")
                break

    return all_titles, movie_links

def get_download_links(movie_url):
    scraper = cloudscraper.create_scraper()
    
    try:
        logger.debug(f"Fetching movie page: {movie_url}")
        response = scraper.get(movie_url, timeout=10)
        response.raise_for_status()
        logger.debug(f"Status code: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        download_link_tags = soup.select('div.wp-content p a[href*="dwo.hair"]')
        if not download_link_tags:
            logger.warning("No download page link found on this page.")
            with open("debug_movie_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            return []

        download_page_url = download_link_tags[0]['href']
        logger.debug(f"Fetching download page: {download_page_url}")
        response = scraper.get(download_page_url, timeout=10)
        response.raise_for_status()
        logger.debug(f"Status code: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        download_links = []
        for idx, tag in enumerate(soup.select('div.download-links-section p a[href]'), 1):
            link_text = tag.text.strip()
            link_url = tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer']):
                download_links.append(f"{idx}) **{link_text}** : {link_url}\n")

        if not download_links:
            logger.warning("No download links found on this page.")
            with open("debug_download_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)

        return download_links

    except Exception as e:
        logger.error(f"Error fetching page: {e}")
        return []