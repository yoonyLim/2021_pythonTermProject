import requests
import m3u8
import re
import os
import shutil
import tempfile
import subprocess

from twitchConfig import CLIENT_ID_OTHR
from os import path
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from datetime import datetime
from collections import OrderedDict

def startVideoDownload(video_id):
    video = get_video(video_id)
    print('\nvideo: ', video, '\n')

    print("\nFetching access token...\n")
    access_token = get_access_token(video_id)

    print("\nFetching playlists...\n")
    playlists_m3u8 = get_playlists(video_id, access_token)
    playlists = list(_parse_playlists(playlists_m3u8))
    playlist_uri = _select_playlist_interactive(playlists)

    print("\nFetching playlist...\n")
    response = requests.get(playlist_uri)
    response.raise_for_status()
    playlist = m3u8.loads(response.text)

    base_uri = re.sub("/[^/]+$", "/", playlist_uri)
    target_dir = _crete_temp_dir(base_uri)
    vod_paths = _get_vod_paths(playlist, None, None)

    # Save playlists for debugging purposes
    with open(path.join(target_dir, "playlists.m3u8"), "w") as f:
        f.write(playlists_m3u8)
    with open(path.join(target_dir, "playlist.m3u8"), "w") as f:
        f.write(response.text)

    print("\nDownloading {} VODs using {} workers to {}".format(
        len(vod_paths), 20, target_dir))
    path_map = download_files(base_uri, target_dir, vod_paths, 20)

    # Make a modified playlist which references downloaded VODs
    # Keep only the downloaded segments and skip the rest
    org_segments = playlist.segments.copy()
    playlist.segments.clear()
    for segment in org_segments:
        if segment.uri in path_map:
            segment.uri = path_map[segment.uri]
            playlist.segments.append(segment)

    playlist_path = path.join(target_dir, "playlist_downloaded.m3u8")
    playlist.dump(playlist_path)

    print("\n\nJoining files...")
    target = video['title'] + '.mp4'
    _join_vods(playlist_path, target, False)

    print("\n<dim>Deleting temporary files...</dim>")
    shutil.rmtree(target_dir)

    print("\nDownloaded: <green>{}</green>".format(target))

VIDEO_FIELDS = """
    id
    title
    publishedAt
    broadcastType
    lengthSeconds
    game {
        name
    }
    creator {
        login
        displayName
    }
"""

def get_video(video_id):
    query = """
    {{
        video(id: "{video_id}") {{
            {fields}
        }}
    }}
    """

    query = query.format(video_id=video_id, fields=VIDEO_FIELDS)

    response = gql_query(query)
    return response["data"]["video"]

def gql_query(query):
    url = "https://gql.twitch.tv/gql"
    response = authenticated_post(url, json={"query": query}).json()

    if "errors" in response:
        raise GQLError(response["errors"])

    return response

def get_access_token(video_id):
    query = """
    {{
        videoPlaybackAccessToken(
            id: {video_id},
            params: {{
                platform: "web",
                playerBackend: "mediaplayer",
                playerType: "site"
            }}
        ) {{
            signature
            value
        }}
    }}
    """

    query = query.format(video_id=video_id)

    response = gql_query(query)
    return response["data"]["videoPlaybackAccessToken"]

def get_playlists(video_id, access_token):
    """
    For a given video return a playlist which contains possible video qualities.
    """
    url = "http://usher.twitch.tv/vod/{}".format(video_id)

    response = requests.get(url, params={
        "nauth": access_token['value'],
        "nauthsig": access_token['signature'],
        "allow_source": "true",
        "player": "twitchweb",
    })
    response.raise_for_status()
    
    return response.content.decode('utf-8')

def authenticated_post(url, data=None, json=None, headers={}):
    headers['Client-ID'] = CLIENT_ID_OTHR
    response = requests.post(url, data=data, json=json, headers=headers)

    response.raise_for_status()

    return response

def raise_for_status(self):
    """Raises :class:`HTTPError`, if one occurred."""

    http_error_msg = ''
    if isinstance(self.reason, bytes):
        # We attempt to decode utf-8 first because some servers
        # choose to localize their reason strings. If the string
        # isn't utf-8, we fall back to iso-8859-1 for all other
        # encodings. (See PR #3538)
        try:
            reason = self.reason.decode('utf-8')
        except UnicodeDecodeError:
            reason = self.reason.decode('iso-8859-1')
    else:
        reason = self.reason

    if 400 <= self.status_code < 500:
        http_error_msg = u'%s Client Error: %s for url: %s' % (self.status_code, reason, self.url)

    elif 500 <= self.status_code < 600:
        http_error_msg = u'%s Server Error: %s for url: %s' % (self.status_code, reason, self.url)

    if http_error_msg:
        raise HTTPError(http_error_msg, response=self)

def _parse_playlists(playlists_m3u8):
    playlists = m3u8.loads(playlists_m3u8)

    for p in playlists.playlists:
        name = p.media[0].name if p.media else ""
        resolution = "x".join(str(r) for r in p.stream_info.resolution)
        yield name, resolution, p.uri

