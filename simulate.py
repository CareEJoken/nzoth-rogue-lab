"""Causal goldfish simulator for the published three-minion N'Zoth Rogue list.

The engine knows the real deck order. The policy only uses remaining counts,
hand/board, and publicly revealed Discover/Dredge information. Deterministic
tactical search never resolves a random draw and never looks at the deck order.
"""
from __future__ import annotations

import argparse
import base64
import itertools
import json
import math
import random
import time
from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DECK_CODE = "AAEBAaIHCvDmAq+RA//uA+PTBPXdBMygBe6eBpCDB8euB4XrBwrtAoYJ9bsC3+MC590D/u4DvYAEt7MEracGwZcHAAA="

# Small integer IDs keep the repeated state-space operations inexpensive.
ICE, KOBOLD, NZOTH, STEP, PREP, COIN, SWINDLE, SHROUD, DIG, FISH, MAP, BLADE, PICK, BONE, SHADOW, EVASION, SCHEME, FISH_TRANSFORM, FUEL, DEJA = range(20)
DBF = [76259, 45936, 128389, 365, 1158, 40437, 61159, 63358, 103341, 72119, 117697, 65597, 102254, 77557, 86092, 45535, 51375, 63359, 115088, 120647]
COST = [1, 5, 15, 0, 0, 0, 2, 3, 1, 1, 2, 1, 2, 2, 0, 2, 1, 1, 1, 1]
COPIES = [1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 1, 1, 1, 1]
MINIONS = frozenset((ICE, KOBOLD, NZOTH))
WEAPONS = frozenset((BLADE, PICK))
SPELLS = frozenset(range(20)) - MINIONS - WEAPONS
DRAW_SPELLS = frozenset((SWINDLE, SHROUD, DIG, FISH, MAP))
TACTICAL = frozenset((ICE, KOBOLD, NZOTH, STEP, PREP, COIN, BONE))
CN = {DBF.index(c["dbfId"]): c["name"] for c in json.loads((ROOT / "cards_zhCN.json").read_text(encoding="utf-8"))}


def decode_deck(code):
    data = base64.b64decode(code)
    pos = 0

    def read():
        nonlocal pos
        value = shift = 0
        while True:
            byte = data[pos]
            pos += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7

    assert (read(), read(), read()) == (0, 1, 1)
    heroes = [read() for _ in range(read())]
    result = {}
    for copies in (1, 2):
        for _ in range(read()):
            result[read()] = copies
    assert read() == 0
    return heroes, result


@dataclass(frozen=True, slots=True)
class Card:
    uid: int
    kind: int
    delta: int = 0
    shadow: bool = False


@dataclass(slots=True)
class State:
    deck: list[Card]
    hand: list[Card]
    turn: int = 0
    mana: int = 0
    combo: bool = False
    prep: int = 0
    next_discount: int = 0
    ice_discount: int = 0
    board_ice: bool = False
    board_kobold: bool = False
    enemy_target: bool = False
    weapon: int = -1
    durability: int = 0
    attacked: bool = False
    evasion: bool = False
    known_top: int = -1
    # (selected card uid, turn selected, remaining offered card kinds)
    rewards: tuple = ()
    started: bool = False
    burned: int = 0
    deathrattle_summons: int = 0

    def clone(self):
        return replace(self, deck=self.deck.copy(), hand=self.hand.copy())


def card_cost(s, c):
    result = COST[c.kind] + c.delta - s.next_discount
    if c.kind in SPELLS:
        result -= s.prep
    if c.kind == KOBOLD:
        result -= s.ice_discount
    if c.kind == NZOTH:
        result -= s.deathrattle_summons
    return max(0, result)


def missing(s):
    kinds = {c.kind for c in s.hand}
    return (
        not (s.ice_discount or ICE in kinds),
        not (KOBOLD in kinds or s.board_kobold),
        NZOTH not in kinds,
    )


