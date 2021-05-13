import requests
import sys

from datetime import datetime, timedelta
from twitchConfig import CLIENT_ID, PARSE_SECONDS

def parseChat(video_id, duration):
    response = requests.get("https://api.twitch.tv/v5/videos/{0}/comments?content_offset_seconds=0".format(video_id), headers={"Client-ID": CLIENT_ID}).json()

    # print(response['comments'][0])

    # set time to check to parse every 50 seconds
    timeCheck = timedelta(seconds = response['comments'][0]['content_offset_seconds'] + PARSE_SECONDS)

    result = []
    tmp = []
    numChat = 0

    while "_next" in response:
        cursor = response['_next']

        tmp.extend(list(map(processBody, response['comments'])))

        # check if the end chat is after 40 seconds of the starting chat
        if timedelta(seconds = tmp[len(tmp) - 1][0]) >= timeCheck:
            # print('\nthis is timeCheck: ', timeCheck)
            # print('\nthis is exceeded timestamp: ', timedelta(seconds = tmp[len(tmp) - 1][0]), '\n')
            idx, timeCheck = resetTimeCheck(tmp, 0, len(tmp) - 1, timeCheck)
            timeCheck += timedelta(seconds = PARSE_SECONDS)
            result.append(tmp[:idx])
            tmp = tmp[idx:]
            # print('\ntmp after resetting dateCheck: ', tmp, '\n')

        numChat += len(list(response['comments']))
        sys.stdout.write('\r%d chats fetched: %.2f%% done' % (numChat, calcPercent(tmp, formatTime(duration))))
        sys.stdout.flush()
        response = requests.get("https://api.twitch.tv/v5/videos/{0}/comments?cursor={1}".format(video_id, cursor), headers={"Client-ID": CLIENT_ID}).json()
    
    # append the rest of remaining tmp log
    result.append(tmp[:])

    return result

def processBody(b):
    return [b['content_offset_seconds'], b['message']['body']]

def calcPercent(L, duration):
    return round((timedelta(seconds = L[0][0]).total_seconds() / duration.total_seconds() * 100), 2)

def resetTimeCheck(lst, earlier, later, time):
    earlier = earlier
    later = later
    middle = (earlier + later) // 2

    try:
        e = timedelta(seconds = lst[earlier][0])
        m = timedelta(seconds = lst[middle][0])
        l = timedelta(seconds = lst[later][0])
    except Exception as e:
        print('\nAn error occured:', e, '\n', lst[earlier], lst[middle], lst[later], '\n')

    '''
    print('\ntimeCheck: ', time, '\n')
    print('\nthis is earlier idx: ', earlier)
    print('this is resetTimeCheck e: ', e, '\n')
    print('\nthis is middle idx: ', middle)
    print('this is resetTimeCheck m: ', m, '\n')
    print('\nthis is later idx: ', later)
    print('this is resetTimeCheck l: ', l, '\n')

    print('\ne and time: ', e >= time, '\n')
    print('\nm and time: ', m >= time, '\n')
    print('\nl and time: ', l >= time, '\n')
    '''

    if e >= time:
        return earlier, e
    elif m == time:
        return middle, m
    elif m > time:
        return resetTimeCheck(lst, earlier, middle - 1, time)
    elif m < time:
        return resetTimeCheck(lst, middle + 1, later, time)

def analyzeChat(video_id, duration):
    chatLog = parseChat(video_id, duration)

    numChatL = []
    numLOLL = []

    mostChatIdxL = []
    mostLOLIdxL = []

    timestamps = []

    for i in range(0, len(chatLog)):
        # print('\nthis is', i + 1, 'th log: ', chatLog[i], '\n')
        numChatL.append(len(chatLog[i]))
        numLOLL.append(countLOL(chatLog[i]))
    
    # make sure that video is at least (PARSE_SECONDS * 10) seconds long
    if len(chatLog) > 10:
        for j in range(0, 5):
            mostChatIdxL.append(numChatL.index(max(numChatL)))
            mostLOLIdxL.append(numLOLL.index(max(numLOLL)))
            numChatL[numChatL.index(max(numChatL))] = 0
            numLOLL[numLOLL.index(max(numLOLL))] = 0
    else:
        print('video/clip is TOO SHORT or has NO CHAT')
        return 'NA'

    for idx in list(set(mostChatIdxL) | set(mostLOLIdxL)):
        # store created_at data of the first occurrence with its delayed time subtracted
        timestamps.append(chatLog[idx][0][0])

    for stamp in timestamps:
        if formatTime(duration) < timedelta(seconds = stamp):
            timestamps.remove(stamp)

    print('\nTimestamps: ', timestamps, '\n')
    
    return timestamps

def countLOL(L):
    numLOL = 0
    for i in L:
        numLOL += i[1].count('ㅋ')
        
    return numLOL

def formatTime(time):
    if time.find('h') != -1:
        return datetime.strptime(time, '%Hh%Mm%Ss') - datetime(1900, 1, 1)
    elif time.find('m') != -1:
        return datetime.strptime(time, '%Mm%Ss') - datetime(1900, 1, 1)
    else:
        return datetime.strptime(time, '%Ss') - datetime(1900, 1, 1)