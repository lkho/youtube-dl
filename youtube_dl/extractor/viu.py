# coding: utf-8
from __future__ import unicode_literals

from datetime import datetime
import json
import random
import re

from .common import InfoExtractor
from ..compat import (
    compat_kwargs,
    compat_str,
)
from ..utils import (
    ExtractorError,
    determine_ext,
    int_or_none,
    smuggle_url,
    unsmuggle_url,
)


class ViuBaseIE(InfoExtractor):
    def _real_initialize(self):
        viu_auth_res = self._request_webpage(
            'https://www.viu.com/api/apps/v2/authenticate', None,
            'Requesting Viu auth', query={
                'acct': 'test',
                'appid': 'viu_desktop',
                'fmt': 'json',
                'iid': 'guest',
                'languageid': 'default',
                'platform': 'desktop',
                'userid': 'guest',
                'useridtype': 'guest',
                'ver': '1.0'
            }, headers=self.geo_verification_headers())
        self._auth_token = viu_auth_res.info()['X-VIU-AUTH']

    def _call_api(self, path, *args, **kwargs):
        headers = self.geo_verification_headers()
        headers.update({
            'X-VIU-AUTH': self._auth_token
        })
        headers.update(kwargs.get('headers', {}))
        kwargs['headers'] = headers
        response = self._download_json(
            'https://www.viu.com/api/' + path, *args,
            **compat_kwargs(kwargs))['response']
        if response.get('status') != 'success':
            raise ExtractorError('%s said: %s' % (
                self.IE_NAME, response['message']), expected=True)
        return response


class ViuIE(ViuBaseIE):
    _VALID_URL = r'(?:viu:|https?://[^/]+\.viu\.com/[a-z]{2}/media/)(?P<id>\d+)'
    _TESTS = [{
        'url': 'https://www.viu.com/en/media/1116705532?containerId=playlist-22168059',
        'info_dict': {
            'id': '1116705532',
            'ext': 'mp4',
            'title': 'Citizen Khan - Ep 1',
            'description': 'md5:d7ea1604f49e5ba79c212c551ce2110e',
        },
        'params': {
            'skip_download': 'm3u8 download',
        },
        'skip': 'Geo-restricted to India',
    }, {
        'url': 'https://www.viu.com/en/media/1130599965',
        'info_dict': {
            'id': '1130599965',
            'ext': 'mp4',
            'title': 'Jealousy Incarnate - Episode 1',
            'description': 'md5:d3d82375cab969415d2720b6894361e9',
        },
        'params': {
            'skip_download': 'm3u8 download',
        },
        'skip': 'Geo-restricted to Indonesia',
    }, {
        'url': 'https://india.viu.com/en/media/1126286865',
        'only_matching': True,
    }]

    def _real_extract(self, url):
        video_id = self._match_id(url)

        video_data = self._call_api(
            'clip/load', video_id, 'Downloading video data', query={
                'appid': 'viu_desktop',
                'fmt': 'json',
                'id': video_id
            })['item'][0]

        title = video_data['title']

        m3u8_url = None
        url_path = video_data.get('urlpathd') or video_data.get('urlpath')
        tdirforwhole = video_data.get('tdirforwhole')
        # #EXT-X-BYTERANGE is not supported by native hls downloader
        # and ffmpeg (#10955)
        # hls_file = video_data.get('hlsfile')
        hls_file = video_data.get('jwhlsfile')
        if url_path and tdirforwhole and hls_file:
            m3u8_url = '%s/%s/%s' % (url_path, tdirforwhole, hls_file)
        else:
            # m3u8_url = re.sub(
            #     r'(/hlsc_)[a-z]+(\d+\.m3u8)',
            #     r'\1whe\2', video_data['href'])
            m3u8_url = video_data['href']
        formats = self._extract_m3u8_formats(m3u8_url, video_id, 'mp4')
        self._sort_formats(formats)

        subtitles = {}
        for key, value in video_data.items():
            mobj = re.match(r'^subtitle_(?P<lang>[^_]+)_(?P<ext>(vtt|srt))', key)
            if not mobj:
                continue
            subtitles.setdefault(mobj.group('lang'), []).append({
                'url': value,
                'ext': mobj.group('ext')
            })

        return {
            'id': video_id,
            'title': title,
            'description': video_data.get('description'),
            'series': video_data.get('moviealbumshowname'),
            'episode': title,
            'episode_number': int_or_none(video_data.get('episodeno')),
            'duration': int_or_none(video_data.get('duration')),
            'formats': formats,
            'subtitles': subtitles,
        }