def acquisition_value(s, kind):
    need = missing(s)
    if kind in MINIONS:
        return (32, 37, 38)[kind] if need[kind] else (2 if kind == ICE else 0)
    if kind == SHADOW:
        return 7
    if kind == STEP:
        return 16 if s.board_ice or any(c.kind == ICE for c in s.hand) else 6
    if kind == COIN:
        return 13 if not any(need) else 9
    if kind == PREP:
        return 12 if any(c.kind in DRAW_SPELLS for c in s.hand) else 6
    if kind in (DIG, SHROUD):
        return 19 if any(need) else 1
    if kind == SWINDLE:
        return 17 if any(need) else 5
    if kind in (FISH, MAP, BLADE):
        return 12 if any(need) else 7
    if kind == PICK:
        return max(1, 13 - 2 * s.turn)
    if kind == BONE:
        return 10 if s.board_ice or s.enemy_target or s.board_kobold else 2
    return 0


def add_hand(s, c):
    if len(s.hand) == 10:
        s.burned += 1
        return False
    s.hand.append(c)
    return True


def draw(s, rng, kind_filter=None, selected_kind=None):
    if not s.deck:
        return None
    if selected_kind is not None:
        indices = [i for i, c in enumerate(s.deck) if c.kind == selected_kind]
    elif kind_filter is not None:
        indices = [i for i, c in enumerate(s.deck) if c.kind in kind_filter]
    else:
        indices = [0]
    if not indices:
        return None
    index = rng.choice(indices)
    c = s.deck.pop(index)
    if index == 0:
        s.known_top = -1
    add_hand(s, c)
    return c


def update_shadow(s, cast):
    # Copies permanent enchantments, not Preparation/next-card aura discounts.
    s.hand = [Card(c.uid, cast.kind, cast.delta, True) if c.shadow else c for c in s.hand]


def discover_options(s, rng, weighted=False):
    pool = Counter(c.kind for c in s.deck)
    result = []
    for _ in range(min(3, len(pool))):
        if weighted:
            kind = rng.choices(list(pool), weights=list(pool.values()))[0]
        else:
            kind = rng.choice(sorted(pool))
        result.append(kind)
        del pool[kind]
    return result


def select_option(s, options, bonus=False):
    if not options:
        return None

    def value(kind):
        result = acquisition_value(s, kind)
        if bonus:
            cost = max(0, COST[kind] - s.next_discount - (s.prep if kind in SPELLS else 0))
            if kind == KOBOLD:
                cost = max(0, cost - s.ice_discount)
            playable = kind in (ICE, COIN, PREP, DIG, SWINDLE, SHROUD, FISH, MAP, BLADE, PICK)
            if kind == STEP:
                playable = s.board_ice or s.board_kobold
            if kind == BONE:
                playable = s.board_ice or s.board_kobold or s.enemy_target
            if playable and cost <= s.mana:
                others = [acquisition_value(s, k) for k in options if k != kind]
                result += 0.65 * max(others, default=0)
        return result, -COST[kind], -kind

    return max(options, key=value)


def finish_rewards(s, uid, rng, trace):
    active = [r for r in s.rewards if r[0] == uid and r[1] == s.turn]
    s.rewards = tuple(r for r in s.rewards if r[0] != uid)
    for _, _, options in active:
        available = {c.kind for c in s.deck}
        valid = [k for k in options if k in available]
        kind = select_option(s, valid)
        if kind is not None:
            c = draw(s, rng, selected_kind=kind)
            if trace is not None:
                trace.append({"turn": s.turn, "event": "map_bonus", "card": CN[c.kind]})