def _select_playlist_interactive(playlists):
    print("\nAvailable qualities:")
    for n, (name, resolution, uri) in enumerate(playlists):
        print("{}) {} [{}]".format(n + 1, name, resolution))

    no = read_int("Choose quality", min=1, max=len(playlists) + 1, default=1)
    _, _, uri = playlists[no - 1]
    return uri

def read_int(msg, min, max, default):
    msg = msg + " [default {}]: ".format(default)

    while True:
        try:
            val = input(msg)
            if not val:
                return default
            if min <= int(val) <= max:
                return int(val)
        except ValueError:
            pass

def _crete_temp_dir(base_uri):
    """Create a temp dir to store downloads if it doesn't exist."""
    path = urlparse(base_uri).path.lstrip("/")
    temp_dir = Path(tempfile.gettempdir(), "twitch-dl", path)
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir

def _get_vod_paths(playlist, start, end):
    """Extract unique VOD paths for download from playlist."""
    files = []
    vod_start = 0
    for segment in playlist.segments:
        vod_end = vod_start + segment.duration

        # `vod_end > start` is used here becuase it's better to download a bit
        # more than a bit less, similar for the end condition
        start_condition = not start or vod_end > start
        end_condition = not end or vod_start < end

        if start_condition and end_condition and segment.uri not in files:
            files.append(segment.uri)

        vod_start = vod_end

    return files

def download_files(base_url, target_dir, vod_paths, max_workers):
    """
    Downloads a list of VODs defined by a common `base_url` and a list of
    `vod_paths`, returning a dict which maps the paths to the downloaded files.
    """
    urls = [base_url + path for path in vod_paths]
    targets = [os.path.join(target_dir, "{:05d}.ts".format(k)) for k, _ in enumerate(vod_paths)]
    partials = (partial(download_file, url, path) for url, path in zip(urls, targets))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fn) for fn in partials]
        _print_progress(futures)

    return OrderedDict(zip(vod_paths, targets))

def _print_progress(futures):
    downloaded_count = 0
    downloaded_size = 0
    max_msg_size = 0
    start_time = datetime.now()
    total_count = len(futures)

    for future in as_completed(futures):
        size = future.result()
        downloaded_count += 1
        downloaded_size += size

        percentage = 100 * downloaded_count // total_count
        est_total_size = int(total_count * downloaded_size / downloaded_count)
        duration = (datetime.now() - start_time).seconds
        speed = downloaded_size // duration if duration else 0
        remaining = (total_count - downloaded_count) * duration / downloaded_count

        msg = " ".join([
            "Downloaded VOD {}/{}".format(downloaded_count, total_count),
            "({}%)".format(percentage),
            "<cyan>{}</cyan>".format(format_size(downloaded_size)),
            "of <cyan>~{}</cyan>".format(format_size(est_total_size)),
            "at <cyan>{}/s</cyan>".format(format_size(speed)) if speed > 0 else "",
            "remaining <cyan>~{}</cyan>".format(format_duration(remaining)) if speed > 0 else "",
        ])

        max_msg_size = max(len(msg), max_msg_size)
        print("\r" + msg.ljust(max_msg_size), end="")

def _format_size(value, digits, unit):
    if digits > 0:
        return "{{:.{}f}}{}".format(digits, unit).format(value)
    else:
        return "{{:d}}{}".format(unit).format(value)


def format_size(bytes_, digits=1):
    if bytes_ < 1024:
        return _format_size(bytes_, digits, "B")

    kilo = bytes_ / 1024
    if kilo < 1024:
        return _format_size(kilo, digits, "kB")

    mega = kilo / 1024
    if mega < 1024:
        return _format_size(mega, digits, "MB")

    return _format_size(mega / 1024, digits, "GB")

def format_duration(total_seconds):
    total_seconds = int(total_seconds)
    hours = total_seconds // 3600
    remainder = total_seconds % 3600
    minutes = remainder // 60
    seconds = total_seconds % 60

    if hours:
        return "{} h {} min".format(hours, minutes)

    if minutes:
        return "{} min {} sec".format(minutes, seconds)

    return "{} sec".format(seconds)

def download_file(url, path, retries=5):
    if os.path.exists(path):
        return os.path.getsize(path)

    for _ in range(retries):
        try:
            return _download(url, path)
        except RequestException:
            pass

    raise DownloadFailed(":(")

def _download(url, path):
    tmp_path = path + ".tmp"
    response = requests.get(url, stream=True, timeout=5)
    size = 0
    with open(tmp_path, 'wb') as target:
        for chunk in response.iter_content(chunk_size=1024):
            target.write(chunk)
            size += len(chunk)

    os.rename(tmp_path, path)
    return size

def _join_vods(playlist_path, target, overwrite):
    command = [
        "ffmpeg",
        "-i", playlist_path,
        "-c", "copy",
        target,
        "-stats",
        "-loglevel", "warning",
    ]

    if overwrite:
        command.append("-y")

    print("<dim>{}</dim>".format(" ".join(command)))
    result = subprocess.run(command)
    if result.returncode != 0:
        raise ConsoleError("Joining files failed")