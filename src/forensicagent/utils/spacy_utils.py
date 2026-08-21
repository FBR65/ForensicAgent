from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any

import spacy
from spacy.matcher import PhraseMatcher

SPACY_MODEL = "de_dep_news_trf"
os.environ.setdefault("FORENSIC_SPACY_MODEL", SPACY_MODEL)
SPACY_MODEL = os.environ.get("FORENSIC_SPACY_MODEL", SPACY_MODEL)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_nlp() -> spacy.language.Language:
    return spacy.load(SPACY_MODEL)


@lru_cache(maxsize=1)
def get_nlp_ner() -> spacy.language.Language:
    return spacy.load(SPACY_MODEL)


def extract_entities(text: str) -> list[dict[str, Any]]:
    nlp = get_nlp()
    doc = nlp(text)
    entities: list[dict[str, Any]] = []
    for ent in doc.ents:
        sent = ent.sent
        entities.append({
            "text": ent.text,
            "label": ent.label_,
            "start": ent.start_char,
            "end": ent.end_char,
            "sent_start": sent.start_char if sent else 0,
            "sentence": sent.text.strip() if sent else "",
        })
    return entities


def split_sentences(text: str) -> list[str]:
    nlp = get_nlp()
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents]


def tokenize(text: str) -> list[str]:
    nlp = get_nlp()
    doc = nlp(text)
    return [token.lemma_.lower() for token in doc if not token.is_punct and not token.is_space]


# Domain-specific regex patterns.  The DATE patterns are ordered so that
# the longer/more-specific one wins in overlap resolution.
_GERMAN_DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SLASH_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
# German court reference (Aktenzeichen): "2 O 415/2026", "31 C 4321/22", "I ZR 123/22"
_COURT_REF_RE = re.compile(r"\b\d{1,2}\s+[A-Z]{1,2}\s+\d{1,4}/\d{2,4}\b"
                           r"|\bI\s+[A-Z]{1,2}\s+\d{1,4}/\d{2,4}\b")