def apply(s, action, rng, trace=None, weighted=False):
    op, uid, target = action
    if op == "attack":
        assert s.weapon >= 0 and s.durability and not s.attacked
        s.attacked = True
        if s.weapon == PICK:
            draw(s, rng)
        s.durability -= 1
        if not s.durability:
            s.weapon = -1
        if trace is not None:
            trace.append({"turn": s.turn, "event": "attack", "mana": s.mana})
        return
    c = next(c for c in s.hand if c.uid == uid)
    if op == "trade":
        assert c.kind == BLADE and s.mana >= 1 and s.deck
        s.mana -= 1
        s.hand.remove(c)
        drawn = draw(s, rng)
        at = rng.randrange(len(s.deck) + 1)
        s.deck.insert(at, c)
        if at == 0:
            s.known_top = -1
        spells = [i for i, h in enumerate(s.hand) if h.kind in SPELLS]
        if spells:
            i = rng.choice(spells)
            s.hand[i] = replace(s.hand[i], delta=s.hand[i].delta - 1)
        if trace is not None:
            trace.append({"turn": s.turn, "event": "trade", "draw": CN[drawn.kind], "mana": s.mana})
        return
    paid = card_cost(s, c)
    assert paid <= s.mana, (action, paid, s.mana)
    before_combo = s.combo
    s.mana -= paid
    s.next_discount = 0
    if c.kind in SPELLS:
        s.prep = 0
    s.hand.remove(c)
    s.combo = True
    if c.kind in SPELLS:
        update_shadow(s, c)
    play_event = None
    if trace is not None:
        play_event = {"turn": s.turn, "event": "play", "card": CN[c.kind], "shadow": c.shadow,
                      "paid": paid, "mana_after_payment": s.mana, "combo_before": before_combo, "target": target}
        trace.append(play_event)
    if c.kind == ICE:
        assert not s.board_ice
        s.board_ice = True
        s.ice_discount += 1
    elif c.kind == KOBOLD:
        assert not s.board_kobold
        s.deathrattle_summons += 1
        if s.ice_discount:
            s.ice_discount = 0
            if [h.kind for h in s.hand if h.kind in MINIONS] == [NZOTH]:
                s.started = True
        else:
            s.board_kobold = True
    elif c.kind == NZOTH:
        raise AssertionError("Hard-casting N'Zoth is outside this <=5-turn model")
    elif c.kind == STEP:
        if target == "ice":
            assert s.board_ice
            s.board_ice = False
            add_hand(s, Card(76259, ICE, -2))
        else:
            assert s.board_kobold
            s.board_kobold = False
            add_hand(s, Card(45936, KOBOLD, -2))
    elif c.kind == PREP:
        s.prep += 2
    elif c.kind == COIN:
        s.mana = min(10, s.mana + 1)
    elif c.kind == BONE:
        if target == "ice":
            assert s.board_ice
            s.board_ice = False
        elif target == "kobold":
            assert s.board_kobold
            s.board_kobold = False
            if [h.kind for h in s.hand if h.kind in MINIONS] == [NZOTH]:
                s.started = True
        else:
            assert s.enemy_target
            s.enemy_target = False
        s.next_discount += 2
    elif c.kind == DIG:
        draw(s, rng, MINIONS)
    elif c.kind == SWINDLE:
        draw(s, rng, SPELLS)
        if before_combo:
            draw(s, rng, MINIONS)
    elif c.kind == SHROUD:
        draw(s, rng, MINIONS)
        draw(s, rng, MINIONS)
    elif c.kind == FISH:
        bottom = s.deck[-3:]
        if bottom:
            chosen = max(bottom, key=lambda h: (acquisition_value(s, h.kind), -COST[h.kind]))
            s.deck.remove(chosen)
            s.deck.insert(0, chosen)
            s.known_top = chosen.uid
            if trace is not None:
                trace.append({"turn": s.turn, "event": "dredge", "options": [CN[h.kind] for h in bottom], "chosen": CN[chosen.kind]})
            if before_combo:
                draw(s, rng)
    elif c.kind == MAP:
        options = discover_options(s, rng, weighted)
        selected = select_option(s, options, bonus=True)
        if selected is not None:
            h = draw(s, rng, selected_kind=selected)
            if h in s.hand:
                s.rewards += ((h.uid, s.turn, tuple(k for k in options if k != selected)),)
            if trace is not None:
                trace.append({"turn": s.turn, "event": "discover", "options": [CN[k] for k in options], "chosen": CN[selected]})
    elif c.kind in WEAPONS:
        s.weapon = c.kind
        s.durability = 2
    elif c.kind == EVASION:
        assert not s.evasion
        s.evasion = True
    else:
        raise AssertionError("Excluded opponent-dependent spell")
    if not s.started:
        finish_rewards(s, uid, rng, trace)
    if play_event is not None:
        play_event["mana_after_resolution"] = s.mana
        play_event["ice_discount_after"] = s.ice_discount


