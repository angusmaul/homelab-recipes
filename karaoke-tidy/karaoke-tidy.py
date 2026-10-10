#!/usr/bin/env python3
"""File the songs guests download from their phones. Runs nightly on the PiKaraoke host. Dry run unless --execute.

PiKaraoke saves in-app downloads to the ROOT of the library, named after the raw YouTube title
("『MV』毛不易Mao Buyi - 像我這樣的人 官方高畫質 Official…"). Each night this script:

  1. lists root songs that are over an hour old and are NOT queued or playing (PiKaraoke's
     /get_queue and /now_playing), so nothing is moved from under a singer;
  2. POSTs their titles to the n8n workflow "Karaoke tidy" (karaoke-tidy.workflow.json),
     which asks gpt-oss:20b AND qwen3:30b-a3b, and files a song only when they AGREE (see eval/ for the
     measurements). Chinese songs they can't place as Mandopop vs Cantopop, and anything else they
     disagree on, stay in the root for review;
  3. RE-VALIDATES every decision here (folder allow-list, sanitised name, no collision): n8n is
     trusted to classify, never to choose paths;
  4. moves each song with its .ass/.cdg companions, KEEPING the `---<youtube id>` suffix.
     Note: PiKaraoke's scanner detects a move only when the BASENAME is unchanged,
     and we also rename, so it logs delete + add. Play
     history still survives: `plays` keeps youtube_id, which history and rankings are keyed on
     (checked on the original install); only plays.song_id goes NULL, as PiKaraoke's
     schema intends when a file is replaced;
  5. restarts PiKaraoke only if something moved, which runs its library sync;
  6. appends every decision to Karaoke/.logs/tidy.log in the library, dry runs included.

It never deletes anything. It fails safe: if n8n or Ollama is down, nothing moves and the log says so.

  python3 /usr/local/bin/karaoke-tidy.py              # dry run: decisions + plan, nothing moves
  python3 /usr/local/bin/karaoke-tidy.py --execute    # what the timer runs
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

LIB = os.environ.get('KARAOKE_LIBRARY', '').rstrip('/')    # no default: PiKaraoke's download path
LOG = os.path.join(LIB, '.logs', 'tidy.log')
WEBHOOK = os.environ.get('KARAOKE_TIDY_WEBHOOK')      # no default: e.g. https://<your n8n>/webhook/karaoke-tidy
PIKA = (os.environ.get('PIKARAOKE_URL') or '').rstrip('/')   # no default: e.g. http://127.0.0.1:5555 on the PiKaraoke host
FOLDERS = {'K-pop', 'Mandopop', 'Cantopop', 'English', 'Chinese'}
MEDIA = {'.mp4', '.webm', '.mkv', '.mp3', '.zip', '.m4a'}
COMPANIONS = ('.ass', '.cdg', '.ASS', '.CDG')
MIN_AGE_S = 3600
ID_SUFFIX = re.compile(r'(---[A-Za-z0-9_-]{11}|\s\[[A-Za-z0-9_-]{11}\])$')


def get_json(url, timeout=15):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def busy_files():
    """Songs queued or playing right now; never touched."""
    busy = set()
    try:
        busy |= {q.get('file') for q in get_json(PIKA + '/get_queue') if q.get('file')}
        np = get_json(PIKA + '/now_playing')
        for k in ('now_playing_url', 'now_playing_filename', 'now_playing_file'):
            if np.get(k):
                busy.add(np[k])
        np_title = np.get('now_playing')
    except Exception as e:                       # can't see the queue -> refuse to move anything
        raise SystemExit(f'cannot read the PiKaraoke queue ({e}); moving nothing')
    return busy, np_title


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', name or '')
    name = re.sub(r'\s+', ' ', name).strip(' .-')
    return name[:140]


CHINESE_FOLDERS = {'Mandopop', 'Cantopop', 'Chinese'}
CJK = re.compile(r'[一-鿿]')
NATIVE = re.compile(r'[一-鿿가-힣]')          # Chinese or Hangul


def artist_map(exclude=()):
    """{native artist name: established English name}, learned from the library's own filenames.

    Every seeded / filed song is named "<English> <native> - <title>", so the library already knows
    how each artist is spelt. The models do not: on the first night they called 毛不易 "Mao Buyi" twice and
    "Mao Yibei" twice, and a search for "Mao Buyi" missed two of his songs. So an established name
    always wins over the model's; the model only names artists the library has never seen.

    `exclude`: files being refiled do NOT vote. On the first refile the two "Mao Yibei" files voted
    for their own bad name, tied 2-2 with "Mao Buyi", and were judged "already right"."""
    counts = {}
    for folder in ('K-pop', 'Mandopop', 'Cantopop', 'English', 'Chinese'):
        try:
            names = os.listdir(os.path.join(LIB, folder))
        except OSError:
            continue
        for fn in names:
            if f'{folder}/{fn}' in exclude:
                continue
            artist_part = fn.split(' - ', 1)[0]
            for act in artist_part.split(' & '):
                m = re.match(r'^([^一-鿿가-힣]+?)\s+([一-鿿가-힣][^A-Za-z]*)$', act.strip())
                if m:
                    en, native = m.group(1).strip(), m.group(2).strip()
                    counts.setdefault(native, {}).setdefault(en, 0)
                    counts[native][en] += 1
    def rank(native, en):
        # most votes first; on a tie, prefer a name that is NOT just the pinyin of the native name
        squash = re.sub(r'[\s\-]', '', en).lower()
        try:
            import pypinyin
            is_py = squash == ''.join(pypinyin.lazy_pinyin(''.join(CJK.findall(native)))).lower()
        except ImportError:
            is_py = False
        return (counts[native][en], not is_py, en)
    return {native: max(ens, key=lambda en: rank(native, en)) for native, ens in counts.items()}


def build_name(d, folder, amap):
    """House-format name, built HERE rather than trusted from the model:
        Chinese  <Artist EN> <艺人 简体> - <歌名 简体> (<Pin Yin>)
        K-pop    <Artist EN> <가수> - <제목> (<English title>)
        English  n8n's name as given
    For Chinese: the models keep Traditional script and translate titles ('Fuji Mountain Below')
    instead of giving pinyin, which would not match the rest of the library. The English artist name
    comes from the library map first, then the model (asked for OFFICIAL names only, else blank),
    then pinyin. Debian python3-opencc + python3-pypinyin."""
    if folder not in CHINESE_FOLDERS and folder != 'K-pop':
        return d.get('name')
    import opencc
    import pypinyin
    t2s = opencc.OpenCC('t2s.json')
    py = lambda s: ' '.join(w[:1].upper() + w[1:] for w in pypinyin.lazy_pinyin(''.join(CJK.findall(s))))
    chinese = folder in CHINESE_FOLDERS
    an = (d.get('artist_native') or '').strip()
    tn = (d.get('title_native') or '').strip()
    te = (d.get('title_en') or '').strip()
    if chinese:
        an, tn = t2s.convert(an), t2s.convert(tn)
    if not tn:
        return None
    # An established library name ALWAYS wins: consistency is what makes filename search work.
    # (A rule letting an "official" model name beat a pinyin-looking library name was tried and
    # removed the same day: "Mao Buyi" IS the pinyin of 毛不易, so the model's "Mao Yibei" beat it.)
    ae = amap.get(an) or (d.get('artist_en') or '').strip() or (py(an) if chinese else '')
    artist = f'{ae} {an}' if ae and an and ae.lower() != an.lower() and NATIVE.search(an) else (ae or an)
    if chinese:
        rom = py(tn)
    else:
        rom = te if te and NATIVE.search(tn) and te.lower() != tn.lower() else ''
    title = f'{tn} ({rom})' if rom else tn
    return f'{artist} - {title}' if artist else None


def log(lines):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--min-age', type=int, default=MIN_AGE_S, help='seconds a download must have sat (default 3600)')
    ap.add_argument('--refile', nargs='+', metavar='PATH',
                    help='re-run these library files (paths relative to the library, e.g. "Chinese/x---id.mp4") '
                         'through the same classify + name pipeline, instead of scanning the root')
    args = ap.parse_args()
    if not WEBHOOK or not LIB or not PIKA:
        raise SystemExit('set KARAOKE_TIDY_WEBHOOK, KARAOKE_LIBRARY and PIKARAOKE_URL first; there are no defaults')
    mode = 'EXECUTE' if args.execute else 'DRY RUN'
    stamp = datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    out = [f'=== {stamp}  karaoke-tidy  {mode}']

    busy, np_title = busy_files()
    now = time.time()
    songs, skipped = [], []
    candidates = args.refile if args.refile else sorted(os.listdir(LIB))
    for fn in candidates:
        path = os.path.normpath(os.path.join(LIB, fn))
        if not path.startswith(LIB + os.sep):
            skipped.append(f'  SKIP outside the library: {fn}')
            continue
        base, ext = os.path.splitext(os.path.basename(fn))
        if not os.path.isfile(path) or ext.lower() not in MEDIA or os.path.basename(fn).startswith('.'):
            if args.refile:
                skipped.append(f'  SKIP not a song file: {fn}')
            continue
        m = ID_SUFFIX.search(base)
        if not m:
            skipped.append(f'  SKIP no youtube-id suffix: {fn}')
            continue
        if path in busy or (np_title and base.startswith(np_title)):
            skipped.append(f'  SKIP queued/playing: {fn}')
            continue
        if not args.refile and now - os.path.getmtime(path) < args.min_age:
            skipped.append(f'  SKIP younger than {args.min_age // 60} min: {fn}')
            continue
        title = base[:m.start()].strip()
        if args.refile:
            # A refiled song already carries our old English artist name ("Old Name 艺人 - …");
            # the models would just echo it back, so ask about the native name only.
            title = re.sub(r'^[^一-鿿가-힣]*(?=[一-鿿가-힣])', '', title)
        songs.append(dict(file=fn, title=title, suffix=m.group(1), ext=ext))
    out += skipped
    if not songs:
        out.append('  nothing to file')
        log(out)
        print('\n'.join(out))
        return

    try:
        req = urllib.request.Request(WEBHOOK, json.dumps({'songs': [{'file': s['file'], 'title': s['title']} for s in songs]},
                                                          ensure_ascii=False).encode('utf-8'),
                                     {'Content-Type': 'application/json'})
        decisions = json.loads(urllib.request.urlopen(req, timeout=900).read())
        if isinstance(decisions, dict):
            decisions = [decisions]
    except Exception as e:
        out.append(f'  n8n/Ollama unavailable ({e}); nothing moved')
        log(out)
        print('\n'.join(out))
        sys.exit(2)

    by_file = {d.get('file'): d for d in decisions}
    amap = artist_map(exclude={os.path.normpath(p).replace(os.sep, '/') for p in (args.refile or [])})
    moved = 0
    for s in songs:
        d = by_file.get(s['file']) or {}
        why = f"[A {d.get('genre_a')} / B {d.get('genre_b')}] {d.get('reason', 'no decision returned')}"
        folder = d.get('folder')
        name = safe_name(build_name(d, folder, amap))
        if folder not in FOLDERS or not name:
            out.append(f"  REVIEW {s['file']}  {why}")
            continue
        dest_dir = os.path.join(LIB, folder)
        base_new = f"{name}{s['suffix']}"
        dest = os.path.join(dest_dir, base_new + s['ext'])
        if os.path.normpath(dest) == os.path.normpath(os.path.join(LIB, s['file'])):
            out.append(f"  OK already right: {s['file']}")
            continue
        if os.path.normpath(dest).lower() == os.path.normpath(os.path.join(LIB, s['file'])).lower():
            # 🔴 case-only rename on a case-insensitive SMB share: rename() through the CIFS mount
            # silently does nothing (use a fresh smbclient session for these).
            out.append(f"  REVIEW {s['file']}  case-only rename to {base_new}{s['ext']}: do it over a fresh SMB session")
            continue
        if os.path.exists(dest):
            out.append(f"  REVIEW {s['file']}  target exists: {folder}/{base_new}{s['ext']}")
            continue
        companions = [(os.path.join(LIB, s['file'][:-len(s['ext'])] + c), os.path.join(dest_dir, base_new + c))
                      for c in COMPANIONS if os.path.exists(os.path.join(LIB, s['file'][:-len(s['ext'])] + c))]
        out.append(f"  {'MOVE' if args.execute else 'WOULD MOVE'} {s['file']}\n"
                   f"       -> {folder}/{base_new}{s['ext']}" + (f"  (+{len(companions)} companion)" if companions else '')
                   + f"\n       {why}")
        if args.execute:
            os.makedirs(dest_dir, exist_ok=True)
            os.rename(os.path.join(LIB, s['file']), dest)
            for src, dst in companions:
                if not os.path.exists(dst):
                    os.rename(src, dst)
            moved += 1
    if args.execute and moved:
        subprocess.run(['systemctl', 'restart', 'pikaraoke'], check=False)
        out.append(f'  moved {moved}; restarted pikaraoke (its startup sync re-registers them; plays keep their youtube_id)')
    out.append(f"  summary: {len(songs)} considered, {moved if args.execute else sum('WOULD MOVE' in l for l in out)} "
               f"{'moved' if args.execute else 'would move'}, {sum('REVIEW' in l for l in out)} left for review")
    log(out)
    print('\n'.join(out))


if __name__ == '__main__':
    main()
