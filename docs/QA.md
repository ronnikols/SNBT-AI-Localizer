# QA and Jury: what is evaluated and how

This document describes how snbt_localizer verifies translation quality: what
the deterministic machine tier catches (free, before any LLM), what the LLM
judge evaluates, how a multi-judge jury works, and how fixes are applied.

---

## 1. Machine tier (Tier B) — before the audit, 0 tokens

Deterministic checks. Everything they catch is **hard**: the pair is
retranslated by the main translator immediately, and the LLM judge never sees
that text.

| Detector | Catches | Example |
|---|---|---|
| `not_target_lang` | ≥90% of words are outside the target script | "Craft the Lead Ingot" left in English |
| `cjk_symbols` | **Any** Chinese / Japanese (kana) / Korean (hangul) / full-width character in a non-CJK target | "Сделай 工作台 тут" — the translation slipped into Chinese |
| `mixed_script` | one word mixing two alphabets | "Sсейчас", "Блок你好" |
| `latin_leak` | a latin word that is **not in the source** (mod names from the source are legal) | "S&lnow" → "Snow" |
| `garbage_chars` | replacement / zero-width characters | `\ufffd` |
| UNTRANSLATED (full-copy) | translation equals the source (with a mod-name whitelist: minecraft, ae2, create…) | — |
| `CODES_MISMATCH` | lost/added format codes `&l`, `&#RRGGBB`, tags | — |
| `NUMBERS_MISMATCH` | numbers/units/percentages differ from the source | "10%" → "15%" |
| `GLUE_ARTIFACT` | a duplicated word in the translation that the source does not repeat (source repetition is legal) | "предохранители… предохранители" |

Retry after a script violation: one, through the main translator (context
`qa-script-retry`). If the same string comes back, the pair is honestly counted
as `unresolved` — never silently skipped. A script-fixed pair stays in the
audit: the judge re-checks the fresh text.

---

## 2. LLM audit — two-phase (cheap head, expensive details)

**Phase 1 (ids-only):** the judge scans every pair in batches and returns only
the ids that have a problem — a cheap call, schema drift nearly impossible.

**Phase 2 (details):** on the flagged ids — full verdict
`{id, category, severity, issue, suggested, glossary_fix}`.

Categories:
- **hard** (auto-escalated): `UNTRANSLATED`, `WRONG_DOMAIN` (homonyms:
  Frame = рама, Rod = стержень), `GRAMMAR`, `MEANING_FLIP`,
  `SOURCE_GARBAGE` (source typos resolved by meaning), `TRUNCATED`;
- **soft** (fixed by a deterministic replacement): `TERM_INCONSISTENT`,
  `GLOSSARY_VIOLATION`, `GLOSSARY_AWKWARD`, `VANILLA_TERM`, `PROPER_NOUN`,
  `INVENTED_WORD`, `CALQUE`, `STYLE` + synonyms (`MISTRANSLATION`,
  `CAPITALIZATION`, `FLUENCY`, `OMISSION`, `TERMINOLOGY` — normalized).

Judge rules: meaning, not taste; official vanilla terms are authoritative
("Всполох", "жители"); mod names in `@JEI` references are not translated; the
issue must be non-empty; a suggested string preserves the exact multiset of
codes/numbers/tags.

**Advice without a replacement → constraint-retry:** when the judge explains
but does not give a replacement string, the finding is returned to the model as
a constraint (1 retry) and the fix is completed.

---

## 3. Jury — several judges

- Judges: **j1** = the main QA configuration; **j2–j4** = additional ones, each
  with its own key/model (the "Additional judges" table in the GUI).
- Phase 1 runs with the **same prompt in parallel for all** — diversity comes
  from the models, not from the prompts.
- **Consensus**: threshold 2/N by default. ≥ threshold → phase 2 by the
  primary; 1 vote → the pair is **disputed** → **foreman** (j1 at effort+1,
  neutral prompt: it is not told who flagged). The foreman verdict is final:
  confirmed → the apply pipeline runs, cleared → the pair is clean.
- Survival: a judge dies (dead key) → excluded with an honest log line; one
  left → single-judge mode; the foreman dies → disputed pairs stay disputed.
- `glossary_fix` is accepted only by consensus.

---

## 4. Glossary — term convergence

- **Pins are additive forever**: an existing pin is never re-asked (the
  re-roll roulette is dead).
- **Extractor** (auto pre-scan over quest titles): accepts multi-word terms and
  rare capitalized words; frequent words, verbs, numerals, prepositions/adverbs
  (a closed class of 140 words) are rejected with a log line
  `[Glossary] pin 'X' rejected (...)`.
- **Write gate** for auditor advice: frequency is NOT applied (advice is a
  deliberate decision), but prose/non-terms/declined forms are cut;
  "Power → Энергия" passes, "and → Энтро-пыль" does not.
- **Pin arbitration**: a string deviates from a pin → a mini-model decides: the
  pin is good → the string is fixed; the pin is bad → `glossary_fix` and the
  pin is replaced.
- The vanilla glossary is **disabled** (owner's decision): official terms are
  only a hint in the prompt, not enforcement; the known poisons
  (Lead→Поводок, Power→Сила) are gone.

---

## 5. Apply pipeline and the second pass

1. **hard** → translation retry (machine or judge).
2. **soft + suggested** → deterministic replacement with code/number/tag
   validation.
3. **advice without a replacement** → constraint-retry.
4. **pass-2**: every changed pair is rescanned (at most 2 passes);
   "pass-2: clean" = the retry passed the check.
5. Unresolved items go to `unresolved` with an honest counter, not silently.

The run summary is ONE `[QA] run total` line and one `[JURY] run total` line
for the entire run (all phases and files); the dataset is one jsonl
(`~/.snbt-tr/datasets/<pack>/<run_ts>.jsonl`) with a verdict for every pair.

---

## 6. Resilience

- Timeout ladder 90→120→150→180s; a batch is split in half after a timeout.
- Key: 2 consecutive failures → benched for the rest of the run; with a
  single-key pool a cooldown is used instead of a bench. 402/401/403 = key
  death, not "scan failed".
- Scan-failed pairs are **not** marked clean in the verdict cache.
- The verdict cache is keyed by pair content (source+translation+config): valid
  across runs, and overwrite does not poison it.
