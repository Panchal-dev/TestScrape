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

    if movie_name:
        search_query = f"{movie_name.replace(' ', '+').lower()}"
        base_url = f"https://{SITE_CONFIG['cinevood']}/?s={search_query}"
    else:
        base_url = f"https://{SITE_CONFIG['cinevood']}/"

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        logger.debug(f"Fetching page {page}: {url}")

        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            logger.debug(f"Status code: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('article.latestPost.excerpt')
            logger.debug(f"Found {len(movie_elements)} movie elements")

            if not movie_elements:
                logger.warning("No movie elements found on this page.")
                with open(f"debug_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                if movie_name:
                    break
                continue

            for element in movie_elements:
                title_tag = element.select_one('h2.title.front-view-title a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title}")
                        movie_links.append(link)

            if movie_name:
                pagination = soup.find('div', class_='pagination')
                next_page = pagination.find('a', class_='next') if pagination else None
                if not next_page:
                    break

            time.sleep(3)

        except Exception as e:
            logger.error(f"Error fetching page {page}: {e}")
            break

    return all_titles, movie_links

def get_download_links(movie_url):
    scraper = cloudscraper.create_scraper()
    download_links = []
    
    try:
        logger.debug(f"Fetching movie page: {movie_url}")
        response = scraper.get(movie_url, timeout=10)
        response.raise_for_status()
        logger.debug(f"Status code: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')

        # Try primary selector: div.download-btns
        download_sections = soup.select('div.download-btns')
        if download_sections:
            logger.debug("Found download sections with 'div.download-btns' selector.")
            for section in soup.find_all('div', class_='download-btns'):
                description_tag = section.find('h6')
                link_tags = section.find_all('a', href=True)
                if description_tag and link_tags:
                    description = description_tag.text.strip()
                    if any(exclude in description.lower() for exclude in ['download', 'trailer']):
                        continue
                    for link_tag in link_tags:
                        link_text = link_tag.text.strip()
                        link_url = link_tag['href']
                        download_links.append(f"{description} [{link_text}]: {link_url}")

        # Try alternative structure: center > h6 + a.maxbutton-8 or a.maxbutton-9
        if not download_links:
            logger.debug("Trying new structure: center > h6 + a.maxbutton")
            center_tags = soup.find_all('center')
            for center_tag in center_tags:
                h6_tags = center_tag.find_all('h6')
                for h6_tag in h6_tags:
                    description = h6_tag.text.strip()
                    if any(exclude in description.lower() for exclude in ['download', 'trailer']):
                        continue
                    current = h6_tag.next_sibling
                    while current:
                        if current and hasattr(current, 'name') and current.name == 'a' and any(cls in current.get('class', []) for cls in ['maxbutton-8', 'maxbutton-9']):
                            link_text = current.find('span', class_='mb-text').text.strip() if current.find('span', class_='mb-text') else 'Download'
                            link_url = current['href']
                            download_links.append(f"{description} [{link_text}]: {link_url}")
                        elif current and hasattr(current, 'name') and current.name == 'p':
                            link_tags = current.find_all('a', class_=['maxbutton-8', 'maxbutton-9'])
                            for tag in link_tags:
                                link_text = tag.find('span', class_='mb-text').text.strip() if tag.find('span', class_='mb-text') else 'Download'
                                link_url = tag['href']
                                if 'Download' not in description.lower():
                                    download_links.append(f"{description} [{link_text}]: {link_url}")
                        elif current and hasattr(current, 'name') and current.name == 'h6':
                            break
                        current = current.next_sibling

        # Fallbacks: search for h6 tags globally
        if not download_links:
            logger.debug("Trying fallback: searching for downloading links for h6")
            h6_tags = soup.find_all('h6')
            for h6_tag in h6_tags:
                description = h6_tag.text.strip()
                if any(exclude in description.lower() for exclude in ['watch online', 'trailer']):
                    continue
                current = h6_tag.next_sibling
                while current:
                    if current and hasattr(current, 'name') and current.name == 'a' and any(cls in current.get('class', []) for cls in ['maxbutton-8', 'maxbutton-9']):
                        link_text = current.find('span', class_='mb-text').text.strip() if current.find('span', class_='mb-text') else 'Download'
                        link_url = current['href']
                        download_links.append(f"{description} [{link_text}]: {link_url}")
                    elif current and hasattr(current, 'name') and current.name == 'p':
                        link_tags = current.find_all('a', class_=['maxbutton-8', 'maxbutton-9'])
                        for tag in link_tags:
                            link_text = tag.find('span', class_='mb-text').text.strip() if tag.find('span', class_='mb-text') else 'Download'
                            link_url = tag['href']
                            if 'Download' not in description.lower():
                                download_links.append(f"{description} [{link_text}]: {link_url}")
                    elif current and hasattr(current, 'name') and current.name == 'h6':
                        break
                    current = current.next_sibling

        if not download_links:
            logger.warning("No download links found.")
            with open("debug_movie_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)

    except Exception as e:
        logger.error(f"Error fetching page: {e}")
        return []

    return download_links