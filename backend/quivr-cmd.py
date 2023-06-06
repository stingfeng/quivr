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

commons = common_dependencies()


credentials = {
    "email": os.environ.get("USER_EMAIL")
}

async def get_answer(chat_message: ChatMessage):
    msg = await chat_endpoint(commons, chat_message, credentials)
    print(msg)

async def list_files():
    msg = await explore_endpoint(commons, credentials)
    print(msg)

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
        for file_type in accept:
            accepted_files.extend(glob.glob('**/'+file_type, recursive=True))
    else:
        accepted_files.extend(glob.glob('**/*', recursive=True))

    if ignore:
        for file_type in ignore:
            ignored_files = glob.glob('**/'+file_type, recursive=True)
            accepted_files = [f for f in accepted_files if f not in ignored_files]

    accepted_files = [f for f in accepted_files if not os.path.isdir(f)]
    return accepted_files

async def push_files(directory, accept=None, ignore=None):
    files = await collect_files(directory, accept, ignore)
    if not files:
        return
    for filename in files:
        await push_file(filename)

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
    parser.add_argument('command', choices=['run', 'ls', 'rm', 'pull', 'push', 'push-dir', 'test', 'combine'], help='The command to execute.')
    parser.add_argument('--file', metavar='input file name', help='The file to operate on.')
    parser.add_argument('--dir', metavar='dirname', help='The directory to operate on.')
    parser.add_argument('--out', metavar='output file name', help='The file to output.')
    parser.add_argument('--allow', metavar='wildcard', help='accepted file wildcard, e.g. *.md')

    # 解析命令行参数
    args = parser.parse_args()

    # 根据命令行参数来选择运行哪个函数
    if args.command == 'run':
        chat_message = ChatMessage(
            question='',
            history = [],
            max_tokens = 500,
        )
        while True:
            chat_message.question = input("Enter your question here: ")
            if chat_message.question == 'exit':
                break;
            asyncio.run(get_answer(chat_message))
    elif args.command == 'ls':
        asyncio.run(list_files())
    elif args.command == 'rm':
        if args.file is None:
            print("Please provide a file name with the --file option.")
        else:
            asyncio.run(remove_file(args.file))
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
