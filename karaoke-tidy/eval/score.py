#!/usr/bin/env python3
"""Recompute the figures quoted in the README from the raw answers in this folder.

  python3 score.py

results-local.jsonl   one line per (model, title): the label, and the model's JSON answer
results-jev.jsonl     one line per title: the hosted model's genre choice and its
                      probability for "is this sung in Cantonese?"

The labels come from where each title was taken (a Korean karaoke channel, a Mandarin one, a
Cantonese one, assorted English ones), so a few may be wrong: the Cantonese channel also hosts
Mandarin songs by Hong Kong singers.
"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CHINESE = {'Mandopop', 'Cantopop'}
A, B = 'gpt-oss:20b', 'qwen3:30b-a3b'


def load(name):
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    local = load('results-local.jsonl')
    by_model = collections.defaultdict(dict)
    label = {}
    for r in local:
        by_model[r['model']][r['title']] = r.get('answer') or {}
        label[r['title']] = r['genre']

    print(f'{len(label)} labelled titles')
    for model, answers in by_model.items():
        right = sum(a.get('genre') == label[t] for t, a in answers.items())
        wrong_conf = sorted({a.get('confidence') for t, a in answers.items()
                             if a.get('genre') != label[t] and a.get('confidence') is not None})
        print(f'  {model:16} {right}/{len(answers)} right; confidence on its wrong answers: {wrong_conf}')

    agree = right = 0
    splits = []
    for t in label:
        ga, gb = by_model[A].get(t, {}).get('genre'), by_model[B].get(t, {}).get('genre')
        if ga and ga == gb and ga != 'Other':
            agree += 1
            right += ga == label[t]
        elif ga in CHINESE and gb in CHINESE:
            splits.append(t)
    print(f'{A} and {B} agree on {agree}; {right} of those are right, {agree - right} wrong')
    print(f'both say Chinese but disagree: {len(splits)}; '
          f'{sum(label[t] == "Mandopop" for t in splits)} are labelled Mandopop')

    jev = {r['title']: r['answer'] for r in load('results-jev.jsonl')}
    ok = sum((jev[t].get('cantonese', 0) >= 0.5) == (label[t] == 'Cantopop') for t in splits if t in jev)
    print(f'hosted yes/no at 0.5 settles {ok} of those {len(splits)} as labelled')


if __name__ == '__main__':
    main()
