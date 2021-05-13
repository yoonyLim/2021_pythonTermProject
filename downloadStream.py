import os
import requests
import subprocess

from twitchConfig import CLIENT_ID, CLIENT_SECRET, PARSE_SECONDS
from analyzeChat import analyzeChat
from datetime import timedelta

def startDownload(det, isVid):
    access_token = requests.post("https://id.twitch.tv/oauth2/token?client_id={0}&client_secret={1}&grant_type=client_credentials".format(CLIENT_ID, CLIENT_SECRET)).json()['access_token']

    if isVid:
        video_info = requests.get("https://api.twitch.tv/helix/videos?id=" + det, headers={"Client-ID": CLIENT_ID, "Authorization": 'Bearer ' + access_token}).json()['data'][0]
        title = video_info['title']
        m3u_url = 'https://vod-secure.twitch.tv/{}/720p60/index-dvr.m3u8'.format(video_info['thumbnail_url'].split('/')[5])
        duration = video_info['duration']
        timestamps = analyzeChat(det, duration)
        downloadFile(title, m3u_url, timestamps)
    else:
        clip_info = requests.get("https://api.twitch.tv/helix/clips?id=" + det, headers={"Client-ID": CLIENT_ID, "Authorization": 'Bearer ' + access_token}).json()['data'][0]
        title = clip_info['title']
        mp4_url = clip_info['thumbnail_url'].split("-preview",1)[0] + ".mp4"
        duration = clip_info['duration']
        timestamps = analyzeChat(clip_info['video_id'], duration)
        downloadFile(title, mp4_url, timestamps)

def downloadFile(title, url, timestamps):
    if timestamps == 'NA':
        output_path = os.path.join(os.path.abspath(__file__).rpartition('/')[0], title + '.mp4')

        command = [
            "ffmpeg",
            # filter from the given url
            "-i", url,
            # frame rate
            #"-crf", "15",
            # resolution (lower resolution means longer time to process the original higher resolution video)
            #"-filter:v", "scale=640:480",
            # save file to
            #"-c:a", "copy",
            "-c", "copy",
            output_path,
            "-stats",
            "-loglevel", "warning",
        ]

        try:
            subprocess.run(command)
        except Exception as e:
            print("An exception occurred: ", e)
    else:
        output_path = os.path.join(os.path.abspath(__file__).rpartition('/')[0], title)
        
        for stamp in timestamps:
            trial = 1

            start = timedelta(seconds = stamp)
            end = start + timedelta(seconds = PARSE_SECONDS)

            command = [
                "ffmpeg",
                # set start time
                "-ss", str(start.total_seconds()).split('.')[0], 
                # filter from the given url
                "-i", url,
                # frame rate
                "-crf", "30",
                # set how long is end time after start time
                "-to", str(PARSE_SECONDS),
                # save file to
                "-c", "copy",
                output_path + '(from ' + str(start).split('.')[0].replace(':', '-') + ' to ' + str(end).split('.')[0].replace(':', '-') + ')'  + '.mp4',
                "-stats",
                "-loglevel", "warning",
            ]

            print('\n', trial, 'out of', str(len(timestamps)), 'clips processing...\n')

            try:
                subprocess.run(command)
                trial += 1
            except Exception as e:
                print("An exception occurred: ", e)
                print("\nHTTP error 403 means 'object not found' error here.\nThis can be due to Twitch's internal server error.\nPLEASE TRY AGAIN LATER OR DIFFERENT URL!")
'''
def showProgress(count, block_size, total_size):
    #try:
        #urllib.request.urlretrieve(url, output_path, reporthook=showProgress)
    percent = int(count * block_size * 100 / total_size)
    sys.stdout.write("\r...%d%%" % percent)
    sys.stdout.flush()
'''