# Tactical solver's hand representation has no deck, RNG, or unknown cards.
# Each entry is (kind, permanent cost delta, is Shadow of Demise).
def tac_hand(s):
    return tuple(sorted((c.kind, c.delta, c.shadow) for c in s.hand if c.kind in TACTICAL or c.shadow))


def tac_args(s):
    return (tac_hand(s), s.mana, s.prep, s.next_discount, s.ice_discount,
            s.board_ice, s.board_kobold, s.enemy_target)


@lru_cache(maxsize=180000)
def tactical(hand, mana, prep, nxt, ice, bi, bk, enemy):
    kinds = [c[0] for c in hand]
    if NZOTH not in kinds or (KOBOLD not in kinds and not bk):
        return None
    for i, (kind, delta, shadow) in enumerate(hand):
        if kind not in TACTICAL or kind == NZOTH:
            continue
        cost = max(0, COST[kind] + delta - nxt - (prep if kind in SPELLS else 0) - (ice if kind == KOBOLD else 0))
        if cost > mana:
            continue
        if kind == ICE and bi:
            continue
        if kind == STEP:
            targets = (["ice"] if bi else []) + (["kobold"] if bk else [])
        elif kind == BONE:
            targets = (["kobold"] if bk else []) + (["enemy"] if enemy else []) + (["ice"] if bi else [])
        else:
            targets = [""]
        for target in targets:
            rest = list(hand[:i] + hand[i + 1:])
            if kind in SPELLS:
                rest = [(kind, delta, True) if sh else (k, d, sh) for k, d, sh in rest]
            m, p, n, a, b, k, e = mana - cost, (0 if kind in SPELLS else prep), 0, ice, bi, bk, enemy
            success = False
            if kind == KOBOLD:
                if a:
                    success = [h[0] for h in rest if h[0] in MINIONS] == [NZOTH]
                    a = 0
                    if not success:
                        continue
                elif not k:
                    k = True
                else:
                    continue
            elif kind == ICE:
                a += 1
                b = True
            elif kind == STEP:
                rest.append((ICE if target == "ice" else KOBOLD, -2, False))
                if target == "ice":
                    b = False
                else:
                    k = False
            elif kind == COIN:
                m = min(10, m + 1)
            elif kind == PREP:
                p += 2
            elif kind == BONE:
                n += 2
                if target == "ice":
                    b = False
                elif target == "kobold":
                    k = False
                    success = [h[0] for h in rest if h[0] in MINIONS] == [NZOTH]
                    if not success:
                        continue
                else:
                    e = False
            selector = (kind, delta, shadow, target)
            if success:
                return (selector,)
            tail = tactical(tuple(sorted(rest)), m, p, n, a, b, k, e)
            if tail is not None:
                return (selector,) + tail
    return None


def actual_action(s, selector):
    kind, delta, shadow, target = selector
    c = next(c for c in s.hand if (c.kind, c.delta, c.shadow) == (kind, delta, shadow))
    return ("play", c.uid, target)