# ISO-8601 timestamps: "2026-03-14T08:47:32Z", "2026-03-14T08:47:32+02:00", "2026-03-14 08:47:32"
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?\b"
    r"|\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b"
)
# Device / host identifiers: "SRV-DB-01", "DEV-A8F3-2026", "WIN-7K9X2M"
_DEVICE_ID_RE = re.compile(
    r"\b(?:DEV|SRV|WIN|WS|HOST|PC|LAPTOP|SERVER|DEVICE|NODE|FW|GW|AP)"
    r"[-_][A-Z0-9]{1,8}(?:[-_][A-Z0-9]{1,8})*\b"
    r"|\b[A-Z]{4,}[-_][A-Z0-9]{2,}(?:[-_][A-Z0-9]{2,})*\b"
)
# German account number (Kontonummer): 5-10 digit number after a label
_ACCOUNT_RE = re.compile(
    r"(?:Konto(?:nummer)?|Kto|KTN)[:\s]+(\d{5,10})\b"
)
_TAX_CODE_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}\b")
_URL_RE = re.compile(r"\bhttps?://[^\s]+\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PHONE_RE = re.compile(r"\b\+?[\d ]{10,}\b")
# A "real" monetary amount: requires currency symbol OR a decimal part with 2 digits.
# Handles both English (1,234.56) and German (1.234,56) decimal formats.
_AMOUNT_RE = re.compile(
    # Currency prefix + German format (thousands with ., decimals with ,, optional)
    r"(?:[$€£]|USD|EUR|GBP)\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?\b"
    # Currency prefix + English format (thousands with ,, decimals with ., optional)
    r"|(?:[$€£]|USD|EUR|GBP)\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b"
    # Currency prefix + bare number (no thousands separators, optional decimals)
    r"|(?:[$€£]|USD|EUR|GBP)\s*\d+(?:[,.]\d{2})?\b"
    # German format + currency suffix (thousands with ., decimals with ,, optional)
    r"|\b\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s*(?:[$€£]|USD|EUR|GBP)\b"
    # English format + currency suffix (thousands with ,, decimals with ., optional)
    r"|\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:[$€£]|USD|EUR|GBP)\b"
    # Bare German decimal + currency suffix (no thousands separators)
    r"|\b\d+,\d{2}\s*(?:[$€£]|USD|EUR|GBP)\b"
    # Bare English decimal + currency suffix (no thousands separators)
    r"|\b\d+\.\d{2}\s*(?:[$€£]|USD|EUR|GBP)\b"
    # German decimal, no currency (with thousands separators)
    r"|\b\d{1,3}(?:\.\d{3})*,\d{2}\b"
    # English decimal, no currency (with thousands separators)
    r"|\b\d{1,3}(?:,\d{3})*\.\d{2}\b"
    # Bare German decimal, no currency (no thousands separators)
    r"|\b\d+,\d{2}\b"
    # Bare English decimal, no currency (no thousands separators)
    r"|\b\d+\.\d{2}\b"
)


def extract_domain_entities(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for label, pattern in [
        ("TAX_CODE", _TAX_CODE_RE),
        ("IBAN", _IBAN_RE),
        ("EMAIL", _EMAIL_RE),
        ("URL", _URL_RE),
        ("IP_ADDRESS", _IP_RE),
        ("PHONE", _PHONE_RE),
        ("COURT_REF", _COURT_REF_RE),
        ("TIMESTAMP", _TIMESTAMP_RE),
        ("DEVICE_ID", _DEVICE_ID_RE),
        ("DATE", _ISO_DATE_RE),
        ("DATE", _SLASH_DATE_RE),
        ("GERMAN_DATE", _GERMAN_DATE_RE),
        ("AMOUNT", _AMOUNT_RE),
    ]:
        for m in pattern.finditer(text):
            # For ACCOUNT, only capture the number group.
            match_text = m.group(1) if m.groups() else m.group()
            results.append({
                "text": match_text,
                "label": label,
                "start": m.start(1) if m.groups() else m.start(),
                "end": m.end(1) if m.groups() else m.end(),
            })
    # ACCOUNT extraction (uses a capture group for the number itself).
    for m in _ACCOUNT_RE.finditer(text):
        results.append({
            "text": m.group(1),
            "label": "ACCOUNT",
            "start": m.start(1),
            "end": m.end(1),
        })
    results.extend(_extract_person_names(text))
    return results


# Pattern: "Label: <First Last>" or "<First Last>" after a field header.
# Allows newlines/tabs between label and name.
_PERSON_LABEL_RE = re.compile(
    r"(?:"
    r"Insured\s+(?:Person|Name)|Drivers?|Witnesse?s|Patients?|Subjects?|"
    r"Name|Account\s+Holder|Applicant|Insured"
    r"|Kläger(?:in)?|Beklagte?|Zeuge(?:in)?|Gutachter(?:in)?|Arzt(?:ärztin)?"
    r"|Patient(?:in)?|Versicherte?r|Fahrer(?:in)?|Name|Untersuchung(?:s)?"
    r"|Sachbearbeiter(?:in)?|Rechtsanwalt(?:Rechtsanwältin)?|Richter(?:in)?"
    r"|Prüfer(?:in)?|Buchhalter(?:in)?|Sachverständige?r"
    r")[\s:]+([A-Z][a-zäöüß]+(?: [A-Z][a-zäöüß]+){0,3})",
)
# Fallback: standalone "First Last" with two+ capitalized tokens.
_PROPER_NAME_RE = re.compile(r"\b([A-Z][a-zäöüß]+(?:\ [A-Z][a-zäöüß]+){1,3})\b")

# Field headers / section names that look like names but aren't.
_FALSE_PERSON_WORDS = {
    "REPORT", "NUMBER", "PARTIES", "PLATE", "DESCRIPTION", "RESULT",
    "STATEMENT", "FILE", "FORM", "DOCUMENT", "CASE", "INCIDENT",
    "PHOTO", "TIMESTAMP", "VEHICLE", "DAMAGE", "HEADLIGHT", "BUMPER",
    "INSURANCE", "PROVIDER", "CONCLUSION", "INVESTIGATION",
    "LANDGERICHT", "AMTSGERICHT", "OLG", "BGH", "BVERWG",
}


def _looks_like_person(name: str) -> bool:
    """Heuristic: reject multi-word proper names where any token is a
    common document field word."""
    tokens = name.split()
    if len(tokens) == 1 and tokens[0].upper() in _FALSE_PERSON_WORDS:
        return False
    for tok in tokens:
        if tok.upper() in _FALSE_PERSON_WORDS:
            return False
    return True


def _extract_person_names(text: str) -> list[dict[str, Any]]:
    """Extract PERSON entities using structured-field patterns first, then
    a proper-noun fallback.  Compensates for the German model's NER
    limitations on mixed-language / structured forensic documents."""
    results: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()
    for m in _PERSON_LABEL_RE.finditer(text):
        name = m.group(1).strip()
        if not _looks_like_person(name):
            continue
        start = m.start(1)
        end = m.end(1)
        if (start, end) not in seen_spans:
            seen_spans.add((start, end))
            results.append({"text": name, "label": "PERSON", "start": start, "end": end})
    # Fallback: only if we didn't find enough label-based names.
    if len(results) < 2:
        for m in _PROPER_NAME_RE.finditer(text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            name = m.group(1).strip()
            if not _looks_like_person(name):
                continue
            if name.upper() in _FALSE_POSITIVE_NAMES:
                continue
            overlapping = any(
                m.start() < r["end"] and m.end() > r["start"]
                for r in results
            )
            if not overlapping:
                seen_spans.add(span)
                results.append({"text": name, "label": "PERSON", "start": span[0], "end": span[1]})
    return results


def _resolve_overlaps(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove shorter overlapping spans; prefer domain entities over NER.
    When priorities are equal, keep the *longer* span."""
    def priority(label: str) -> int:
        domain_priority = {"TAX_CODE": 5, "IBAN": 5, "IP_ADDRESS": 5, "DATE": 4, "GERMAN_DATE": 4, "AMOUNT": 4, "EMAIL": 5, "URL": 5, "PHONE": 3, "COURT_REF": 5, "TIMESTAMP": 5, "DEVICE_ID": 4, "ACCOUNT": 4}
        if label in domain_priority:
            return domain_priority[label]
        return 1
    # Sort by start, then by descending length so longer spans are processed first.
    entities = sorted(entities, key=lambda e: (e["start"], -(e["end"] - e["start"])))
    result: list[dict[str, Any]] = []
    for ent in entities:
        conflict = None
        replace_existing = False
        for existing in result:
            if ent["start"] < existing["end"] and ent["end"] > existing["start"]:
                p_new = priority(ent["label"])
                p_old = priority(existing["label"])
                if p_new > p_old:
                    conflict = "higher"
                    replace_existing = True
                elif p_new == p_old:
                    len_new = ent["end"] - ent["start"]
                    len_old = existing["end"] - existing["start"]
                    if len_new > len_old:
                        conflict = "equal-longer"
                        replace_existing = True
                    else:
                        conflict = "equal-shorter"
                else:
                    conflict = "lower"
                break
        if conflict is None:
            result.append(ent)
        elif replace_existing and conflict in ("higher", "equal-longer"):
            result.remove(existing)
            result.append(ent)
        # else: skip (shorter / lower priority wins)
    return sorted(result, key=lambda e: e["start"])


_FALSE_POSITIVE_NAMES = {
    "STATEMENT", "REPORT", "CASE FILE", "WITNESS STATEMENT",
    "POLICE REPORT", "DATE OF", "LOCATION OF", "INCIDENT",
    "CLAIM FORM", "INVESTIGATION", "INSURANCE PROVIDER",
    "ACCIDENT PHOTO", "WITNESS", "DRIVER", "PATIENT",
    "reports neck pain following", "of the above vehicle",
    "did not request emergency",
    "Landgericht Berlin", "Amtsgericht München", "Amtsgericht Köln",
}


def _is_false_positive(text: str, label: str) -> bool:
    norm = text.strip()
    if norm in _FALSE_POSITIVE_NAMES:
        return True
    if norm.upper() in _FALSE_POSITIVE_NAMES:
        return True
    return False


def extract_all_entities(text: str) -> list[dict[str, Any]]:
    ents = extract_entities(text)
    # The de_dep_news_trf model's NER is unreliable for PERSON in
    # mixed-language forensic docs; use our custom regex-based extraction
    # instead and filter out spaCy PERSON + known false positives.
    ents = [
        e for e in ents
        if e["label"] != "PERSON" and not _is_false_positive(e["text"], e["label"])
    ]
    domain = extract_domain_entities(text)
    domain = [e for e in domain if not _is_false_positive(e["text"], e["label"])]
    combined = _resolve_overlaps(ents + domain)
    return combined


class EvidencePhraseMatcher:
    def __init__(self, nlp: spacy.language.Language) -> None:
        self._nlp = nlp
        self._matcher = PhraseMatcher(nlp.vocab, attr="LOWER")

    def add(self, label: str, phrases: list[str]) -> None:
        docs = [self._nlp.make_doc(p) for p in phrases]
        self._matcher.add(label, docs)

    def __call__(self, text: str) -> list[dict[str, Any]]:
        nlp = self._nlp
        doc = nlp(text)
        matches = self._matcher(doc)
        out: list[dict[str, Any]] = []
        for match_id, start, end in matches:
            label = nlp.vocab.strings[match_id]
            span = doc[start:end]
            out.append({
                "text": span.text,
                "label": label,
                "start": span.start_char,
                "end": span.end_char,
            })
        return out
