# -*- coding: utf-8 -*-
"""Vendored OpenAI CLIP BPE tokenizer for the local AI embedder (EP7).

Adapted from openai/CLIP (clip/simple_tokenizer.py, MIT License) so StaX does not
depend on the full `clip` package. ``ftfy`` is optional here (it only fixes
mojibake); ``regex`` is required for CLIP's exact token pattern.

``ClipTokenizer(model_dir).encode(text)`` returns a ``(1, 77)`` int32 array of
token ids — the input the bundled CLIP text encoder (clip_text.onnx) expects.
The BPE merge table is read from ``bpe_simple_vocab_16e6.txt.gz`` inside
``model_dir`` (the same weights folder that holds the ONNX models).
"""

import gzip
import html
import os
from functools import lru_cache

import numpy as np
import regex as re

try:                                    # ftfy only fixes mojibake; optional.
    import ftfy

    def _fix_text(text):
        return ftfy.fix_text(text)
except Exception:                       # pragma: no cover - ftfy not installed
    def _fix_text(text):
        return text


@lru_cache()
def default_bpe():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "bpe_simple_vocab_16e6.txt.gz")


@lru_cache()
def bytes_to_unicode():
    bs = (list(range(ord("!"), ord("~") + 1)) +
          list(range(ord("\xa1"), ord("\xac") + 1)) +
          list(range(ord("\xae"), ord("\xff") + 1)))
    cs = bs[:]
    n = 0
    for b in range(2 ** 8):
        if b not in bs:
            bs.append(b)
            cs.append(2 ** 8 + n)
            n += 1
    cs = [chr(c) for c in cs]
    return dict(zip(bs, cs))


def get_pairs(word):
    pairs = set()
    prev_char = word[0]
    for char in word[1:]:
        pairs.add((prev_char, char))
        prev_char = char
    return pairs


def basic_clean(text):
    text = _fix_text(text)
    text = html.unescape(html.unescape(text))
    return text.strip()


def whitespace_clean(text):
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class SimpleTokenizer(object):
    def __init__(self, bpe_path=None):
        bpe_path = bpe_path or default_bpe()
        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}
        merges = gzip.open(bpe_path).read().decode("utf-8").split("\n")
        merges = merges[1:49152 - 256 - 2 + 1]
        merges = [tuple(merge.split()) for merge in merges]
        vocab = list(bytes_to_unicode().values())
        vocab = vocab + [v + "</w>" for v in vocab]
        for merge in merges:
            vocab.append("".join(merge))
        vocab.extend(["<|startoftext|>", "<|endoftext|>"])
        self.encoder = dict(zip(vocab, range(len(vocab))))
        self.decoder = {v: k for k, v in self.encoder.items()}
        self.bpe_ranks = dict(zip(merges, range(len(merges))))
        self.cache = {"<|startoftext|>": "<|startoftext|>",
                      "<|endoftext|>": "<|endoftext|>"}
        self.pat = re.compile(
            r"""<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|"""
            r"""[\p{L}]+|[\p{N}]|[^\s\p{L}\p{N}]+""",
            re.IGNORECASE)

    def bpe(self, token):
        if token in self.cache:
            return self.cache[token]
        word = tuple(token[:-1]) + (token[-1] + "</w>",)
        pairs = get_pairs(word)
        if not pairs:
            return token + "</w>"
        while True:
            bigram = min(pairs, key=lambda pair: self.bpe_ranks.get(pair, float("inf")))
            if bigram not in self.bpe_ranks:
                break
            first, second = bigram
            new_word = []
            i = 0
            while i < len(word):
                try:
                    j = word.index(first, i)
                    new_word.extend(word[i:j])
                    i = j
                except ValueError:
                    new_word.extend(word[i:])
                    break
                if word[i] == first and i < len(word) - 1 and word[i + 1] == second:
                    new_word.append(first + second)
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            new_word = tuple(new_word)
            word = new_word
            if len(word) == 1:
                break
            pairs = get_pairs(word)
        word = " ".join(word)
        self.cache[token] = word
        return word

    def encode(self, text):
        bpe_tokens = []
        text = whitespace_clean(basic_clean(text)).lower()
        for token in re.findall(self.pat, text):
            token = "".join(self.byte_encoder[b] for b in token.encode("utf-8"))
            bpe_tokens.extend(self.encoder[bpe_token] for bpe_token in self.bpe(token).split(" "))
        return bpe_tokens


class ClipTokenizer(object):
    """Encode text to the (1, context_length) int32 token tensor CLIP expects."""

    def __init__(self, model_dir=None, context_length=77):
        if model_dir:
            bpe_path = os.path.join(model_dir, "bpe_simple_vocab_16e6.txt.gz")
        else:
            bpe_path = default_bpe()
        self._tok = SimpleTokenizer(bpe_path)
        self.context_length = context_length
        self.sot = self._tok.encoder["<|startoftext|>"]
        self.eot = self._tok.encoder["<|endoftext|>"]

    def encode(self, text):
        tokens = [self.sot] + self._tok.encode(text or "") + [self.eot]
        n = self.context_length
        if len(tokens) > n:
            tokens = tokens[:n]
            tokens[-1] = self.eot
        arr = np.zeros((1, n), dtype=np.int32)
        arr[0, :len(tokens)] = np.asarray(tokens, dtype=np.int32)
        return arr