def deterministic_actions(s):
    seen = set()
    for c in s.hand:
        signature = (c.kind, c.delta, c.shadow)
        if signature in seen or card_cost(s, c) > s.mana:
            continue
        seen.add(signature)
        targets = []
        if c.kind == ICE and not s.board_ice:
            targets = [""]
        elif c.kind in (COIN, PREP):
            targets = [""]
        elif c.kind == STEP and s.board_ice:
            targets = ["ice"]
        elif c.kind == BONE:
            if s.enemy_target:
                targets.append("enemy")
            if s.board_ice:
                targets.append("ice")
        elif c.kind == BLADE and s.weapon != PICK and (not s.combo or any(r[0] == c.uid for r in s.rewards)):
            targets = [""]
        elif c.kind == EVASION and not s.evasion and (not s.combo or any(r[0] == c.uid for r in s.rewards)):
            targets = [""]
        for target in targets:
            yield ("play", c.uid, target)


def expected_max(s, counts, sample_size, unique=False):
    n = sum(counts.values())
    if not n:
        return 0
    if unique:
        counts = {k: 1 for k in counts}
        n = len(counts)
    r = min(sample_size, n)
    groups = Counter()
    for kind, count in counts.items():
        groups[acquisition_value(s, kind)] += count
    denom = math.comb(n, r)
    cumulative = previous_cdf = result = 0
    for value, count in sorted(groups.items()):
        cumulative += count
        cdf = math.comb(cumulative, r) / denom if cumulative >= r else 0
        result += value * (cdf - previous_cdf)
        previous_cdf = cdf
    return result


def draw_value(s, c, counts):
    kind = c.kind
    n_minions = sum(counts[k] for k in MINIONS)
    minion_value = sum(counts[k] * acquisition_value(s, k) for k in MINIONS) / n_minions if n_minions else 0
    n_spells = sum(counts[k] for k in SPELLS)
    spell_value = sum(counts[k] * acquisition_value(s, k) for k in SPELLS) / n_spells if n_spells else 0
    if kind == DIG:
        return minion_value
    if kind == SHROUD:
        return min(2, n_minions) * minion_value
    if kind == SWINDLE:
        return spell_value + (minion_value if s.combo else 0)
    if kind == FISH:
        return expected_max(s, counts, 3) * (1 if s.combo else 0.43)
    if kind == MAP:
        return expected_max(s, counts, 3, unique=True) + (5 if s.mana - card_cost(s, c) >= 1 else 0)
    if kind == BLADE:
        if s.known_top >= 0:
            # The identity is publicly known after a previous Dredge.
            top = next(h for h in s.deck if h.uid == s.known_top)
            value = acquisition_value(s, top.kind)
        else:
            value = sum(counts[k] * acquisition_value(s, k) for k in counts) / max(1, sum(counts.values()))
        return value + (2.5 if any(h.kind in DRAW_SPELLS for h in s.hand) else 1)
    if kind == PICK:
        mean = sum(counts[k] * acquisition_value(s, k) for k in counts) / max(1, sum(counts.values()))
        return mean * (1 + (0.8 if s.turn < 5 else 0)) if s.weapon != PICK else 0
    return 0


def setup_value(s):
    value = (9 if s.ice_discount else 0) + 3 * min(3, max(0, s.ice_discount - 1))
    if s.board_ice:
        value += 1
    if any(c.kind == ICE and COST[ICE] + c.delta <= 0 for c in s.hand):
        value += 0.5
    return value


def resource_penalty(kind):
    return {COIN: 5, PREP: 2, STEP: 2, BONE: 2, EVASION: 0, BLADE: 1}.get(kind, 0)