class ViuPlaylistIE(ViuBaseIE):
    IE_NAME = 'viu:playlist'
    _VALID_URL = r'https?://www\.viu\.com/[^/]+/listing/playlist-(?P<id>\d+)'
    _TEST = {
        'url': 'https://www.viu.com/en/listing/playlist-22461380',
        'info_dict': {
            'id': '22461380',
            'title': 'The Good Wife',
        },
        'playlist_count': 16,
        'skip': 'Geo-restricted to Indonesia',
    }

    def _real_extract(self, url):
        playlist_id = self._match_id(url)
        playlist_data = self._call_api(
            'container/load', playlist_id,
            'Downloading playlist info', query={
                'appid': 'viu_desktop',
                'fmt': 'json',
                'id': 'playlist-' + playlist_id
            })['container']

        entries = []
        for item in playlist_data.get('item', []):
            item_id = item.get('id')
            if not item_id:
                continue
            item_id = compat_str(item_id)
            entries.append(self.url_result(
                'viu:' + item_id, 'Viu', item_id))

        return self.playlist_result(
            entries, playlist_id, playlist_data.get('title'))


class ViuOTTIE(InfoExtractor):
    IE_NAME = 'viu:ott'
    _VALID_URL = r'https?://(?:www\.)?viu\.com/ott/(?P<country_code>[a-z]{2})/(?P<lang_code>[a-z]{2}-[a-z]{2})/vod/(?P<id>\d+)'
    _TESTS = [{
        'url': 'http://www.viu.com/ott/sg/en-us/vod/3421/The%20Prime%20Minister%20and%20I',
        'info_dict': {
            'id': '3421',
            'ext': 'mp4',
            'title': 'A New Beginning',
            'description': 'md5:1e7486a619b6399b25ba6a41c0fe5b2c',
        },
        'params': {
            'skip_download': 'm3u8 download',
            'noplaylist': True,
        },
        'skip': 'Geo-restricted to Singapore',
    }, {
        'url': 'http://www.viu.com/ott/hk/zh-hk/vod/7123/%E5%A4%A7%E4%BA%BA%E5%A5%B3%E5%AD%90',
        'info_dict': {
            'id': '7123',
            'ext': 'mp4',
            'title': '這就是我的生活之道',
            'description': 'md5:4eb0d8b08cf04fcdc6bbbeb16043434f',
        },
        'params': {
            'skip_download': 'm3u8 download',
            'noplaylist': True,
        },
        'skip': 'Geo-restricted to Hong Kong',
    }, {
        'url': 'https://www.viu.com/ott/hk/zh-hk/vod/68776/%E6%99%82%E5%B0%9A%E5%AA%BD%E5%92%AA',
        'playlist_count': 12,
        'info_dict': {
            'id': '3916',
            'title': '時尚媽咪',
        },
        'params': {
            'skip_download': 'm3u8 download',
            'noplaylist': False,
        },
        'skip': 'Geo-restricted to Hong Kong',
    }]

    _AREA_ID = {
        'HK': 1,
        'SG': 2,
        'TH': 4,
        'PH': 5,
    }

    def _real_extract(self, url):
        url, idata = unsmuggle_url(url, {})
        country_code, lang_code, video_id = re.match(self._VALID_URL, url).groups()

        query = {
            'r': 'vod/ajax-detail',
            'platform_flag_label': 'web',
            'product_id': video_id,
        }

        area_id = self._AREA_ID.get(country_code.upper())
        if area_id:
            query['area_id'] = area_id

        product_data = self._download_json(
            'http://www.viu.com/ott/%s/index.php' % country_code, video_id,
            'Downloading video info', query=query)['data']

        video_data = product_data.get('current_product')
        if not video_data:
            raise ExtractorError('This video is not available in your region.', expected=True)

        # return entire series as playlist if not --no-playlist
        if not (self._downloader.params.get('noplaylist') or idata.get('force_noplaylist')):
            series = product_data.get('series', {})
            product = series.get('product')
            if product:
                entries = []
                for entry in sorted(product, key=lambda x: int_or_none(x.get('number', 0))):
                    item_id = entry.get('product_id')
                    if not item_id:
                        continue
                    item_id = compat_str(item_id)
                    entries.append(self.url_result(
                        smuggle_url(
                            'http://www.viu.com/ott/%s/%s/vod/%s/' % (country_code, lang_code, item_id),
                            {'force_noplaylist': True}),  # prevent infinite recursion
                        'ViuOTT',
                        item_id,
                        entry.get('synopsis', '').strip()))

                return self.playlist_result(
                    entries,
                    video_data.get('series_id'),
                    series.get('name'),
                    series.get('description'))
        # else fall-through

        if self._downloader.params.get('noplaylist'):
            self.to_screen(
                'Downloading only video %s in series %s because of --no-playlist' %
                (video_id, video_data.get('series_id')))

        stream_data = self._download_json(
            'https://d1k2us671qcoau.cloudfront.net/distribute_web_%s.php' % country_code,
            video_id, 'Downloading stream info', query={
                'ccs_product_id': video_data['ccs_product_id'],
            }, headers={
                'Referer': url,
                'Origin': re.search(r'https?://[^/]+', url).group(0),
            })['data']['stream']

        stream_sizes = stream_data.get('size', {})
        formats = []
        for vid_format, stream_url in stream_data.get('url', {}).items():
            height = int_or_none(self._search_regex(
                r's(\d+)p', vid_format, 'height', default=None))
            formats.append({
                'format_id': vid_format,
                'url': stream_url,
                'height': height,
                'ext': 'mp4',
                'filesize': int_or_none(stream_sizes.get(vid_format))
            })
        self._sort_formats(formats)

        subtitles = {}
        for sub in video_data.get('subtitle', []):
            sub_url = sub.get('url')
            if not sub_url:
                continue
            subtitles.setdefault(sub.get('name'), []).append({
                'url': sub_url,
                'ext': 'srt',
            })

        title = video_data['synopsis'].strip()

        return {
            'id': video_id,
            'title': title,
            'description': video_data.get('description'),
            'series': product_data.get('series', {}).get('name'),
            'episode': title,
            'episode_number': int_or_none(video_data.get('number')),
            'duration': int_or_none(stream_data.get('duration')),
            'thumbnail': video_data.get('cover_image_url'),
            'formats': formats,
            'subtitles': subtitles,
        }


