import os
import sys
import argparse

from downloadStream import startDownload

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--url")
args = parser.parse_args()

if len(sys.argv) == 1:
    print("Usage: python3 main.py --url <clip/video_url_here>")
    sys.exit()

isVid = False

url = args.url

if url.rpartition('/')[-3].rpartition('/')[-1] == 'videos':
    isVid = True

# test clip: https://www.twitch.tv/woowakgood/clip/LachrymoseResilientBibimbapWutFace-5sW0CQ_ViPN6OtM_
# test video: https://www.twitch.tv/videos/996697442?filter=archives&sort=time
startDownload(url.rpartition('/')[-1].split('?')[0], isVid)