def choose_action(s, rng, prefix_depth=2):
    win = tactical(*tac_args(s))
    if win:
        return actual_action(s, win[0])
    counts = Counter(c.kind for c in s.deck)
    initial_setup = setup_value(s)
    best_score, best_action = 0.0, None
    frontier = [(s, (), 0.0, 0)]
    visited = set()
    while frontier:
        node, prefix, penalty, paid_so_far = frontier.pop()
        key = (tuple(sorted((c.kind, c.delta, c.shadow) for c in node.hand)), node.mana, node.combo,
               node.prep, node.next_discount, node.ice_discount, node.board_ice, node.enemy_target,
               node.weapon, node.evasion)
        if key in visited:
            continue
        visited.add(key)
        progress = setup_value(node) - initial_setup
        score_end = progress - penalty - 3 * paid_so_far
        if prefix and score_end > best_score:
            best_score, best_action = score_end, prefix[0]
        seen = set()
        for c in node.hand:
            signature = (c.kind, c.delta, c.shadow)
            if signature in seen:
                continue
            seen.add(signature)
            if c.kind in DRAW_SPELLS or c.kind == PICK:
                cost = card_cost(node, c)
                if cost > node.mana:
                    continue
                action = ("play", c.uid, "")
                if c.kind == PICK and node.attacked:
                    continue
            elif c.kind == BLADE and node.mana >= 1 and node.deck:
                cost = 1
                action = ("trade", c.uid, "")
            else:
                continue
            benefit = draw_value(node, c, counts)
            if action[0] == "play":
                for uid, turn, options in node.rewards:
                    if uid == c.uid and turn == node.turn:
                        benefit += max((acquisition_value(node, k) for k in options), default=0)
            score = benefit + progress - penalty - 3 * (paid_so_far + cost)
            # Holding a combo-dependent draw for next turn is often better than
            # spending resources just to draw a spell with uncomboed Swindle.
            if c.kind == SWINDLE and not node.combo:
                score -= 5
            if score > best_score:
                best_score, best_action = score, prefix[0] if prefix else action
        if len(prefix) == prefix_depth:
            continue
        for action in deterministic_actions(node):
            c = next(c for c in node.hand if c.uid == action[1])
            # Random post-play rewards are handled by the live engine, not by
            # speculative planning. This prevents using unknown draws as facts.
            if any(r[0] == c.uid for r in node.rewards):
                continue
            child = node.clone()
            spent = card_cost(node, c)
            apply(child, action, rng)
            frontier.append((child, prefix + (action,), penalty + resource_penalty(c.kind), paid_so_far + spent))
    # The policy can play a Map-marked deterministic card to claim a known bonus.
    for uid, turn, options in s.rewards:
        if turn != s.turn:
            continue
        c = next((h for h in s.hand if h.uid == uid), None)
        if c is None:
            continue
        eligible = next((a for a in deterministic_actions(s) if a[1] == uid), None)
        if eligible:
            score = max((acquisition_value(s, k) for k in options), default=0) - 3 * card_cost(s, c)
            if c.kind == ICE:
                score += 9 if not s.ice_discount else 3
            if score > best_score:
                best_score, best_action = score, eligible
    return best_action


def mulligan(rng, second, policy):
    deck = [Card(100 + k * 3 + j, k, shadow=k == SHADOW) for k, n in enumerate(COPIES) for j in range(n)]
    rng.shuffle(deck)
    n = 4 if second else 3
    opening, deck = deck[:n], deck[n:]
    keep = MINIONS | {DIG, SWINDLE, SHROUD}
    if policy == "combo":
        if any(c.kind in (SWINDLE, SHROUD) for c in opening):
            keep |= {PREP}
    elif policy == "cheap":
        keep = MINIONS | {DIG, SHROUD}
        if any(c.kind in (DIG, SHROUD, SWINDLE, MAP) for c in opening):
            keep |= {PREP}
        if any(c.kind == ICE for c in opening):
            keep |= {STEP}
    held = [c for c in opening if c.kind in keep]
    rejected = [c for c in opening if c.kind not in keep]
    replacement = deck[:len(rejected)]
    deck = deck[len(rejected):] + rejected
    rng.shuffle(deck)
    hand = held + replacement
    if second:
        hand.append(Card(999, COIN))
    return State(deck, hand), opening, rejected


