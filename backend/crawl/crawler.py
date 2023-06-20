import requests
from pydantic import BaseModel
import re
import unicodedata
import os
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import json
from utils.file import compute_sha1_from_content


class CrawlWebsite(BaseModel):
    url : str
    js : bool = False
    depth : int = 1
    max_pages : int = 100
    max_time : int = 60
    async def process(self, out_dir):
        crawler = Crawler(url=self.url, js=self.js, depth=self.depth,
                        max_pages=self.max_pages, max_time=self.max_time,
                        out_dir=out_dir)
        await crawler.process()

class SiteInfo:
    filepath : str
    fetched_urls : dict = dict()
    unfetched : set = set()
    def __init__(self, filepath):
        self.filepath = filepath
        self.load()

    def add_new_url(self, url):
        if url not in self.fetched_urls:
            #print(url)
            self.unfetched.add(url)
    def remove_not_found_url(self, url):
        self.unfetched.discard(url)
    def add_fetched_url(self, url, filepath = None, filesha1 = None):
        self.unfetched.discard(url)
        if filepath is not None and filesha1 is not None:
            if filesha1 in self.fetched_urls:
                print(f"file {filepath} / url {url} has been downloaded, skip")
                return False
            self.fetched_urls[filesha1] = {"filepath": filepath, "url": url}
        return True
    def get_unfetch_urls(self):
        return self.unfetched
    def save(self):
        with open(self.filepath, "w") as f:
            urls = {"fetched": self.fetched_urls, "unfetched": list(self.unfetched)}
            json.dump(urls, f)
    def load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as f:
                urls = json.load(f)
                self.fetched_urls = urls.get("fetched", ())
                self.unfetched = set(urls.get("unfetched", ()))

class Crawler:
    url : str
    js : bool = False
    depth : int = 1
    max_pages : int = 100
    max_time : int = 60
    pattern : re.Pattern
    base_url : str
    out_dir: str
    urls : SiteInfo = None
    pages : int = 0
    def __init__(self, url, out_dir, js : bool = False, depth : int = 1, max_pages : int = 100, max_time : int = 60):
        self.url = url
        self.js = js
        self.depth = depth
        self.max_pages = max_pages
        self.max_time = max_time
        self.out_dir = out_dir or 'out'
        self.urls = SiteInfo(os.path.join(self.out_dir, "site_metadata.json"))

        parsed_url = urlparse(self.url)
        self.pattern=re.compile(f"^{self.url}"),
        self.base_url=parsed_url.scheme + "://" + parsed_url.netloc


    def _crawl(self, url):
        response = requests.get(url)
        if response.status_code == 200:
            return response.text, response.status_code
        else:
            print(f"Failed to crawl {url}, status code: {response.status_code}")
            return None, response.status_code

    async def process(self):
        self._process_one(self.url)
        while not self.should_stop() and len(self.urls.get_unfetch_urls()) > 0:
            url = self.urls.get_unfetch_urls().pop()
            self._process_one(url)

    def write_file(self, url, content):
        filepath, filename = self.url_to_filepath(url)

        with open(filepath, 'w') as f:
            f.write(content)

        return filepath, filename
    
    def url_to_filepath(self, url):
        parsed_url = urlparse(url)
        #print(parsed_url)

        # 找出path，根据path建目录
        path_parts = [slugify(part) for part in parsed_url.path.strip('/').split('/')]

        # 保留查询参数和锚点部分
        if parsed_url.query:
            path_parts.append(slugify(parsed_url.query))
        # if parsed_url.fragment:
        #     path_parts.append(slugify(parsed_url.fragment))

        #print(path_parts)
        if not path_parts or path_parts[-1] == "":
            filename = "index.html"
        elif len(path_parts) == 1:
            filename = path_parts[-1] + ".html"
        else:
            # path的最后一部份是文件名，把文件名的后缀加上.html
            filename = path_parts[-1] + ".html"

        directory = os.path.join(self.out_dir, *path_parts[:-1])
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, filename)
        return filepath, filename

    def fetch_url(self, url):
        content = None
        filepath, _ = self.url_to_filepath(url)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
            if content:
                self.urls.add_fetched_url(url)
                print(f"file has been downloaded, successfully read from {filepath}")
                return content
        
        content, status_code = self._crawl(url)
        if content:
            self.pages = self.pages + 1
            if self.urls.add_fetched_url(url, filepath, compute_sha1_from_content(content.encode('utf-8'))):
                self.write_file(url, content)
            print(f"Successfully crawled {url}")
        else:
            print(f"Failed to read or crawl {url}")
            if status_code == 404:
                self.urls.remove_not_found_url(url)
        return content
    
    def _process_one(self, url):
        content = self.fetch_url(url)
        if content is None:
            return
        
        self._find_all_links(content)

        self.urls.save()
        
    def should_stop(self):
        # if self.pages >= self.max_pages:
        #     return True
        return False

    def _find_all_links(self, content):
        # create soap object
        soup = BeautifulSoup(content, 'html.parser')

        # print(soup.find_all('a', attrs={'href': args.pattern}))
        # print(soup.find_all('a', attrs={'href': re.compile('^/')}))

        # find all the anchor tags with "href"
        # attribute starting with "https://"
        for link in soup.find_all('a',
                                attrs={'href': self.pattern}):
            # display the actual urls
            self.urls.add_new_url(link.get('href'))
        
        for link in soup.find_all('a',
                                attrs={'href': re.compile('^/')}):
            href = link.get('href')
            if href is not None:
                url = urljoin(self.base_url, href)
                self.urls.add_new_url(url)

def slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.replace('=', '-')  # Replace equals signs with hyphens
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    text = re.sub(r'[-\s]+', '-', text)
    return text
