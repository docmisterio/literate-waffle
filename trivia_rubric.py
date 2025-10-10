#!/usr/bin/env python3
"""
Generate a grading rubric CSV from a trivia PDF exported by Geeks Who Drink.

The script extracts each round title and the associated answers, outputting a CSV
with the round as a section header followed by question/answer pairs.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zlib
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
NOTE_PATTERN = re.compile(r"\|\s*\(note:.*", re.IGNORECASE)
WHITESPACE_COLLAPSE = re.compile(r"\s+")


def read_stream_strings(data: bytes) -> Iterable[str]:
    """Yield decoded text strings from each compressed PDF stream."""

    for match in STREAM_PATTERN.finditer(data):
        raw_stream = match.group(1)
        try:
            decompressed = zlib.decompress(raw_stream)
        except zlib.error:
            continue
        yield from _strings_from_stream(decompressed.decode("latin1"))


def _strings_from_stream(content: str) -> Iterable[str]:
    """Yield literal strings contained in a single PDF content stream."""

    i = 0
    length = len(content)
    while i < length:
        if content[i] != "(":
            i += 1
            continue

        i += 1
        depth = 1
        chunk: List[str] = []
        while i < length and depth > 0:
            ch = content[i]
            if ch == "\\" and i + 1 < length:
                nxt = content[i + 1]
                if nxt in "nrtbf()\\":
                    mapping = {
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                        "b": "\b",
                        "f": "\f",
                        "(": "(",
                        ")": ")",
                        "\\": "\\",
                    }
                    chunk.append(mapping.get(nxt, nxt))
                    i += 2
                    continue
                if "0" <= nxt <= "7":
                    j = i + 1
                    oct_digits: List[str] = []
                    while j < length and len(oct_digits) < 3 and "0" <= content[j] <= "7":
                        oct_digits.append(content[j])
                        j += 1
                    if oct_digits:
                        chunk.append(chr(int("".join(oct_digits), 8)))
                        i = j
                        continue
                chunk.append(nxt)
                i += 2
                continue
            if ch == "(":
                depth += 1
                chunk.append(ch)
                i += 1
                continue
            if ch == ")":
                depth -= 1
                i += 1
                if depth == 0:
                    break
                chunk.append(ch)
                continue
            chunk.append(ch)
            i += 1
        yield "".join(chunk)

def _is_mostly_printable(token: str) -> bool:
    """Return True when most characters in the token are printable."""

    if not token:
        return False

    printable = sum(32 <= ord(ch) <= 126 or ch in "\t\r\n" for ch in token)
    return printable >= int(len(token) * 0.8) or printable == len(token)


def extract_text(pdf_path: Path) -> str:
    """Return sanitized text scraped from the PDF content streams."""

    data = pdf_path.read_bytes()
    strings = [token for token in read_stream_strings(data) if _is_mostly_printable(token)]
    combined = "".join(strings)
    sanitized = "".join(
        ch for ch in combined if 32 <= ord(ch) <= 126 or ch in "\t\r\n"
    )
    sanitized = sanitized.replace("en-US", " ")
    sanitized = sanitized.replace("\r", " ").replace("\n", " ")
    sanitized = WHITESPACE_COLLAPSE.sub(" ", sanitized)
    return sanitized.strip()


def parse_rounds(text: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Identify rounds and their answers from the flattened document text."""

    rounds: List[Tuple[str, List[Tuple[str, str]]]] = []
    round_pattern = re.compile(
        r"(Round\s+\d+:\s*.*?)(?=Round\s+\d+:|Tiebreakers\b|$)", re.IGNORECASE | re.DOTALL
    )

    for match in round_pattern.finditer(text):
        section = match.group(1).strip()
        question_start = re.search(r"\b\d+\.", section)
        if not question_start:
            continue

        round_name = section[: question_start.start()].strip()
        body = section[question_start.start() :].strip()
        entries = _parse_questions(body)
        if entries:
            rounds.append((round_name, entries))

    # Handle tiebreakers (if any) after the main rounds.
    tb_match = re.search(r"\bTiebreakers\b(.*)", text, re.IGNORECASE | re.DOTALL)
    if tb_match:
        section = tb_match.group(1).strip()
        question_start = re.search(r"\b\d+\.", section)
        if question_start:
            body = section[question_start.start() :].strip()
            entries = _parse_questions(body)
            if entries:
                rounds.append(("Tiebreakers", entries))

    return rounds


def _parse_questions(body: str) -> List[Tuple[str, str]]:
    """Extract (question number, answer) pairs from a round body."""

    entries: List[Tuple[str, str]] = []
    question_pattern = re.compile(r"(\d+)\.\s+(.*?)(?=\d+\.\s+|$)", re.DOTALL)
    expected_number: int | None = None

    for number_text, fragment in question_pattern.findall(body):
        fragment = fragment.strip()
        if not fragment:
            continue

        number = int(number_text)
        if expected_number is None:
            expected_number = number
        elif number != expected_number:
            if number > expected_number:
                break
            expected_number = number

        answer = extract_answer(fragment)
        if answer is None:
            continue
        entries.append((number_text, clean_answer(answer)))
        expected_number = number + 1

    return entries


def extract_answer(segment: str) -> str | None:
    """
    Attempt to pull the answer from a question+answer segment.

    Returns None when the segment appears to be question text only.
    """

    text = segment.strip()
    if not text:
        return None

    for marker in ("?", "!"):
        if marker in text:
            pos = text.rfind(marker)
            trailing = text[pos + 1 :].strip()
            if trailing:
                return trailing
            return None

    return text


def clean_answer(answer: str) -> str:
    """Normalize whitespace, strip annotations, and tidy delimiters."""

    answer = NOTE_PATTERN.split(answer.strip())[0]
    answer = answer.rstrip("|").strip()
    answer = re.sub(r"\s*/\s*", " / ", answer)
    answer = re.sub(r"\s*,\s*", ", ", answer)
    answer = re.sub(r"(?<=\d), (?=\d)", ",", answer)
    answer = re.sub(r"\s{2,}", " ", answer)
    return answer.strip()


def write_csv(rounds: Sequence[Tuple[str, Sequence[Tuple[str, str]]]], output_path: Path) -> None:
    """Write the extracted rubric to CSV with round headers."""

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        for round_name, entries in rounds:
            writer.writerow([round_name])
            writer.writerow(["Question", "Answer"])
            for number, answer in entries:
                writer.writerow([number, answer])
            writer.writerow([])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract a grading rubric CSV from a Geeks Who Drink trivia PDF."
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the source PDF exported from Geeks Who Drink.",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Destination CSV file (defaults to PDF name with .csv extension).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    document_text = extract_text(args.pdf)
    rounds = parse_rounds(document_text)

    if not rounds:
        parser.error("No rounds found in PDF; is this a supported export?")

    output = args.output or args.pdf.with_suffix(".csv")
    try:
        write_csv(rounds, output)
    except PermissionError as exc:
        parser.error(f"Cannot write to {output}: {exc.strerror or exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