def game(rng, second=False, enemy=False, policy="guide", weighted=False, depth=2, record=False, ablate=None):
    s, opening, rejected = mulligan(rng, second, policy)
    trace = [] if record else None
    if trace is not None:
        trace.append({"event": "mulligan", "opening": [CN[c.kind] for c in opening],
                      "rejected": [CN[c.kind] for c in rejected], "kept_and_replaced": [CN[c.kind] for c in s.hand]})
    for turn in range(1, 6):
        s.turn, s.mana = turn, turn
        s.combo, s.prep, s.next_discount = False, 0, 0
        s.attacked = False
        s.rewards = ()
        s.enemy_target = enemy and turn >= 2
        natural = draw(s, rng)
        if trace is not None:
            trace.append({"turn": turn, "event": "natural_draw", "card": CN[natural.kind] if natural else None})
        for step in range(60):
            if s.weapon == PICK and s.durability and not s.attacked:
                action = ("attack", -1, "")
            elif ablate == "natural_only":
                plan = tactical(*tac_args(s))
                action = actual_action(s, plan[0]) if plan else None
                if action is None:
                    ice = next((c for c in s.hand if c.kind == ICE and card_cost(s, c) <= s.mana), None)
                    action = ("play", ice.uid, "") if ice and not s.board_ice else None
            else:
                action = choose_action(s, rng, depth)
            if action is None:
                break
            apply(s, action, rng, trace, weighted)
            assert 0 <= s.mana <= 10 and len(s.hand) <= 10
            if s.started:
                return turn, trace, s.burned
        else:
            raise AssertionError("Action safety cap reached")
        if trace is not None:
            trace.append({"turn": turn, "event": "end", "mana": s.mana,
                          "hand": [CN[c.kind] for c in s.hand], "ice_discount": s.ice_discount})
    return 0, trace, s.burned


def wilson(k, n):
    z = 1.95996398454
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z / denominator * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [center - half, center + half]


def run(n, seed, second, enemy, policy, weighted=False, depth=2, ablate=None):
    rng = random.Random(seed)
    counts = Counter()
    examples = {}
    burn_games = 0
    started_at = time.perf_counter()
    for i in range(n):
        state = rng.getstate() if len(examples) < 5 else None
        turn, _, burns = game(rng, second, enemy, policy, weighted, depth, ablate=ablate)
        counts[turn] += 1
        burn_games += bool(burns)
        if turn not in examples and state is not None:
            replay = random.Random()
            replay.setstate(state)
            _, trace, _ = game(replay, second, enemy, policy, weighted, depth, record=True, ablate=ablate)
            examples[turn] = trace
        if (i + 1) % max(1, n // 10) == 0:
            print(json.dumps({"done": i + 1, "n": n, "second": second, "enemy": enemy,
                              "policy": policy, "elapsed": round(time.perf_counter() - started_at, 1)}, ensure_ascii=False), flush=True)
    rows = []
    for t in range(1, 6):
        first = counts[t]
        cumulative = sum(counts[k] for k in range(1, t + 1))
        rows.append({"turn": t, "first_count": first, "first": first / n,
                     "first_ci95": wilson(first, n), "cumulative_count": cumulative,
                     "cumulative": cumulative / n, "cumulative_ci95": wilson(cumulative, n)})
    return {"n": n, "seed": seed, "second": second, "enemy_target": enemy, "mulligan": policy,
            "discover_weighted": weighted, "prefix_depth": depth, "ablation": ablate,
            "seconds": time.perf_counter() - started_at, "failed": counts[0],
            "burn_games": burn_games, "rows": rows, "examples": examples,
            "tactical_cache": str(tactical.cache_info())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--second", action="store_true")
    parser.add_argument("--enemy", action="store_true")
    parser.add_argument("--policy", choices=("guide", "cheap", "combo"), default="guide")
    parser.add_argument("--weighted", action="store_true")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--natural-only", action="store_true")
    parser.add_argument("--out", default="result.json")
    args = parser.parse_args()
    _, decoded = decode_deck(DECK_CODE)
    assert decoded == dict(zip(DBF, COPIES)), "Deck code and engine list differ"
    result = run(args.n, args.seed, args.second, args.enemy, args.policy, args.weighted,
                 args.depth, "natural_only" if args.natural_only else None)
    (ROOT / args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": args.out, "seconds": result["seconds"], "rows": result["rows"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
