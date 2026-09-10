"""A small public smoke suite, not a calibrated or held-out rating standard."""

from __future__ import annotations

import random
import re
from typing import Any

from .data import digest

HEADER = "{-# OPTIONS --without-K --exact-split #-}\nmodule Task where\n\n"
EQUALITY = """data Eq {A : Set} (x : A) : A → Set where
  refl : Eq x x

"""
NAT = """data Nat : Set where
  zero : Nat
  succ : Nat → Nat

add : Nat → Nat → Nat
add zero n = n
add (succ m) n = succ (add m n)

"""
LIST = """data List (A : Set) : Set where
  nil : List A
  cons : A → List A → List A

append : {A : Set} → List A → List A → List A
append nil ys = ys
append (cons x xs) ys = cons x (append xs ys)

"""
SIGMA = """record Sigma (A : Set) (B : A → Set) : Set where
  constructor pair
  field
    first : A
    second : B first
open Sigma

"""
VECTOR = """data Vec (A : Set) : Nat → Set where
  vnil : Vec A zero
  vcons : {n : Nat} → A → Vec A n → Vec A (succ n)

"""


def smoke_suite(*, seed: int = 0, variants: int = 2) -> dict[str, Any]:
    if type(variants) is not int or not 1 <= variants <= 100:
        raise ValueError("variants must be between 1 and 100")
    # (domain, family, context, immutable type, witness body)
    templates = [
        ("logic", "identity", "", "{A : Set} → A → A", "goal x = x\n"),
        (
            "logic",
            "composition",
            "",
            "{A B C : Set} → (A → B) → (B → C) → A → C",
            "goal f g x = g (f x)\n",
        ),
        (
            "logic",
            "exchange",
            "",
            "{A B C : Set} → (A → B → C) → B → A → C",
            "goal f y x = f x y\n",
        ),
        (
            "logic",
            "contraction",
            "",
            "{A B : Set} → (A → A → B) → A → B",
            "goal f x = f x x\n",
        ),
        (
            "equality",
            "reflexivity",
            EQUALITY,
            "{A : Set} → (x : A) → Eq x x",
            "goal x = refl\n",
        ),
        (
            "equality",
            "symmetry",
            EQUALITY,
            "{A : Set} {x y : A} → Eq x y → Eq y x",
            "goal refl = refl\n",
        ),
        (
            "equality",
            "transitivity",
            EQUALITY,
            "{A : Set} {x y z : A} → Eq x y → Eq y z → Eq x z",
            "goal refl q = q\n",
        ),
        (
            "equality",
            "congruence",
            EQUALITY,
            "{A B : Set} (f : A → B) {x y : A} → Eq x y → Eq (f x) (f y)",
            "goal f refl = refl\n",
        ),
        (
            "induction",
            "add-right-zero",
            EQUALITY + NAT,
            "(n : Nat) → Eq (add n zero) n",
            "goal zero = refl\ngoal (succ n) rewrite goal n = refl\n",
        ),
        (
            "induction",
            "add-right-succ",
            EQUALITY + NAT,
            "(m n : Nat) → Eq (add m (succ n)) (succ (add m n))",
            "goal zero n = refl\ngoal (succ m) n rewrite goal m n = refl\n",
        ),
        (
            "induction",
            "add-associativity",
            EQUALITY + NAT,
            "(a b c : Nat) → Eq (add (add a b) c) (add a (add b c))",
            "goal zero b c = refl\ngoal (succ a) b c rewrite goal a b c = refl\n",
        ),
        (
            "induction",
            "append-right-unit",
            EQUALITY + LIST,
            "{A : Set} (xs : List A) → Eq (append xs nil) xs",
            "goal nil = refl\ngoal (cons x xs) rewrite goal xs = refl\n",
        ),
        (
            "dependent",
            "transport",
            EQUALITY,
            "{A : Set} (B : A → Set) {x y : A} → Eq x y → B x → B y",
            "goal B refl b = b\n",
        ),
        (
            "dependent",
            "sigma-map",
            SIGMA,
            "{A : Set} {B C : A → Set} → ((x : A) → B x → C x) → Sigma A B → Sigma A C",
            "goal f (pair x b) = pair x (f x b)\n",
        ),
        (
            "dependent",
            "vector-map",
            NAT + VECTOR,
            "{A B : Set} {n : Nat} → (A → B) → Vec A n → Vec B n",
            "goal f vnil = vnil\ngoal f (vcons x xs) = vcons (f x) (goal f xs)\n",
        ),
        (
            "dependent",
            "vector-append",
            NAT + VECTOR,
            "{A : Set} {m n : Nat} → Vec A m → Vec A n → Vec A (add m n)",
            "goal vnil ys = ys\ngoal (vcons x xs) ys = vcons x (goal xs ys)\n",
        ),
    ]
    # Witnesses use rewrite, requiring the equality builtin in trusted context.
    # The runner forbids new pragmas in contestant-supplied text.
    eq_with_builtin = EQUALITY + "{-# BUILTIN EQUALITY Eq #-}\n\n"
    rng = random.Random(seed)
    tasks = []
    symbols = "A B C x y z a b c f g m n q xs ys Eq refl Nat zero succ add List nil cons append Sigma pair first second Vec vnil vcons".split()
    pattern = re.compile(r"\b(" + "|".join(symbols) + r")\b")
    for domain, family, context, signature, reference in templates:
        if "rewrite" in reference:
            context = context.replace(EQUALITY, eq_with_builtin)
        for variant in range(variants):
            mapping = {symbol: f"s{rng.getrandbits(64):016x}" for symbol in symbols}

            def rename(text: str, mapping: dict[str, str] = mapping) -> str:
                return pattern.sub(lambda match: mapping[match[0]], text)

            prefix = HEADER + rename(context + "goal : " + signature) + "\n"
            task = {
                "id": f"{family}-{variant}",
                "domain": domain,
                "family": family,
                "prefix": prefix,
                "starter": "goal = {!!}\n",
                "reference": rename(reference),
            }
            tasks.append(task)
    return {
        "schema_version": "portable-prover-rating.suite.v1",
        "name": "Agda portable smoke v1",
        "role": "public-smoke-only",
        "track": "agda-intensional-without-K-exact-split-v1",
        "generator_seed": seed,
        "tasks": tasks,
    }


def suite_metadata(suite: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": t["id"],
            "domain": t["domain"],
            "family": t["family"],
            "sha256": digest({"prefix": t["prefix"], "starter": t["starter"]}),
        }
        for t in suite["tasks"]
    ]