class ViuTVIE(InfoExtractor):
    IE_NAME = 'viu:tv'
    _VALID_URL = r'https?://(?:www\.)?viu\.tv/encore/(?P<program_slug>[^/]+)(?:/(?P<episode_slug>[^/?]+))?'
    _TESTS = [{
        'url': 'https://viu.tv/encore/leap-day/leap-daye2si-hung-long-yan',
        'info_dict': {
            'id': '202002281024764',
            'ext': 'mp4',
            'title': '"時空浪人',
        },
        'params': {
            'skip_download': 'm3u8 download',
        },
        'skip': 'Geo-restricted to Hong Kong',
    }]

    _SUBTITLE_LANG = {
        'chinese': 'TRD',
        'english': 'GBR',
        'german': 'DEU',
        'spanish': 'ESP',
        'french': 'FRA',
        'italian': 'ITA',
        'japanese': 'JAP',
    }

    def _real_extract(self, url):
        program_slug, episode_slug = re.match(self._VALID_URL, url).groups()

        product_data = self._download_json(
            'https://api.viu.tv/production/programmes/%s' % program_slug,
            program_slug, 'Downloading program info')['programme']

        episodes = product_data['episodes']

        program_title = product_data.get('programmeMeta', {}).get('seriesTitle') or \
            product_data.get('title')

        # return entire series as playlist if no episode_slug
        if episode_slug is None:
            entries = []
            for entry in sorted(
                    episodes,
                    key=lambda x: int_or_none(x.get('episodeNum', 0))):
                item_slug = entry.get('slug')
                item_id = entry.get('productId')
                if not item_id:
                    continue
                item_slug = compat_str(item_slug)
                video_meta = entry.get('videoMeta', {})
                title = video_meta.get('title') or \
                    entry.get('episodeNameU3') or \
                    entry.get('ga_title')

                entries.append(self.url_result(
                    'http://viu.tv/encore/%s/%s' % (program_slug, item_slug),
                    'ViuTV', item_id, title))

            return self.playlist_result(
                entries,
                product_data.get('programmeId'),
                program_title,
                product_data.get('synopsis'))
        # else fall-through

        ep_data = next((x for x in episodes if x.get('slug') == episode_slug), {})
        product_id = ep_data.get('productId')

        if not product_id:
            raise ExtractorError('Video %s does not exist' % program_slug, expected=True)

        random_cookie = '%018x' % random.randrange(16 ** 18)
        payload = {
            'PIN': 'password',
            'callerReferenceNo': datetime.now().strftime('%Y%m%d%H%M%S'),
            'contentId': product_id,
            'contentType': 'Vod',
            'cookie': random_cookie,
            'deviceId': random_cookie,
            'deviceType': 'ANDROID_PHONE',
            'format': 'HLS',
            'mode': 'prod',
            'productId': product_id,
        }

        get_vod_data = self._download_json(
            'https://api.viu.now.com/p8/3/getVodURL', product_id,
            note='Downloading stream info', data=json.dumps(payload).encode())

        manifest_url = next(iter(get_vod_data.get('asset', [])), None)
        drm = get_vod_data.get('drmToken', None)

        if not manifest_url:
            raise ExtractorError(
                'Cannot get stream info', expected=True, video_id=product_id)

        formats = []

        ext = determine_ext(manifest_url)
        if ext == 'm3u8':
            formats = self._extract_m3u8_formats(
                    manifest_url, product_id, 'mp4', entry_protocol='m3u8_native',
                    fatal=False)
        elif ext == 'mpd':
            formats = self._extract_mpd_formats(manifest_url, product_id, fatal=False)

        if not formats and drm:
            raise ExtractorError('This video is DRM protected.', expected=True)

        subtitles = {}
        for lang in (ep_data.get('productSubtitle', '').split(',')):
            key = self._SUBTITLE_LANG.get(lang.lower())
            if not key:
                continue
            subtitles.setdefault(lang, []).append({
                'url': 'https://static.viu.tv/subtitle/{0}/{0}-{1}.srt'.format(product_id, key),
                'ext': 'srt',
            })

        video_meta = ep_data.get('videoMeta', {})

        title = video_meta.get('title') or \
            ep_data.get('episodeNameU3') or \
            ep_data.get('ga_title')

        tags = video_meta.get('tags')
        try:
            if isinstance(tags, list):
                tags = [x.get('name') for x in tags if x.get('name')]
            else:
                tags = None
        except TypeError:
            tags = None

        self._sort_formats(formats)

        return {
            'id': product_id,
            'title': title,
            'formats': formats,
            'description': ep_data.get('videoMeta', {}).get('program_synopsis'),
            'series': program_title,
            'episode': title,
            'episode_number': int_or_none(ep_data.get('episodeNum')),
            'duration': int_or_none(ep_data.get('totalDurationSec')),
            'thumbnail': ep_data.get('avatar'),
            'programme_slug': product_data.get('slug'),
            'slug': ep_data.get('slug'),
            'tags': tags,
            'subtitles': subtitles,
        }
