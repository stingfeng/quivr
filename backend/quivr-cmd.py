import os
import asyncio
import shutil
import argparse
import glob
from tempfile import SpooledTemporaryFile
from models.chats import (ChatMessage)
from utils.vectors import (common_dependencies)
from fastapi import UploadFile
from main import chat_endpoint, explore_endpoint, delete_endpoint, download_endpoint, upload_file
from mock_processors import mock_filter_file
from crawl.crawler import CrawlWebsite
from utils.file import compute_sha1_from_file
import json

commons = common_dependencies()


credentials = {
    "email": os.environ.get("USER_EMAIL")
}

async def crawl_website(url, out_dir):
    crawler = CrawlWebsite(url=url)
    await crawler.process(out_dir=out_dir)

async def get_answer(chat_message: ChatMessage):
    msg = await chat_endpoint(commons, chat_message, credentials)
    print(msg)

async def list_files():
    msg = await explore_endpoint(commons, credentials)
    print(msg)

async def remove_files_by_tag(tag):
    email = credentials['email']
    # Cascade delete the summary from the database first, because it has a foreign key constraint
    commons['supabase'].table("summaries").delete().match(
        {"metadata->>tag": tag}).execute()
    commons['supabase'].table("vectors").delete().match(
        {"metadata->>tag": tag, "user_id": email}).execute()
    print({"message": f"files with {tag} of user {email} have been all deleted."})

async def remove_file(filename):
    msg = await delete_endpoint(commons, filename, credentials)
    print(msg)

async def download_file(filename):
    msg = await download_endpoint(commons, filename, credentials)
    print(msg)

async def push_file(file_path, analyze_only: bool = False):
    # Create a SpooledTemporaryFile from the file_path
    spooled_file = SpooledTemporaryFile()
    file_name = os.path.basename(file_path)

    with open(file_path, 'rb') as f:
        shutil.copyfileobj(f, spooled_file)

    # Pass the SpooledTemporaryFile to UploadFile
    file = UploadFile(file=spooled_file, filename=file_name)
    if not analyze_only:
        msg = await upload_file(commons, file, True, credentials)
        print(msg)
        return msg
    else:
        msg = await mock_filter_file(file)
        print('metadata={}'.format(msg['metadata']))
        print('\n\n====================\n\n')
        for doc in msg['documents']:
            print(f'doc={doc.page_content}')
            print('\n\n====================\n\n')

async def collect_files(directory, accept=None, ignore=None):
    os.chdir(directory)

    accepted_files = []
    if accept:
        accepted_files.extend(glob.glob('**/'+accept, recursive=True))
    else:
        accepted_files.extend(glob.glob('**/*', recursive=True))

    if ignore:
        ignored_files = glob.glob('**/'+ignore, recursive=True)
        accepted_files = [f for f in accepted_files if f not in ignored_files]

    accepted_files = [f for f in accepted_files if not os.path.isdir(f)]
    return accepted_files

class FileSha1Cache:
    filepath : str
    uploaded_file_sha1s : set = set()
    def __init__(self, filepath):
        self.filepath = filepath
    def add(self, file_sha1):
        self.uploaded_file_sha1s.add(file_sha1)
    def file_already_exists(self, file_sha1):
        return file_sha1 in self.uploaded_file_sha1s
    def save(self):
        with open(self.filepath, "w") as f:
            json.dump(list(self.uploaded_file_sha1s), f)
    def load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as f:
                self.uploaded_file_sha1s = set(json.load(f))

def lookup_file(cached_sha1s : FileSha1Cache, file_sha1):
    if cached_sha1s.file_already_exists(file_sha1):
        return True
    response = commons['supabase'].table("vectors").select("id").filter("metadata->>file_sha1", "eq", file_sha1) \
        .filter("user_id", "eq", credentials.get('email', 'none')).execute()
    if response and len(response.data) > 0:
        cached_sha1s.add(file_sha1)
        cached_sha1s.save()
        return True
    return False

async def push_files(directory, accept=None, ignore=None):
    files = await collect_files(directory, accept, ignore)
    if not files:
        return
    fsc = FileSha1Cache("uploaded_file_sha1s.json")
    fsc.load()
    for file_path in files:
        file_sha1 = compute_sha1_from_file(file_path)
        if lookup_file(fsc, file_sha1):
            print(f'file {file_path} already exists.')
        else:
            msg = await push_file(file_path)
            if msg and msg.get("type", '') == "success":
                fsc.add(file_sha1)
                fsc.save()


async def combine_files(directory, outfile, accept=None, ignore=None):
    files = await collect_files(directory, accept, ignore)
    if not files:
        return

    with open(outfile, 'w') as ofile:
        for filename in files:
            with open(filename, 'r') as ifile:
                ofile.write(ifile.read())

if __name__ == '__main__':
    # 创建解析器
    parser = argparse.ArgumentParser()

    # 添加命令行参数
    parser.add_argument('command', choices=['run', 'ls', 'rm', 'pull', 'push', 'push-dir', 'test', 'combine', 'crawl'], help='The command to execute.')
    parser.add_argument('--file', metavar='input file name', help='The file to operate on.')
    parser.add_argument('--dir', metavar='dirname', help='The directory to operate on.')
    parser.add_argument('--out', metavar='output file name', help='The file to output.')
    parser.add_argument('--allow', metavar='wildcard', help='accepted file wildcard, e.g. *.md')
    parser.add_argument('--tag', metavar='tag of files', help='tag you pushed files with')
    parser.add_argument('--url', metavar='a website to crawl', help='The website to crawl.')

    # 解析命令行参数
    args = parser.parse_args()

    # 根据命令行参数来选择运行哪个函数
    if args.command == 'run':
        chat_message = ChatMessage(
            model = "gpt-3.5-turbo-0613",
            question='',
            history = [],
            max_tokens = 1000,
            use_summarization = False,
        )
        while True:
            chat_message.question = input("Enter your question here: ")
            if chat_message.question == 'exit':
                break
            asyncio.run(get_answer(chat_message))
    elif args.command == 'ls':
        asyncio.run(list_files())
    elif args.command == 'rm':
        if args.file is not None:
            asyncio.run(remove_file(args.file))
        elif args.tag is not None:
            asyncio.run(remove_files_by_tag(args.tag))
        else:
            print("Please provide a file name with the --file option, or a tag with the --tag option.")
    elif args.command == 'pull':
        if args.file is None:
            print("Please provide a file name with the --file option.")
        else:
            asyncio.run(download_file(args.file))
    elif args.command == 'push':
        if args.file is None and args.dir is None:
            print("Please provide a file name with the --file option, or a directory with the --dir option.")
        else:
            asyncio.run(push_file(args.file, args.dir))
    elif args.command == 'test':
        if args.file is None:
            print("Please provide a file name with the --file option.")
        else:
            asyncio.run(push_file(args.file, True))
    elif args.command == 'push-dir':
        if args.dir is None:
            print("Please provide a directory to collect files.")
        if args.allow is None:
            print("Please provide a wildcard to collect.")
        else:
            asyncio.run(push_files(args.dir, args.allow))
    elif args.command == 'combine':
        if args.dir is None:
            print("Please provide a directory to collect files.")
        if args.out is None:
            print("Please provide a output file to write combined files.")
        if args.allow is None:
            print("Please provide a wildcard to collect.")
        else:
            asyncio.run(combine_files(args.dir, args.out, args.allow))
    elif args.command == 'crawl':
        if args.url is None:
            print("Please provide a url to crawl files.")
        else:
            asyncio.run(crawl_website(args.url, args.dir))
