# File phone-added karaoke songs with two local models that have to agree

A nightly job for a [PiKaraoke](https://github.com/vicwomg/pikaraoke) library. Songs that guests
download from their phones land in the library root under raw YouTube titles. This asks two local
models which language each is sung in, and renames and files a song only when both give the same
answer. Everything else stays where it is, listed for a person. Written up in [A Karaoke Server for My Partner, and Two Local AI Models That Argue About Cantopop at 4 am](https://geekconsulting.au/writing/karaoke-server-homelab-ai/).

## Status

As of 2026-10-10. Everything in this section is from the author's own install and cannot be
reproduced from the files here; only the 80-title test in `eval/` can. **Run there:** twelve nightly runs on a library of about 800 songs in Korean,
Mandarin, Cantonese and English; 40 songs filed; the agreement rule; Chinese name building; the log;
the fail-safe when the workflow is unreachable.
**Known wrong:** the artist/title split has no second check. One song was filed with the song title
as the artist and an uploader tag as the title. Two copies of a song by a Hong Kong singer, which
appears to be in Mandarin, were filed as Cantopop with both models agreeing.
**Not proven:** any other language pair, and libraries whose names follow a different pattern.

## Files

- `karaoke-tidy.workflow.json`: the n8n workflow. Webhook in, two Ollama calls per title, one
  decision step, JSON out. Exported from the running workflow with ids and addresses removed.
- `karaoke-tidy.py`: runs on the PiKaraoke host. Lists root songs, calls the webhook, re-validates
  every decision, moves the files, restarts PiKaraoke, writes the log. Derived from the script on the author's
  install; the three addresses became environment variables. Dry run unless `--execute`.
- `karaoke-tidy.service`, `karaoke-tidy.timer`: systemd units for 04:00.
- `eval/`: the raw model answers on 80 labelled titles, and `score.py` to recompute the figures.

## Requirements

- PiKaraoke 1.23.0, run as a systemd service called `pikaraoke`, with its `/get_queue` and
  `/now_playing` routes reachable from the script.
- [n8n](https://n8n.io/) (built on 2.41.6), reachable from the PiKaraoke host.
- [Ollama](https://ollama.com/) (built on 0.35.1) with `gpt-oss:20b` and `qwen3:30b-a3b` pulled,
  reachable from n8n.
- Python 3 with [OpenCC](https://github.com/BYVoid/OpenCC) and
  [pypinyin](https://github.com/mozillazg/python-pinyin) (Debian: `python3-opencc`, `python3-pypinyin`).

## Substitute these

| Placeholder | In | What it is | Example |
|---|---|---|---|
| `__OLLAMA_URL__` | workflow, twice | base address of Ollama | `http://ollama.example:11434` |
| `__N8N_WEBHOOK_URL__` | service | the workflow's production webhook | `https://n8n.example/webhook/karaoke-tidy` |
| `__LIBRARY_PATH__` | service, twice | PiKaraoke's download path | `/media/karaoke` |
| `__PIKARAOKE_URL__` | service | PiKaraoke's own address, as seen from the script | `http://127.0.0.1:5555` |

`grep -o "__[A-Z_]*__" *` lists every one left. The script reads `KARAOKE_TIDY_WEBHOOK`,
`KARAOKE_LIBRARY` and `PIKARAOKE_URL` from the environment and refuses to run without all three.

## Mandarin or Cantonese splits

When both models say "Chinese" but disagree on which, **this workflow leaves the song for review**.

The original install does something else there, which is not shipped because it needs an account
with a hosted service: it asks [Jev](https://typesafe.ai/), a hosted decision model, one yes/no question
("This is the title of a YouTube karaoke video. Is this song sung in Cantonese?") and files the
song as Cantopop at 0.5 or above, Mandopop below. `eval/` has those answers too. If you add
something like it, send it only the split titles and keep "no answer" meaning "leave for review".

So the shipped workflow differs from the running one in this one branch, and **that edited branch
has not been run**. The rest matches what runs on the author's install, which you cannot check from here.

## The measurements

`eval/` holds the raw answers behind every figure quoted here, and `python3 eval/score.py`
recomputes them: 80 labelled titles; each of the two models used here gets 67 right alone (a
third, smaller model that is not used gets 72); the two used
here agree on 55 and all 55 are right; they split Mandarin against Cantonese on 20, of which 10
are labelled each way; the hosted yes/no question matches the label on 19 of those 20.

That is a test of 80 titles labelled by their source channel, not a guarantee. On the live library
the same rule has since filed one song in what looks like the wrong language folder (see Status).

## Assumptions that bite

- **Folder names are the labels.** `K-pop`, `Mandopop`, `Cantopop`, `English` appear in the prompt,
  the schema, the decision step and the script's allow-list. Change all four together. The script's
  allow-list also accepts a `Chinese` folder, left from an earlier version; the workflow never
  sends it, and you can delete it.
- **The agreement rule depends on these two models.** It works because their errors point in
  opposite directions. Swap a model and you must re-measure.
- **Filenames end in the YouTube id** (`---<11 characters>`), as PiKaraoke writes them. Files
  without it are skipped. The id is kept on rename because play history is keyed on it.
- **Names follow `<English artist> <native artist> - <native title> (<romanisation>)`.** The
  artist-name map is learned from files already named that way. On an empty library it learns
  nothing and the models name every artist.
- **Simplified Chinese.** Names are converted Traditional to Simplified. Remove the `t2s` step if
  your singers read Traditional.
- **Case-insensitive shares.** A capitals-only rename through an SMB mount can report success and
  do nothing. The script leaves those for review.

## Install

1. Import the workflow into n8n, substitute the placeholder, activate it.
2. Put `karaoke-tidy.py` on the PiKaraoke host. Export the three environment variables and run it
   with no arguments. Read the plan it prints.
3. Run it once with `--execute` while nobody is singing.
4. Install the two units, substitute the placeholders, `systemctl enable --now karaoke-tidy.timer`.

## Verify it works

- After a dry run, no song has moved. The one thing a dry run does write is its own entry in
  `.logs/tidy.log` inside the library (it creates `.logs/` if needed).
- After `--execute`, list the genre folder: the file is there under its new name. Search for it in
  PiKaraoke's web page. Check the song count in PiKaraoke before and after: it must not drop.
- Stop n8n and run it: it must say nothing moved, and exit non-zero.

## For AI agents

1. Read PiKaraoke's routes on the installed version before trusting `/get_queue` and
   `/now_playing`; the script refuses to move anything if it cannot read the queue, so keep that.
2. Dry-run and show the plan before `--execute`. Never add a delete.
3. Do not gate on the models' `confidence` field. In `eval/`, one model reported 0.95 on all 13 of
   its wrong answers and on 66 of its 67 right ones.
4. Before changing a model or adding a language, build a labelled test set and measure agreement
   and wrong moves, not accuracy alone.
5. Count the library before and after any rename; a success return is not proof.
6. Never build a shell command from a filename.

## License

MIT, see the repository root.
